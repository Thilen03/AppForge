"""Phase 3: backup history, retention and rollback (pure core logic, no real AppImages needed)."""
import os
import sqlite3
import time
from pathlib import Path

import pytest

from appforge.core.backups import DEFAULT_KEEP, BackupService, is_backup_file
from appforge.core.backups import service as backups_mod
from appforge.core.database import MIGRATIONS, Database
from appforge.core.library import LibraryError
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.updates.installer import InstallError, InstallResult
from appforge.core.updates.service import UpdateService


@pytest.fixture(autouse=True)
def fake_validation(monkeypatch):
    """The fixtures here are plain byte blobs; real-AppImage validation is covered in test_updates."""
    def validate(path):
        if Path(path).read_bytes().startswith(b"BAD"):
            raise InstallError("not a valid AppImage")
    monkeypatch.setattr(backups_mod, "validate_appimage_file", validate)


def make_app(service, tmp_path, content=b"v3", version="3.0"):
    target = tmp_path / "apps" / "Dolphin.AppImage"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    target.chmod(0o755)
    entry = AppEntry(name="Dolphin", path=str(target), installed_version=version,
                     update_status=UpdateStatus.UP_TO_DATE, latest_version=version,
                     github_repo="https://github.com/o/r")
    service.db.add(entry)
    return entry, target


def add_backup(service, entry, version, content, age):
    """Create a backup file + record, ``age`` seconds old."""
    bdir = Path(entry.path).parent / ".Dolphin.backups"
    bdir.mkdir(exist_ok=True)
    f = bdir / f"Dolphin-{version}.AppImage"
    f.write_bytes(content)
    fresh = service.db.get(entry.id)
    fresh.backup_info.setdefault("backups", []).append(
        {"file": str(f), "version": version, "created": time.time() - age})
    service.db.update(fresh)
    return f


# ----------------------------------------------------------------------------- settings
def test_retention_default_set_and_clamped(service):
    b = BackupService(service)
    assert b.retention() == DEFAULT_KEEP == 3
    assert b.set_retention(5) == 5 and b.retention() == 5
    assert b.set_retention(-4) == 0 and b.retention() == 0       # 0 = unlimited
    assert b.set_retention(10_000) == 50


def test_migration_adds_settings_table_to_existing_v1_database(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0])
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    db = Database(path)
    assert db.get_setting("x") is None
    db.set_setting("x", "1")
    db.set_setting("x", "2")
    assert db.get_setting("x") == "2"
    db.close()


