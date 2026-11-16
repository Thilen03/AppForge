"""Filesystem locations used by TuxShelf (XDG-compliant, overridable for tests)."""
from __future__ import annotations

import os
from pathlib import Path

from .. import APP_ID
from .compat import LEGACY_ID, environment


def data_dir() -> Path:
    """Return (and create) the per-user data directory.

    ``TUXSHELF_DATA_DIR`` overrides the location; used by tests and for portable setups.
    """
    override = environment("DATA_DIR")
    if override:
        base = Path(override).expanduser()
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        parent = Path(xdg) if xdg else Path.home() / ".local" / "share"
        base = parent / APP_ID
        legacy = parent / LEGACY_ID
        # Reuse the library in place: stored icon and backup paths stay valid,
        # and a running earlier version keeps sharing its database and lock.
        if not (base / "library.db").exists() and (legacy / "library.db").is_file():
            base = legacy
    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    return data_dir() / "library.db"


def icons_dir() -> Path:
    p = data_dir() / "icons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def applications_dir() -> Path:
    """Where the per-user ``.desktop`` launchers go (the XDG ``applications`` directory).

    Resolution order: ``TUXSHELF_APPLICATIONS_DIR`` (explicit override); ``<TUXSHELF_DATA_DIR>/applications``
    when a throw-away data dir is in use (tests, portable setups – so they never touch the real menu);
    otherwise ``$XDG_DATA_HOME/applications`` (default ``~/.local/share/applications``).

    The directory is *not* created here; ``DesktopService`` creates it when it first writes.
    """
    explicit = environment("APPLICATIONS_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if environment("DATA_DIR"):
        return data_dir() / "applications"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "applications"
