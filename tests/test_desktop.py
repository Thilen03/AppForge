"""Phase 4: application-menu launchers (.desktop entries) and moved/renamed-file handling.

Pure core logic: no real AppImages and no Qt needed.
"""
import configparser
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from appforge.core import library as library_mod
from appforge.core import relocate as relocate_mod
from appforge.core.desktop import (
    DesktopError, DesktopService, entry_filename, quote_exec_arg, render_entry,
)
from appforge.core.formats import AppMetadata
from appforge.core.library import LibraryError
from appforge.core.models import AppEntry
from appforge.core.paths import applications_dir
from appforge.core.relocate import find_candidates, identity_key


# ------------------------------------------------------------------------------- helpers
def parse_exec(value: str) -> list[str]:
    """A small, spec-conformant Exec parser (string-unescape, then double-quote rules, %% -> %)."""
    value = value.replace("\\\\", "\\")                      # string-value layer
    args, cur, i, quoted, started = [], "", 0, False, False
    while i < len(value):
        c = value[i]
        if quoted:
            if c == "\\" and i + 1 < len(value) and value[i + 1] in '"`$\\':
                cur += value[i + 1]
                i += 1
            elif c == '"':
                quoted = False
            else:
                cur += c
        elif c == '"':
            quoted, started = True, True
        elif c == " ":
            if started or cur:
                args.append(cur)
            cur, started = "", False
        else:
            cur += c
        i += 1
    if started or cur:
        args.append(cur)
    return [a.replace("%%", "%") for a in args]


def read_entry(path: Path) -> dict[str, str]:
    cp = configparser.RawConfigParser(strict=True, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text("utf-8"))
    return dict(cp.items("Desktop Entry"))


def make_app(service, tmp_path, name="Dolphin", filename="Dolphin.AppImage", **meta):
    target = tmp_path / "apps" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x" * 100)
    target.chmod(0o755)
    entry = AppEntry(name=name, path=str(target), installed_version="1.0", metadata=dict(meta))
    service.db.add(entry)
    return service.db.get(entry.id), target


def launcher(service, entry) -> Path:
    return service.desktop.entry_path(entry.id)


# ------------------------------------------------------------------------------- Exec quoting
def test_exec_quoting_round_trips_awkward_paths():
    paths = ["/home/u/Apps/Plain.AppImage", "/home/u/My Apps/Foo Bar.AppImage", '/tmp/a"b.AppImage',
             "/tmp/dollar$HOME.AppImage", "/tmp/back\\slash.AppImage", "/tmp/100%/x.AppImage",
             "/tmp/(paren)/`tick`.AppImage", "/tmp/semi;colon&amp.AppImage", "/tmp/it's.AppImage"]
    for p in paths:
        assert parse_exec(quote_exec_arg(p)) == [p], p
        assert parse_exec(quote_exec_arg(p) + " %U") == [p, "%U"], p
    assert quote_exec_arg("/plain/path") == "/plain/path"          # no needless quoting
    assert quote_exec_arg("/a b") == '"/a b"'
    assert quote_exec_arg("/a%b") == "/a%%b"


# ------------------------------------------------------------------------------- rendering
def test_render_has_required_keys_and_marker(service, tmp_path):
    entry, target = make_app(service, tmp_path, description_unused=None)
    entry.description = "Fast editor"
    entry.metadata.update(categories="Development;TextEditor;", generic_name="Editor",
                          desktop_exec="app --flag %U", startup_wm_class="dolphin")
    data = read_entry_from_text(render_entry(entry))
    assert data["Type"] == "Application" and data["Name"] == "Dolphin"
    assert data["Comment"] == "Fast editor" and data["GenericName"] == "Editor"
    assert parse_exec(data["Exec"]) == [str(target), "%U"]       # only the field code is borrowed
    assert data["TryExec"] == str(target) and data["Path"] == str(target.parent)
    assert data["Terminal"] == "false" and data["StartupWMClass"] == "dolphin"
    assert data["Categories"] == "Development;TextEditor;"
    assert data["Icon"] == "application-x-executable"            # no icon stored
    assert data["X-AppForge-Id"] == entry.id


def read_entry_from_text(text: str) -> dict[str, str]:
    cp = configparser.RawConfigParser(strict=True, interpolation=None)
    cp.optionxform = str
    cp.read_string(text)
    return dict(cp.items("Desktop Entry"))


