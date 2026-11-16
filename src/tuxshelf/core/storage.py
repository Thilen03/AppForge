"""Read-only storage snapshots and explicit backup cleanup, without SQLite or Qt."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import stat

from .backups.files import backup_directory, backup_name, delete_managed_backup, identity
from .backups.service import scan_backup_records
from .models import AppEntry


@dataclass
class StoredBackup:
    path: str
    version: str | None
    created: float
    size: int
    reclaimable: int
    identity: tuple


@dataclass
class AppStorage:
    entry: AppEntry
    size: int = 0
    backups: list[StoredBackup] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    @property
    def backup_size(self):
        return sum(b.size for b in self.backups)

    @property
    def total(self):
        return self.size + self.backup_size


@dataclass
class StorageSnapshot:
    apps: list[AppStorage] = field(default_factory=list)
    cancelled: bool = False

    @property
    def application_size(self):
        return sum(a.size for a in self.apps)

    @property
    def backup_size(self):
        return sum(a.backup_size for a in self.apps)

    @property
    def backup_count(self):
        return sum(len(a.backups) for a in self.apps)


def scan_storage(entries, cancel, progress=lambda done, total: None):
    result = StorageSnapshot()
    for index, entry in enumerate(entries):
        if cancel.is_set():
            result.cancelled = True
            break
        app = AppStorage(entry)
        try:
            info = os.stat(entry.path)
            if stat.S_ISREG(info.st_mode):
                app.size = info.st_size
            else:
                app.notices.append('Application is not a regular file')
        except OSError as exc:
            app.notices.append(f'Application unavailable: {exc.strerror or exc}')
        try:
            records = scan_backup_records(entry, cancel=cancel)
            if records:
                with backup_directory(entry) as fd:
                    for record in records:
                        if cancel.is_set():
                            result.cancelled = True
                            break
                        try:
                            info = os.stat(backup_name(entry, record['file']), dir_fd=fd,
                                           follow_symlinks=False)
                            if not stat.S_ISREG(info.st_mode):
                                app.notices.append('A backup changed during scanning; refresh')
                                continue
                            app.backups.append(StoredBackup(
                                record['file'], record.get('version'), record['created'],
                                info.st_size, info.st_size if info.st_nlink == 1 else 0, identity(info)))
                        except OSError:
                            app.notices.append('A backup disappeared or is unavailable; refresh')
        except (OSError, ValueError) as exc:
            app.notices.append(f'Backup folder unavailable: {exc}')
        result.apps.append(app)
        progress(index + 1, len(entries))
    result.cancelled = result.cancelled or cancel.is_set()
    return result


@dataclass
class CleanupResult:
    removed: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def cleanup_backups(selected, current_paths, cancel, progress=lambda done, total: None):
    """Only delete the exact files approved in the preview; continue after per-file errors."""
    result = CleanupResult()
    for index, (entry, backup) in enumerate(selected):
        if cancel.is_set():
            result.cancelled = True
            break
        try:
            delete_managed_backup(entry, backup.path, current_paths, backup.identity)
            result.removed.append((entry.id, backup.path))
        except (OSError, ValueError) as exc:
            result.errors.append(f'{entry.name} / {Path(backup.path).name}: {exc}')
        progress(index + 1, len(selected))
    return result
