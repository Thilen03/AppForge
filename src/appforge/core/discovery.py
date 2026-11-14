"""Read-only discovery of portable apps. No Qt, database writes, or subprocesses."""
from __future__ import annotations

import json
import os
import stat
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .formats import AppMetadata, detect_format
from .library import LibraryError, LibraryService, inspect_file, normalize_path

ROOTS_KEY = "discovery_roots"
IGNORED_KEY = "discovery_ignored"


def default_roots() -> list[str]:
    return [str(Path.home() / "Applications"), str(Path.home() / "Downloads"), "/opt"]


def load_paths(db, key: str, default: list[str] | None = None) -> list[str]:
    try:
        values = json.loads(db.get_setting(key) or "null")
        if isinstance(values, list) and all(isinstance(p, str) and p.strip() for p in values):
            return list(dict.fromkeys(normalize_path(p) for p in values))
    except (ValueError, TypeError):
        pass
    return list(default or [])


def save_paths(db, key: str, paths: Iterable[str]) -> None:
    db.set_setting(key, json.dumps(list(dict.fromkeys(normalize_path(p) for p in paths))))


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _backup_dir(path: Path) -> bool:
    return path.name.startswith(".") and path.name.endswith(".backups")


def _safe_path(path: Path) -> bool:
    # Reject links in ancestors as well as the final component, including scan roots.
    return not any(p.is_symlink() or _backup_dir(p) for p in (path, *path.parents))


@dataclass
class Candidate:
    path: str
    metadata: AppMetadata
    signature: tuple[int, int, int, int]
    registered: bool = False
    ignored: bool = False


@dataclass
class ScanResult:
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    visited: int = 0
    cancelled: bool = False


def scan(roots: Iterable[str], registered: Iterable[str] = (), ignored: Iterable[str] = (),
         cancel: threading.Event | None = None,
         progress: Callable[[int, str], None] | None = None) -> ScanResult:
    """Recursively inspect only chosen roots. All symlinks are deliberately skipped."""
    result = ScanResult()
    cancel = cancel or threading.Event()
    known_paths = {normalize_path(p) for p in registered}
    ignored_paths = {normalize_path(p) for p in ignored}
    known_ids = set()
    for p in known_paths:
        try:
            known_ids.add(_identity(os.stat(p)))
        except OSError:
            pass
    seen_files, seen_dirs = set(), set()

    def report(path, exc):
        # Avoid retaining unbounded errors in very large inaccessible trees.
        if len(result.errors) < 100:
            result.errors.append(f"{path}: {exc}")

    def visit(directory: Path):
        if cancel.is_set() or not _safe_path(directory):
            return
        try:
            info = directory.stat()
            if not stat.S_ISDIR(info.st_mode):
                return
            identity = _identity(info)
            if identity in seen_dirs:
                return
            seen_dirs.add(identity)
            with os.scandir(directory) as entries:
                for item in entries:
                    if cancel.is_set():
                        break
                    path = Path(item.path)
                    try:
                        if item.is_symlink():
                            continue
                        if item.is_dir(follow_symlinks=False):
                            if not _backup_dir(path):
                                visit(path)
                            continue
                        info = item.stat(follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        identity = _identity(info)
                        if identity in seen_files:
                            continue
                        seen_files.add(identity)
                        result.visited += 1
                        if progress and (result.visited == 1 or result.visited % 25 == 0):
                            progress(result.visited, str(path))
                        fmt = detect_format(path)
                        if fmt is None or (fmt.id != "appimage" and not os.access(path, os.X_OK)):
                            continue
                        md = inspect_file(path)
                        if _signature(path.stat()) != _signature(info) or not _safe_path(path):
                            report(path, "File changed during inspection; scan again.")
                            continue
                        norm = normalize_path(path)
                        result.candidates.append(Candidate(norm, md, _signature(info),
                            norm in known_paths or identity in known_ids, norm in ignored_paths))
                    except (OSError, LibraryError) as exc:
                        report(path, exc)
        except (OSError, RecursionError) as exc:
            report(directory, exc)

    for root in dict.fromkeys(normalize_path(p) for p in roots):
        if cancel.is_set():
            break
        path = Path(root)
        if not _safe_path(path):
            report(path, "Symlink paths and backup folders are excluded.")
            continue
        visit(path)
    result.cancelled = cancel.is_set()
    if progress:
        progress(result.visited, "")
    return result


def import_candidate(library: LibraryService, candidate: Candidate, *, integrate_desktop=False):
    """Register a confirmed result through the existing service; never change the app file."""
    path = Path(candidate.path)
    try:
        info = path.stat()
        if not _safe_path(path) or not stat.S_ISREG(info.st_mode):
            raise LibraryError("The discovered file is no longer a regular, non-symlink file.")
        if _signature(info) != candidate.signature:
            raise LibraryError("The discovered file has changed. Scan again before importing it.")
        if candidate.metadata.format_id != "appimage" and not os.access(path, os.X_OK):
            raise LibraryError("The discovered program is no longer executable.")
        for entry in library.list_applications():
            if normalize_path(entry.path) == candidate.path:
                raise LibraryError("This application is already in your library.")
            try:
                if _identity(os.stat(entry.path)) == _identity(info):
                    raise LibraryError("This file is already registered at another location.")
            except OSError:
                pass
    except OSError as exc:
        raise LibraryError(f"Couldn't read the discovered file: {exc}") from exc
    return library.add_application(candidate.path, metadata=candidate.metadata,
                                   integrate_desktop=integrate_desktop)
