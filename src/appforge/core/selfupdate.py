"""AppForge's own update check (against the AppForge GitHub repository). Qt-free, safe on a worker thread."""
from __future__ import annotations

from dataclasses import dataclass

from .. import APP_REPO_URL, __version__
from .updates.github import GitHubError
from .updates.providers import client_for, parse_source
from .updates.version import compare, display_version


@dataclass
class SelfUpdate:
    version: str            # newest version found, e.g. "0.5.2"
    url: str                # release page to open
    notes: str = ""


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
        if compare(latest, current) == 1:
            return SelfUpdate(latest, rel.html_url or f"{APP_REPO_URL}/releases/latest")
        return None
    return None
