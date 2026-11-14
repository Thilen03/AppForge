"""Read-only filesystem details. Receives a snapshot, never a database connection."""
from dataclasses import dataclass
from pathlib import Path
import os
import stat

from .backups.service import scan_backup_records
from .models import AppEntry


@dataclass
class FileDetails:
    size: int | None = None
    state: str = "Unavailable"
    backup_count: int | None = None
    backup_size: int | None = None
    backup_date: float | None = None
    backup_error: str = ""


def inspect_details(entry: AppEntry) -> FileDetails:
    result = FileDetails()
    try:
        info = Path(entry.path).stat()
        if stat.S_ISREG(info.st_mode):
            result.size = info.st_size
            result.state = "Ready" if os.access(entry.path, os.X_OK) else "Not executable"
        else:
            result.state = "Not a regular file"
    except FileNotFoundError:
        result.state = "File missing"
    except OSError:
        result.state = "File unavailable (check permissions)"
    try:
        records = scan_backup_records(entry)
        sizes, dates = [], []
        for record in records:
            try:
                sizes.append(Path(record["file"]).stat().st_size)
                dates.append(float(record.get("created") or 0))
            except FileNotFoundError:
                continue
        result.backup_count = len(sizes)
        result.backup_size = sum(sizes)
        result.backup_date = max(dates, default=0) or None
    except (OSError, ValueError, TypeError, KeyError):
        result.backup_error = "Backup information unavailable; refresh to try again."
    return result
