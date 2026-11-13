"""Desktop notifications without any Qt dependency (Phase 5).

``send_desktop_notification`` uses ``notify-send`` (libnotify) when it is installed. The UI prefers
the system-tray balloon when a tray icon is visible and falls back to this.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Iterable

from ..core.models import AppEntry
from .launcher import clean_environment

log = logging.getLogger(__name__)
MAX_NAMES = 4


def _plain(text: str, limit: int) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def summarize_updates(entries: Iterable[AppEntry]) -> tuple[str, str]:
    """(title, body) for "these apps have updates"."""
    items = list(entries)
    if len(items) == 1:
        e = items[0]
        title = f"Update available for {_plain(e.name, 60)}"
        body = (f"{_plain(e.installed_version or 'installed version unknown', 40)}  →  "
                f"{_plain(e.latest_version or '?', 40)}")
        return title, body
    title = f"{len(items)} application updates available"
    lines = [f"{_plain(e.name, 40)}  {_plain(e.latest_version or '', 30)}".rstrip() for e in items[:MAX_NAMES]]
    if len(items) > MAX_NAMES:
        lines.append(f"and {len(items) - MAX_NAMES} more")
    return title, "\n".join(lines)


def send_desktop_notification(title: str, body: str, icon: str = "appforge",
                              timeout_ms: int = 10000) -> bool:
    """Show a notification via ``notify-send``; False if unavailable or it failed."""
    exe = shutil.which("notify-send")
    if not exe:
        return False
    try:
        result = subprocess.run(  # noqa: S603 - fixed program, text passed as plain arguments
            [exe, "--app-name=AppForge", f"--icon={icon}", f"--expire-time={int(timeout_ms)}",
             "--", _plain(title, 100), _plain(body, 400)],
            env=clean_environment(), timeout=5, check=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        log.debug("notify-send failed", exc_info=True)
        return False
    return result.returncode == 0
