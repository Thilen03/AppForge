"""AppForge's own update: check the AppForge GitHub repository, download the new AppImage, swap it in.

Qt-free and safe on a worker thread.  The heavy lifting (download to a temp file next to the
AppImage, validation, SHA-256 check, backup of the old build, atomic replace) is the same code that
updates the apps in the library (``core.updates.installer``).
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import APP_REPO_URL, __version__
from .updates.assets import choose_asset
from .updates.github import GitHubError
from .updates.installer import InstallError, InstallResult, backup_dir_for, install_update
from .updates.providers import client_for, parse_source
from .updates.version import compare, display_version

log = logging.getLogger(__name__)
KEEP_BACKUPS = 2          # old AppForge builds kept next to the AppImage


@dataclass
class SelfUpdate:
    version: str            # newest version found, e.g. "0.5.3"
    url: str                # release page to open
    notes: str = ""
    asset: dict | None = None                         # the AppImage to download (None: nothing suitable)
    assets: list[dict] = field(default_factory=list)  # every release file (for checksum lookup)


def check_self_update(client=None, token: str | None = None, current: str = __version__) -> SelfUpdate | None:
    """The newest stable release if it is newer than ``current``; ``None`` if up to date or on any error."""
    ref = parse_source(APP_REPO_URL)
    if ref is None:
        return None
    try:
        releases = (client or client_for(ref, token)).releases(ref.owner, ref.name)
    except GitHubError:
        return None
    for rel in releases:                      # newest first
        if rel.draft or rel.prerelease:
            continue
        latest = display_version(rel.tag)
        if compare(latest, current) != 1:
            return None
        current_name = Path(appimage_path() or "AppForge.AppImage").name
        choice = choose_asset(rel, current_filename=current_name, app_name="AppForge")
        return SelfUpdate(latest, rel.html_url or f"{APP_REPO_URL}/releases/latest",
                          asset=choice.asset.to_dict() if choice else None,
                          assets=[a.to_dict() for a in rel.assets])
    return None


def appimage_path() -> Path | None:
    """The AppImage this process was started from (``$APPIMAGE``), if it still exists."""
    p = os.environ.get("APPIMAGE")
    return Path(p) if p and os.path.isfile(p) else None


def install_blocker(update: SelfUpdate) -> str | None:
    """Why AppForge can't update itself in place (``None`` = it can)."""
    target = appimage_path()
    if target is None:
        return "AppForge isn't running from an AppImage, so it can't replace itself."
    if update.asset is None:
        return "The release has no AppImage for this computer."
    if not os.access(target.parent, os.W_OK):
        return f"AppForge can't write to {target.parent}."
    return None


def prune_backups(target: Path, keep: int = KEEP_BACKUPS) -> None:
    """Delete all but the newest ``keep`` old AppForge builds from the hidden backups folder."""
    folder = backup_dir_for(target)
    try:
        files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".appimage"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            log.debug("Couldn't delete old backup %s", old, exc_info=True)


def install_self_update(update: SelfUpdate, progress: Callable[[int, int], None] | None = None,
                        cancel: threading.Event | None = None) -> InstallResult:
    """Download and swap in the new AppImage.  Raises ``InstallError`` (the old build is untouched)."""
    reason = install_blocker(update)
    if reason:
        raise InstallError(reason)
    target = appimage_path()
    assert target is not None and update.asset is not None
    result = install_update(target, update.asset, update.assets, old_version=__version__,
                            progress=progress, cancel=cancel, format_id="appimage")
    prune_backups(target)
    return result


def relaunch(path: str | os.PathLike) -> bool:
    """Start a fresh AppForge (call *after* releasing the single-instance guard)."""
    from ..services.launcher import clean_environment
    try:
        subprocess.Popen([str(path)], env=clean_environment(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        log.warning("Couldn't restart AppForge", exc_info=True)
        return False
