"""Stable identifiers needed to read installations created before the rename.

Keep the former name here only for on-disk compatibility, never for new branding.
"""
from __future__ import annotations

import os
from pathlib import Path

LEGACY_ID = "appforge"
LEGACY_NAME = "AppForge"


def environment(suffix: str) -> str | None:
    """The current override wins; an earlier portable setup remains usable."""
    return os.environ.get(f"TUXSHELF_{suffix}") or os.environ.get(
        f"{LEGACY_ID.upper()}_{suffix}")


def instance_id(directory: Path) -> str:
    """Share the old instance guard when opening an existing installation."""
    if directory.name == LEGACY_ID or (directory / f"{LEGACY_ID}.lock").exists():
        return LEGACY_ID
    return "tuxshelf"


def owned_file(path: Path, *markers: str) -> bool:
    """Compatibility must never adopt a symlink or somebody else's entry."""
    if path.is_symlink() or not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return any(marker in lines for marker in markers)
    except (OSError, UnicodeError):
        return False
