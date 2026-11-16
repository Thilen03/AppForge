"""Find a likely new home for an application file that has gone missing (moved or renamed).

Pure filesystem logic, no database and no Qt. A candidate is an AppImage in one of the searched
folders whose *identity key* matches the library entry's: the file name with version numbers,
architecture and the ``.AppImage`` suffix stripped, lower-cased, so ``Foo-Bar-1.2-x86_64.AppImage``
and ``foo_bar.AppImage`` are both ``foobar``. Folders are scanned one level deep only.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from .formats import detect_format
from .models import AppEntry

MAX_CANDIDATES = 5
MAX_SCAN_PER_DIR = 5000

_ARCH = re.compile(
    r"(?<![a-z0-9])(x86[_-]64|x64|amd64|aarch64|arm64|armv7l|armhf|i[3-6]86|linux|appimage)(?![a-z0-9])",
    re.IGNORECASE)
_VERSIONISH = re.compile(
    r"^(v?\d[\w+~]*|r\d+|build\d*|latest|stable|nightly|continuous|(?=.*\d)[0-9a-f]{7,40})$",
    re.IGNORECASE)


def identity_key(text: str) -> str:
    """Name with versions/architecture/suffix removed; ``""`` if nothing identifying is left."""
    stem = re.sub(r"\.appimage$", "", text, flags=re.IGNORECASE)
    stem = _ARCH.sub(" ", stem)
    parts = [t for t in re.split(r"[\s._+-]+", stem) if t]
    # the first word is always part of the name ("7zip", "1Password"); later numeric words are versions
    tokens = [t for i, t in enumerate(parts) if i == 0 or not _VERSIONISH.match(t)]
    return "".join(tokens).lower()


def default_search_dirs() -> list[Path]:
    home = Path.home()
    return [home / "Applications", home / "AppImages", home / "Downloads", home / "Desktop",
            home / ".local" / "bin", home / "bin", Path("/opt")]


def find_candidates(entry: AppEntry, extra_dirs: Iterable[str | os.PathLike] = (),
                    exclude: Iterable[str | os.PathLike] = (),
                    include_defaults: bool = True) -> list[Path]:
    """AppImages that look like ``entry``'s file at a new location, best match first.

    ``extra_dirs`` are searched after the entry's own (old) folder and before the defaults;
    ``exclude`` holds paths that already belong to other library entries.
    """
    keys = {k for k in (identity_key(Path(entry.path).name), identity_key(entry.name)) if k}
    if not keys:
        return []
    skip = {os.path.abspath(p) for p in exclude} | {os.path.abspath(entry.path)}
    dirs: list[Path] = [Path(entry.path).parent, *(Path(d) for d in extra_dirs)]
    if include_defaults:
        dirs += default_search_dirs()

    seen_dirs: set[str] = set()
    hits: list[tuple[int, float, Path]] = []
    for rank, d in enumerate(dirs):
        key = os.path.abspath(d)
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for n, de in enumerate(it):
                if n >= MAX_SCAN_PER_DIR:
                    break
                name = de.name
                if name.startswith(".") or not name.lower().endswith(".appimage"):
                    continue
                path = os.path.abspath(de.path)
                if path in skip or identity_key(name) not in keys:
                    continue
                try:
                    if not de.is_file():
                        continue
                    mtime = de.stat().st_mtime
                except OSError:
                    continue
                if detect_format(Path(path)) is None:
                    continue
                hits.append((rank, -mtime, Path(path)))
    hits.sort(key=lambda h: (h[0], h[1]))
    out: list[Path] = []
    for _, _, p in hits:
        if p not in out:
            out.append(p)
    return out[:MAX_CANDIDATES]


__all__ = ["find_candidates", "identity_key", "default_search_dirs"]
