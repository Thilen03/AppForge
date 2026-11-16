"""SQLite persistence. Application *metadata* lives here; app files are never touched."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import AppEntry, UpdateStatus

# Each migration brings the schema from version N to N+1. Append new ones; never edit old ones.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE apps (
        id                 TEXT PRIMARY KEY,
        name               TEXT NOT NULL,
        path               TEXT NOT NULL,
        format             TEXT NOT NULL DEFAULT 'appimage',
        installed_version  TEXT,
        latest_version     TEXT,
        github_repo        TEXT,
        icon_path          TEXT,
        description        TEXT,
        last_update_check  REAL,
        update_status      TEXT NOT NULL DEFAULT 'unavailable',
        backup_info        TEXT NOT NULL DEFAULT '{}',
        metadata           TEXT NOT NULL DEFAULT '{}',
        added_at           REAL NOT NULL,
        updated_at         REAL NOT NULL
    );
    CREATE UNIQUE INDEX idx_apps_path ON apps(path);
    """,
    # v2 (Phase 3): small key/value store for global settings (e.g. backup retention).
    """
    CREATE TABLE settings (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL
    );
    """,
]

_COLUMNS = (
    "id", "name", "path", "format", "installed_version", "latest_version", "github_repo",
    "icon_path", "description", "last_update_check", "update_status", "backup_info",
    "metadata", "added_at", "updated_at",
)


class DuplicatePathError(Exception):
    """Raised when an application with the same file path is already in the library."""


def _row_to_entry(row: sqlite3.Row) -> AppEntry:
    try:
        status = UpdateStatus(row["update_status"])
    except ValueError:
        status = UpdateStatus.UNAVAILABLE
    return AppEntry(
        id=row["id"], name=row["name"], path=row["path"], format=row["format"],
        installed_version=row["installed_version"], latest_version=row["latest_version"],
        github_repo=row["github_repo"], icon_path=row["icon_path"],
        description=row["description"], last_update_check=row["last_update_check"],
        update_status=status,
        backup_info=json.loads(row["backup_info"] or "{}"),
        metadata=json.loads(row["metadata"] or "{}"),
        added_at=row["added_at"], updated_at=row["updated_at"],
    )


def _entry_to_params(e: AppEntry) -> tuple:
    return (
        e.id, e.name, e.path, e.format, e.installed_version, e.latest_version, e.github_repo,
        e.icon_path, e.description, e.last_update_check, e.update_status.value,
        json.dumps(e.backup_info), json.dumps(e.metadata), e.added_at, e.updated_at,
    )


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for i in range(version, len(MIGRATIONS)):
            with self._conn:
                self._conn.executescript(MIGRATIONS[i])
                self._conn.execute(f"PRAGMA user_version = {i + 1}")

    def close(self) -> None:
        self._conn.close()

    # -- CRUD ---------------------------------------------------------------------------
    def add(self, entry: AppEntry) -> AppEntry:
        placeholders = ",".join("?" * len(_COLUMNS))
        try:
            with self._conn:
                self._conn.execute(
                    f"INSERT INTO apps ({','.join(_COLUMNS)}) VALUES ({placeholders})",
                    _entry_to_params(entry),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicatePathError(entry.path) from exc
        return entry

    def update(self, entry: AppEntry) -> AppEntry:
        entry.updated_at = time.time()
        assignments = ",".join(f"{c}=?" for c in _COLUMNS[1:])
        params = _entry_to_params(entry)
        try:
            with self._conn:
                self._conn.execute(
                    f"UPDATE apps SET {assignments} WHERE id=?", params[1:] + (entry.id,)
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicatePathError(entry.path) from exc
        return entry

    def delete(self, app_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM apps WHERE id=?", (app_id,))

    def get(self, app_id: str) -> AppEntry | None:
        row = self._conn.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
        return _row_to_entry(row) if row else None

    def find_by_path(self, path: str) -> AppEntry | None:
        row = self._conn.execute("SELECT * FROM apps WHERE path=?", (path,)).fetchone()
        return _row_to_entry(row) if row else None

    # -- global settings ----------------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def list_all(self) -> list[AppEntry]:
        rows = self._conn.execute("SELECT * FROM apps ORDER BY name COLLATE NOCASE").fetchall()
        return [_row_to_entry(r) for r in rows]