# ----------------------------------------------------------------------------- listing
def test_list_drops_missing_files_and_adopts_orphans(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    gone = add_backup(service, entry, "1.0", b"v1", age=300)
    add_backup(service, entry, "2.0", b"v2", age=100)
    gone.unlink()
    orphan = target.parent / ".Dolphin.backups" / "Dolphin-0.9.AppImage"
    orphan.write_bytes(b"v09")
    os.utime(orphan, (time.time() - 1000, time.time() - 1000))     # orphans are dated by file mtime
    recs = BackupService(service).list_backups(entry.id)
    assert [r.version for r in recs][0] == "2.0" and {r.version for r in recs} == {"2.0", "0.9"}
    assert all(r.size > 0 for r in recs)
    stored = [Path(r["file"]).name for r in service.db.get(entry.id).backup_info["backups"]]
    assert "Dolphin-1.0.AppImage" not in stored and "Dolphin-0.9.AppImage" in stored


# ----------------------------------------------------------------------------- retention
def test_prune_keeps_newest_n_and_deletes_oldest_files(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    files = {v: add_backup(service, entry, v, v.encode(), age) for v, age in
             [("1.0", 400), ("1.5", 300), ("2.0", 200), ("2.5", 100)]}
    b = BackupService(service)
    b.set_retention(2)
    removed = b.prune(entry.id)
    assert {Path(p).name for p in removed} == {"Dolphin-1.0.AppImage", "Dolphin-1.5.AppImage"}
    assert not files["1.0"].exists() and not files["1.5"].exists()
    assert files["2.0"].exists() and files["2.5"].exists()
    assert [r.version for r in b.list_backups(entry.id)] == ["2.5", "2.0"]


def test_prune_unlimited_keeps_everything(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    for i in range(5):
        add_backup(service, entry, f"1.{i}", b"x", age=100 - i)
    b = BackupService(service)
    b.set_retention(0)
    assert b.prune(entry.id) == [] and len(b.list_backups(entry.id)) == 5
    assert b.excess(entry.id) == []


def test_excess_previews_without_deleting(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    for v, age in [("1.0", 300), ("2.0", 200), ("2.5", 100)]:
        add_backup(service, entry, v, b"x", age)
    b = BackupService(service)
    assert [r.version for r in b.excess(entry.id, 1)] == ["2.0", "1.0"]
    assert len(b.list_backups(entry.id)) == 3


def test_prune_never_deletes_outside_a_backups_folder(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    innocent = tmp_path / "Documents" / "important.AppImage"
    innocent.parent.mkdir()
    innocent.write_bytes(b"precious")
    for i, v in enumerate(["1.0", "2.0"]):
        add_backup(service, entry, v, b"x", age=100 - i)
    e = service.db.get(entry.id)
    e.backup_info["backups"].append({"file": str(innocent), "version": "0.1", "created": 1.0})
    service.db.update(e)
    BackupService(service).prune(entry.id, keep=1)
    assert innocent.read_bytes() == b"precious" and target.exists()
    assert not is_backup_file(innocent) and not is_backup_file(target)


def test_delete_backup(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    f = add_backup(service, entry, "1.0", b"x", age=10)
    b = BackupService(service)
    b.delete_backup(entry.id, str(f))
    assert not f.exists() and b.list_backups(entry.id) == []
    with pytest.raises(LibraryError):
        b.delete_backup(entry.id, str(f))


def test_apply_install_prunes_to_retention(service, tmp_path):
    entry, target = make_app(service, tmp_path, version="4.0")
    for v, age in [("1.0", 400), ("2.0", 300), ("3.0", 200)]:
        add_backup(service, entry, v, v.encode(), age)
    new_backup = add_backup(service, entry, "4.0", b"v4", age=0)   # what the installer just wrote
    # the installer has already written the file; apply_install records it and then prunes
    e = service.db.get(entry.id)
    e.backup_info["backups"] = [r for r in e.backup_info["backups"] if r["file"] != str(new_backup)]
    e.latest_version, e.metadata["update"] = "5.0", {"tag": "v5.0"}
    service.db.update(e)
    ups = UpdateService(service)
    ups.backups.set_retention(2)
    ups.apply_install(entry.id, InstallResult(str(target), str(new_backup), "verified (sha256)", 2), "v5.0")
    left = sorted(r.version for r in ups.backups.list_backups(entry.id))
    assert left == ["3.0", "4.0"]


# ----------------------------------------------------------------------------- rollback
def test_rollback_swaps_versions_and_keeps_current_as_backup(service, tmp_path):
    entry, target = make_app(service, tmp_path, content=b"v3-content", version="3.0")
    old = add_backup(service, entry, "2.0", b"v2-content", age=100)
    b = BackupService(service)
    res = b.rollback(entry.id, str(old))

    assert target.read_bytes() == b"v2-content" and os.access(target, os.X_OK)
    assert not old.exists()                                           # consumed: it is the active file now
    versions = {r.version: r for r in b.list_backups(entry.id)}
    assert set(versions) == {"3.0"}
    assert Path(versions["3.0"].path).read_bytes() == b"v3-content"   # the replaced version is kept
    assert res.restored_version == "2.0" and res.saved_version == "3.0"
    e = service.db.get(entry.id)
    assert e.installed_version == "2.0" and e.metadata["installed_version_source"] == "rollback"
    assert e.metadata["last_rollback"]["from"] == "3.0"
    assert e.update_status is UpdateStatus.UNAVAILABLE and e.latest_version is None   # must be re-checked
    assert not list(target.parent.glob(".*.part"))


def test_rollback_can_be_undone(service, tmp_path):
    entry, target = make_app(service, tmp_path, content=b"v3", version="3.0")
    old = add_backup(service, entry, "2.0", b"v2", age=100)
    b = BackupService(service)
    b.rollback(entry.id, str(old))
    forward = next(r for r in b.list_backups(entry.id) if r.version == "3.0")
    b.rollback(entry.id, forward.path)
    assert target.read_bytes() == b"v3" and service.db.get(entry.id).installed_version == "3.0"
    assert [r.version for r in b.list_backups(entry.id)] == ["2.0"]


def test_rollback_respects_retention(service, tmp_path):
    entry, _ = make_app(service, tmp_path, version="9.0")
    for i in range(4):
        add_backup(service, entry, f"1.{i}", f"c{i}".encode(), age=400 - i * 10)
    b = BackupService(service)
    b.set_retention(2)
    newest = b.list_backups(entry.id)[0]
    b.rollback(entry.id, newest.path)
    assert len(b.list_backups(entry.id)) == 2


def test_rollback_rejects_invalid_backup_and_changes_nothing(service, tmp_path):
    entry, target = make_app(service, tmp_path, content=b"v3", version="3.0")
    bad = add_backup(service, entry, "2.0", b"BAD-file", age=100)
    with pytest.raises(LibraryError, match="can't be restored"):
        BackupService(service).rollback(entry.id, str(bad))
    assert target.read_bytes() == b"v3" and bad.exists()
    assert service.db.get(entry.id).installed_version == "3.0"
    assert [r.version for r in BackupService(service).list_backups(entry.id)] == ["2.0"]


def test_rollback_failure_during_swap_leaves_everything_intact(service, tmp_path, monkeypatch):
    entry, target = make_app(service, tmp_path, content=b"v3", version="3.0")
    old = add_backup(service, entry, "2.0", b"v2", age=100)

    def boom(*a, **k):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr(backups_mod.os, "replace", boom)
    with pytest.raises(LibraryError, match="Couldn't restore"):
        BackupService(service).rollback(entry.id, str(old))
    assert target.read_bytes() == b"v3" and old.read_bytes() == b"v2"
    assert [p.name for p in (target.parent / ".Dolphin.backups").iterdir()] == ["Dolphin-2.0.AppImage"]
    assert not list(target.parent.glob(".*.part"))
    assert service.db.get(entry.id).installed_version == "3.0"


def test_rollback_refuses_the_already_installed_file(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    bdir = target.parent / ".Dolphin.backups"
    bdir.mkdir()
    link = bdir / "Dolphin-3.0.AppImage"
    os.link(target, link)
    with pytest.raises(LibraryError, match="already installed"):
        BackupService(service).rollback(entry.id, str(link))


def test_rollback_when_installed_file_is_missing_just_restores(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    old = add_backup(service, entry, "2.0", b"v2", age=100)
    target.unlink()
    BackupService(service).rollback(entry.id, str(old))
    assert target.read_bytes() == b"v2" and os.access(target, os.X_OK)


def test_rollback_unknown_backup(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    with pytest.raises(LibraryError, match="no longer exists"):
        BackupService(service).rollback(entry.id, str(tmp_path / "nope.AppImage"))


def test_refresh_does_not_overwrite_a_rolled_back_version(service, tmp_path, monkeypatch):
    """After a rollback the file's embedded version must not silently replace the recorded one."""
    from appforge.core.formats import AppMetadata
    entry, _ = make_app(service, tmp_path, version="2.0")
    e = service.db.get(entry.id)
    e.metadata["installed_version_source"] = "rollback"
    service.db.update(e)
    md = AppMetadata(format_id="appimage", name_suggestion="Dolphin", version="9.9.9")
    monkeypatch.setattr("appforge.core.library.inspect_file", lambda p: md)
    service.refresh_metadata(entry.id)
    assert service.db.get(entry.id).installed_version == "2.0"