def test_render_defaults_and_icon(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"png")
    entry.icon_path = str(icon)
    data = read_entry_from_text(render_entry(entry))
    assert data["Icon"] == str(icon)
    assert data["Categories"] == "Utility;"
    assert "Comment" not in data and "StartupWMClass" not in data
    assert parse_exec(data["Exec"]) == [entry.path]              # no field code unless the app had one
    entry.metadata["categories"] = "Graphics;bad cat;Foo\nExec=evil;"
    assert read_entry_from_text(render_entry(entry))["Categories"] == "Graphics;"


def test_render_cannot_be_injected_through_name_or_description(service, tmp_path):
    entry, target = make_app(service, tmp_path, name="Evil\nExec=rm -rf ~\n[Other]\nX=1")
    entry.description = "line1\r\nExec=bad\n" + "z" * 500
    text = render_entry(entry)
    data = read_entry_from_text(text)                            # strict parser: one section, no dup keys
    assert parse_exec(data["Exec"]) == [str(target)]
    assert "\n" not in data["Name"] and len(data["Comment"]) <= 200
    assert text.count("\nExec=") == 1                             # only the real Exec line starts a line


def test_render_rejects_control_characters_in_path(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    entry.path = entry.path + "\nExec=x"
    with pytest.raises(DesktopError):
        render_entry(entry)


# ------------------------------------------------------------------------------- lifecycle
def test_enable_disable_lifecycle(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    assert not service.desktop_enabled(entry) and not launcher(service, entry).exists()
    on = service.set_desktop_integration(entry.id, True)
    f = launcher(service, entry)
    assert service.desktop_enabled(on) and f.is_file() and f.name == entry_filename(entry.id)
    assert f.parent == applications_dir()                         # redirected into the test data dir
    assert str(f.parent).startswith(str(tmp_path))
    assert oct(f.stat().st_mode & 0o777) == "0o644"
    assert read_entry(f)["Name"] == "Dolphin"
    off = service.set_desktop_integration(entry.id, False)
    assert not service.desktop_enabled(off) and not f.exists()
    assert target.exists()                                       # the AppImage is never touched
    assert service.set_desktop_integration(entry.id, False).id == entry.id   # idempotent


def test_write_is_skipped_when_unchanged(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    assert service.desktop.write_entry(entry) is True
    f = launcher(service, entry)
    os.utime(f, (1_000_000, 1_000_000))
    assert service.desktop.write_entry(entry) is False
    assert f.stat().st_mtime == 1_000_000                        # no rewrite -> no menu-cache churn
    entry.name = "New"
    assert service.desktop.write_entry(entry) is True


def test_no_temp_files_left_behind(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    assert [p.name for p in applications_dir().iterdir()] == [entry_filename(entry.id)]


def test_add_application_can_integrate(service, tmp_path):
    f = tmp_path / "apps" / "Zed.AppImage"
    f.parent.mkdir()
    f.write_bytes(b"x")
    md = AppMetadata(format_id="appimage", name_suggestion="Zed", version="2.0",
                     description="Editor", extra={"categories": "Development;"})
    entry = service.add_application(str(f), metadata=md, integrate_desktop=True)
    assert service.desktop_enabled(service.get(entry.id))
    assert read_entry(launcher(service, entry))["Categories"] == "Development;"
    other = tmp_path / "apps" / "Other.AppImage"
    other.write_bytes(b"x")
    plain = service.add_application(str(other), metadata=md)
    assert not service.desktop_enabled(plain) and not launcher(service, plain).exists()


def test_failure_to_write_is_reported_not_fatal_on_add(service, tmp_path, monkeypatch):
    f = tmp_path / "Q.AppImage"
    f.write_bytes(b"x")
    md = AppMetadata(format_id="appimage", name_suggestion="Q")
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where a directory should be")
    monkeypatch.setenv("APPFORGE_APPLICATIONS_DIR", str(blocked / "apps"))
    entry = service.add_application(str(f), metadata=md, integrate_desktop=True)   # must not raise
    assert not service.desktop_enabled(service.get(entry.id))
    with pytest.raises(LibraryError):
        service.set_desktop_integration(entry.id, True)


def test_desktop_default_setting(service):
    assert service.desktop_default() is True
    service.set_desktop_default(False)
    assert service.desktop_default() is False
    service.set_desktop_default(True)
    assert service.desktop_default() is True


# ------------------------------------------------------------------------------- rename / move / icon
def test_rename_updates_launcher_but_not_file_name(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    f = launcher(service, entry)
    service.update_application(entry.id, name="Dolphin Emulator")
    assert read_entry(f)["Name"] == "Dolphin Emulator"
    assert launcher(service, entry) == f and f.exists()          # same file id -> pins survive


def test_relocating_the_file_rewrites_exec_and_tryexec(service, tmp_path, monkeypatch):
    monkeypatch.setattr(library_mod, "detect_format", lambda p: SimpleNamespace(id="appimage"))
    entry, old = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    new = tmp_path / "elsewhere" / "Dolphin-2.0.AppImage"
    new.parent.mkdir()
    new.write_bytes(b"y" * 100)
    new.chmod(0o755)
    service.update_application(entry.id, path=str(new))
    data = read_entry(launcher(service, entry))
    assert parse_exec(data["Exec"]) == [str(new)]
    assert data["TryExec"] == str(new) and data["Path"] == str(new.parent)


def test_icon_change_updates_launcher(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    img = tmp_path / "mine.png"
    img.write_bytes(b"\x89PNG")
    updated = service.update_application(entry.id, icon=str(img))
    assert read_entry(launcher(service, entry))["Icon"] == updated.icon_path
    assert Path(updated.icon_path).is_file()
    service.update_application(entry.id, icon=None)              # back to the default icon
    assert read_entry(launcher(service, entry))["Icon"] in ("application-x-executable",
                                                              service.get(entry.id).icon_path)


def test_update_application_without_integration_writes_nothing(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    service.update_application(entry.id, name="Other")
    assert not launcher(service, entry).exists()


def test_remove_application_removes_launcher_only(service, tmp_path):
    entry, target = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    f = launcher(service, entry)
    service.remove_application(entry.id)
    assert not f.exists() and target.exists()


# ------------------------------------------------------------------------------- safety
def test_never_deletes_files_that_are_not_ours(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    foreign = launcher(service, entry)
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("[Desktop Entry]\nType=Application\nName=Hand made\nExec=foo\n")  # no marker
    assert service.desktop.remove(entry.id) is False and foreign.exists()
    other = foreign.parent / "firefox.desktop"
    other.write_text("[Desktop Entry]\nName=Firefox\n")
    service.sync_desktop_entries()
    assert other.exists()
    assert foreign.exists()                                      # unmarked -> not managed, not orphan-cleaned


def test_marker_must_match_file_name(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    f = launcher(service, entry)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"[Desktop Entry]\nName=x\nX-AppForge-Id=someone-else\n")
    assert service.desktop.remove(entry.id) is False and f.exists()
    assert service.desktop.list_managed() == []


# ------------------------------------------------------------------------------- startup sync
def test_sync_repairs_missing_and_outdated(service, tmp_path):
    a, _ = make_app(service, tmp_path, name="A", filename="A.AppImage")
    b, _ = make_app(service, tmp_path, name="B", filename="B.AppImage")
    service.set_desktop_integration(a.id, True)
    service.set_desktop_integration(b.id, True)
    launcher(service, a).unlink()                                # user deleted it
    launcher(service, b).write_text(launcher(service, b).read_text().replace("Name=B", "Name=Old"))
    report = service.sync_desktop_entries()
    assert sorted(report.repaired) == ["A", "B"] and not report.failed
    assert read_entry(launcher(service, a))["Name"] == "A"
    assert read_entry(launcher(service, b))["Name"] == "B"
    assert service.sync_desktop_entries().changed is False       # second run is a no-op


def test_sync_adopts_unflagged_launchers(service, tmp_path):
    entry, _ = make_app(service, tmp_path)
    service.desktop.write_entry(entry)                           # e.g. crash before the flag was saved
    report = service.sync_desktop_entries()
    assert report.adopted == ["Dolphin"]
    assert service.desktop_enabled(service.get(entry.id))


def test_sync_removes_orphans_only_when_their_file_is_gone(service, tmp_path):
    ghost = AppEntry(name="Ghost", path=str(tmp_path / "gone" / "Ghost.AppImage"))
    alive_file = tmp_path / "Alive.AppImage"
    alive_file.write_bytes(b"x")
    alive = AppEntry(name="Alive", path=str(alive_file))
    service.desktop.write_entry(ghost)                           # not in the library, file missing
    service.desktop.write_entry(alive)                           # not in the library, file exists
    report = service.sync_desktop_entries()
    assert report.removed == [entry_filename(ghost.id)]
    assert not service.desktop.exists(ghost.id)
    assert service.desktop.exists(alive.id)                      # still works -> left alone


def test_sync_with_unwritable_directory_reports_failure(service, tmp_path, monkeypatch):
    entry, _ = make_app(service, tmp_path)
    service.set_desktop_integration(entry.id, True)
    blocked = tmp_path / "blocked"
    blocked.write_text("file")
    monkeypatch.setenv("APPFORGE_APPLICATIONS_DIR", str(blocked / "apps"))
    report = service.sync_desktop_entries()
    assert [n for n, _ in report.failed] == ["Dolphin"]


# ------------------------------------------------------------------------------- applications_dir
def test_applications_dir_resolution(monkeypatch, tmp_path):
    for var in ("APPFORGE_APPLICATIONS_DIR", "APPFORGE_DATA_DIR", "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert applications_dir() == tmp_path / "home" / ".local" / "share" / "applications"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert applications_dir() == tmp_path / "xdg" / "applications"
    monkeypatch.setenv("APPFORGE_DATA_DIR", str(tmp_path / "portable"))
    assert applications_dir() == tmp_path / "portable" / "applications"
    monkeypatch.setenv("APPFORGE_APPLICATIONS_DIR", str(tmp_path / "explicit"))
    assert applications_dir() == tmp_path / "explicit"
    assert not (tmp_path / "xdg" / "applications").exists()      # resolving never creates anything


# ------------------------------------------------------------------------------- relocation
def test_identity_key():
    same = ["Dolphin-Emu-5.0-x86_64.AppImage", "dolphin_emu.AppImage", "Dolphin Emu",
            "Dolphin.Emu-v2.1.3-linux-amd64.AppImage", "dolphin-emu-2024-05-01.appimage"]
    assert {identity_key(n) for n in same} == {"dolphinemu"}
    assert identity_key("7zip-23.01-x86_64.AppImage") == "7zip"
    assert identity_key("Other-App-1.0.AppImage") != identity_key("Dolphin-Emu-1.0.AppImage")


@pytest.fixture()
def fake_appimage_detection(monkeypatch):
    monkeypatch.setattr(relocate_mod, "detect_format", lambda p: SimpleNamespace(id="appimage"))


def test_find_candidates_after_move_and_rename(service, tmp_path, fake_appimage_detection):
    entry, old = make_app(service, tmp_path, name="Dolphin Emu", filename="Dolphin-Emu-5.0-x86_64.AppImage")
    old.unlink()                                                  # the file vanished
    new_dir = tmp_path / "Downloads"
    new_dir.mkdir()
    moved = new_dir / "Dolphin-Emu-5.1-x86_64.AppImage"
    moved.write_bytes(b"x")
    (new_dir / "Other-1.0.AppImage").write_bytes(b"x")            # different app
    (new_dir / "Dolphin-Emu-notes.txt").write_text("hi")          # not an AppImage
    (new_dir / ".Dolphin-Emu-5.2.AppImage").write_bytes(b"x")     # hidden temp/backup-like file
    assert find_candidates(entry, extra_dirs=[new_dir], include_defaults=False) == [moved]


def test_find_candidates_prefers_old_folder_and_skips_tracked_files(service, tmp_path, fake_appimage_detection):
    entry, old = make_app(service, tmp_path, name="Foo", filename="Foo-1.0.AppImage")
    old.unlink()
    same_dir = old.parent / "Foo-2.0.AppImage"
    same_dir.write_bytes(b"x")
    elsewhere = tmp_path / "x"
    elsewhere.mkdir()
    (elsewhere / "Foo.AppImage").write_bytes(b"x")
    taken = elsewhere / "Foo-3.0.AppImage"
    taken.write_bytes(b"x")
    got = find_candidates(entry, extra_dirs=[elsewhere], exclude=[taken], include_defaults=False)
    assert got == [same_dir, elsewhere / "Foo.AppImage"]          # old folder first; tracked file skipped


def test_find_candidates_requires_real_appimage(service, tmp_path, monkeypatch):
    monkeypatch.setattr(relocate_mod, "detect_format", lambda p: None)
    entry, old = make_app(service, tmp_path, name="Foo", filename="Foo-1.0.AppImage")
    old.unlink()
    (old.parent / "Foo-2.0.AppImage").write_bytes(b"not an appimage")
    assert find_candidates(entry, include_defaults=False) == []


def test_service_suggest_relocations_uses_other_library_folders(service, tmp_path, fake_appimage_detection,
                                                               monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "emptyhome"))
    gone, old = make_app(service, tmp_path, name="Gone", filename="Gone-1.0.AppImage")
    old.unlink()
    neighbour = tmp_path / "other-place" / "Neighbour.AppImage"
    neighbour.parent.mkdir()
    neighbour.write_bytes(b"x")
    service.db.add(AppEntry(name="Neighbour", path=str(neighbour)))
    moved = neighbour.parent / "Gone-1.1.AppImage"                # lives next to another library app
    moved.write_bytes(b"x")
    assert service.suggest_relocations(gone.id) == [moved]
    with pytest.raises(LibraryError):
        service.suggest_relocations("nope")
