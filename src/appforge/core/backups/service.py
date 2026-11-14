"""Backup bookkeeping: list, prune (retention), delete and roll back.

Backups are created by ``core.updates.installer`` in ``.<Name>.backups/`` next to the AppImage and
recorded in ``entry.backup_info["backups"]`` as ``{"file", "version", "created"}``. This service
treats the *files on disk* as the truth: records whose file vanished are dropped, and AppImages
found in the backup folder without a record (e.g. after a database reset) are adopted.

Safety rules:
* Only files inside a ``.<something>.backups`` folder, ending in ``.AppImage`` (AppImages) or
  ``.bak`` (other formats), are ever deleted.
* A rollback backs up the currently installed file *first*, stages the restored file next to the
  target and swaps it in with ``os.replace``; any failure leaves the installed file untouched.
* Main-thread only (it writes to the SQLite connection), like ``UpdateService``.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..library import LibraryError, LibraryService
from ..models import AppEntry
from ..updates.installer import (
    InstallError, _safe_label, backup_dir_for, backup_suffix, validate_appimage_file,
    validate_executable_file,
)

log = logging.getLogger(__name__)

SETTING_KEEP = "backup_keep"
DEFAULT_KEEP = 3          # newest backups kept per app
MAX_KEEP = 50             # 0 means "keep everything"
_BACKUP_DIR_RE = re.compile(r"^\..+\.backups$")
_BACKUP_SUFFIXES = (".appimage", ".bak")


@dataclass
class BackupRecord:
    path: str
    version: str | None
    created: float
    size: int


@dataclass
class RollbackResult:
    entry: AppEntry
    restored_version: str | None
    saved_version: str | None     # version that was installed before and is now a backup


def is_backup_file(path: str | os.PathLike) -> bool:
    """True only for backup files inside a ``.<name>.backups`` folder (the deletion guard)."""
    p = Path(path)
    return bool(_BACKUP_DIR_RE.match(p.parent.name)) and p.suffix.lower() in _BACKUP_SUFFIXES


def _same(a: str, b: str) -> bool:
    return os.path.abspath(a) == os.path.abspath(b)


def _stem(path: Path) -> str:
    return re.sub(r"\.appimage$", "", path.name, flags=re.IGNORECASE)


def _version_from_name(filename: str, stem: str) -> str | None:
    base = re.sub(r"\.(appimage|bak)$", "", filename, flags=re.IGNORECASE)
    if base.startswith(stem + "-"):
        base = base[len(stem) + 1:]
    return None if base in ("", "previous") else base


def _unique_backup_path(bdir: Path, stem: str, label: str, ext: str = ".AppImage") -> Path:
    path = bdir / f"{stem}-{label}{ext}"
    n = 2
    while path.exists():
        path = bdir / f"{stem}-{label}-{n}{ext}"
        n += 1
    return path


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


class BackupService:
    def __init__(self, library: LibraryService):
        self.library = library
        self.db = library.db

    # -- retention setting --------------------------------------------------------------
    def retention(self) -> int:
        """How many backups to keep per app (0 = unlimited)."""
        raw = self.db.get_setting(SETTING_KEEP)
        try:
            return max(0, min(MAX_KEEP, int(raw))) if raw is not None else DEFAULT_KEEP
        except ValueError:
            return DEFAULT_KEEP

    def set_retention(self, keep: int) -> int:
        keep = max(0, min(MAX_KEEP, int(keep)))
        self.db.set_setting(SETTING_KEEP, str(keep))
        return keep

    # -- queries ------------------------------------------------------------------------
    def list_backups(self, app_id: str) -> list[BackupRecord]:
        """Backups of one app, newest first. Also repairs the stored list against the disk."""
        entry = self._require(app_id)
        return self._to_records(self._reconcile(entry))

    def excess(self, app_id: str, keep: int | None = None) -> list[BackupRecord]:
        """Backups that retention would delete (oldest beyond the newest ``keep``)."""
        keep = self.retention() if keep is None else keep
        records = self.list_backups(app_id)
        return records[keep:] if keep > 0 else []

    # -- commands -----------------------------------------------------------------------
    def prune(self, app_id: str, keep: int | None = None) -> list[str]:
        """Delete the oldest backups beyond the retention limit. Returns the deleted paths."""
        keep = self.retention() if keep is None else keep
        if keep <= 0:
            return []
        entry = self._require(app_id)
        recs = self._reconcile(entry)                       # newest first
        removed, remaining = [], list(recs[:keep])
        for rec in recs[keep:]:
            if self._delete_file(rec["file"]):
                removed.append(rec["file"])
            else:
                remaining.append(rec)                       # couldn't delete: keep tracking it
        if removed:
            self._store(entry, remaining)
        return removed

    def delete_backup(self, app_id: str, file: str) -> None:
        entry = self._require(app_id)
        recs = self._reconcile(entry)
        rec = next((r for r in recs if _same(r["file"], file)), None)
        if rec is None:
            raise LibraryError("That backup no longer exists.")
        if not self._delete_file(rec["file"]):
            raise LibraryError("Couldn't delete that backup file.")
        self._store(entry, [r for r in recs if r is not rec])

    def rollback(self, app_id: str, file: str) -> RollbackResult:
        """Make ``file`` (one of this app's backups) the installed version.

        The installed file is backed up first, so a rollback can itself be undone from the list.
        """
        entry = self._require(app_id)
        recs = self._reconcile(entry)
        rec = next((r for r in recs if _same(r["file"], file)), None)
        if rec is None:
            raise LibraryError("That backup no longer exists.")
        src, target = Path(rec["file"]), Path(entry.path)
        if not os.access(target.parent, os.W_OK):
            raise LibraryError(f"AppForge can't write to {target.parent}.")
        has_current = target.is_file()
        if has_current and os.path.samefile(src, target):
            raise LibraryError("That backup is the version that is already installed.")
        try:
            if entry.format == "appimage":
                validate_appimage_file(src)
            else:
                validate_executable_file(src)
        except InstallError as exc:
            raise LibraryError(f"This backup can't be restored: {exc}") from exc

        try:
            mode = (target.stat().st_mode if has_current else src.stat().st_mode) & 0o7777 | 0o111
        except OSError:
            mode = 0o755
        saved_version = entry.installed_version

        pre_backup: Path | None = None
        stage = target.parent / f".{target.name}.{os.getpid()}.rollback.part"
        try:
            if has_current:                                  # 1. keep what is installed now
                bdir = backup_dir_for(target)
                bdir.mkdir(exist_ok=True)
                pre_backup = _unique_backup_path(bdir, _stem(target), _safe_label(saved_version),
                                                 backup_suffix(entry.format))
                _link_or_copy(target, pre_backup)
            stage.unlink(missing_ok=True)                    # 2. stage the restored file
            _link_or_copy(src, stage)
            os.chmod(stage, mode)
            os.replace(stage, target)                        # 3. atomic swap
        except OSError as exc:
            stage.unlink(missing_ok=True)
            if pre_backup is not None:
                pre_backup.unlink(missing_ok=True)           # nothing changed: drop the new backup
            raise LibraryError(f"Couldn't restore the backup: {exc.strerror or exc}") from exc

        remaining = [r for r in recs if r is not rec]
        try:                                                 # the restored file is now the active one
            src.unlink()
        except OSError:
            log.warning("Could not remove restored backup %s", src, exc_info=True)
            remaining.append(rec)
        if pre_backup is not None:
            remaining.append({"file": str(pre_backup), "version": saved_version, "created": time.time()})

        restored = rec.get("version")
        entry.installed_version = restored
        if restored:
            entry.metadata["installed_version_source"] = "rollback"
        else:
            entry.metadata.pop("installed_version_source", None)
        entry.metadata["last_rollback"] = {"time": time.time(), "from": saved_version, "to": restored}
        entry.metadata.pop("last_install", None)
        LibraryService._reset_update_state(entry)            # latest version must be re-checked
        self._store(entry, remaining)
        try:                                                 # fresh icon/description; version if unknown
            entry = self.library.refresh_metadata(app_id, overwrite_version=not restored)
        except Exception:                                    # noqa: BLE001 - best effort
            entry = self.db.get(app_id) or entry
        try:
            self.prune(app_id)
        except Exception:                                    # noqa: BLE001
            log.warning("Retention pruning failed after rollback", exc_info=True)
        return RollbackResult(self.db.get(app_id) or entry, restored, saved_version)

    # -- internals ----------------------------------------------------------------------
    def _require(self, app_id: str) -> AppEntry:
        entry = self.db.get(app_id)
        if entry is None:
            raise LibraryError("That application is no longer in the library.")
        return entry

    def _reconcile(self, entry: AppEntry) -> list[dict]:
        """Records whose file exists, plus adopted orphans; newest first. Persists any change."""
        stored = list(entry.backup_info.get("backups", []))
        found = scan_backup_records(entry)
        if found != stored:
            self._store(entry, found)
        return found

    def _store(self, entry: AppEntry, records: list[dict]) -> None:
        records = sorted(records, key=lambda r: float(r.get("created") or 0), reverse=True)
        entry.backup_info["backups"] = records
        self.db.update(entry)

    @staticmethod
    def _to_records(recs: list[dict]) -> list[BackupRecord]:
        out = []
        for r in recs:
            try:
                size = os.stat(r["file"]).st_size
            except OSError:
                continue
            out.append(BackupRecord(r["file"], r.get("version"), float(r.get("created") or 0), size))
        return out

    @staticmethod
    def _delete_file(path: str) -> bool:
        if not is_backup_file(path):                         # never delete outside a backups folder
            log.warning("Refusing to delete non-backup path %s", path)
            return False
        try:
            Path(path).unlink(missing_ok=True)
            return True
        except OSError:
            log.warning("Could not delete backup %s", path, exc_info=True)
            return False


def scan_backup_records(entry: AppEntry) -> list[dict]:
    """Read backup records from disk without changing SQLite; safe for workers."""
    stored = list(entry.backup_info.get("backups", []))
    found: list[dict] = []
    seen: set[str] = set()
    for rec in stored:
        f = rec.get("file")
        if f and os.path.abspath(f) not in seen and os.path.isfile(f):
            seen.add(os.path.abspath(f))
            found.append(rec)
    target = Path(entry.path)
    bdir = backup_dir_for(target)
    if bdir.is_dir():
        for p in sorted(bdir.iterdir()):
            if (p.suffix.lower() in _BACKUP_SUFFIXES and p.is_file()
                    and os.path.abspath(p) not in seen):
                seen.add(os.path.abspath(p))
                found.append({"file": str(p), "version": _version_from_name(p.name, _stem(target)),
                              "created": p.stat().st_mtime})
    found.sort(key=lambda r: float(r.get("created") or 0), reverse=True)
    return found


__all__ = ["BackupService", "BackupRecord", "RollbackResult", "DEFAULT_KEEP", "MAX_KEEP",
           "is_backup_file"]
