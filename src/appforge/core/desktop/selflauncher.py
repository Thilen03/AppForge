"""AppForge's own application-menu launcher (``appforge.desktop``).

A desktop environment can only offer "Pin to Task Manager" for a window it can match to a
``.desktop`` file.  A bare AppImage has none, so AppForge writes one for itself, pointing at the
AppImage that is running right now.  It is rewritten at every start, so moving or renaming the
AppImage (or updating AppForge) never breaks an existing pin.

The file name is ``appforge.desktop`` - the same as ``QGuiApplication.setDesktopFileName("appforge")``
and the window's ``StartupWMClass`` - which is what makes the match work on both X11 and Wayland.
(It can't collide with the per-app ``appforge-<id>.desktop`` launchers: those are never managed here.)
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from pathlib import Path

from ... import APP_DISPLAY_NAME, APP_ID
from ..paths import applications_dir, data_dir
from .service import _escape_value, quote_exec_arg

log = logging.getLogger(__name__)
SELF_FILENAME = f"{APP_ID}.desktop"
SELF_MARKER = "X-AppForge-Self"


def self_exec_path() -> Path | None:
    """The file that starts this AppForge: the AppImage, or the frozen executable. None when run from source."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return Path(appimage).resolve()
    if getattr(sys, "frozen", False) and not os.environ.get("APPDIR"):
        exe = Path(sys.executable)
        return exe.resolve() if exe.is_file() else None
    return None


def render_self_entry(exec_path: str | os.PathLike, icon: str | os.PathLike | None) -> str:
    exe = str(exec_path)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_DISPLAY_NAME}",
        "GenericName=Application Manager",
        "Comment=Library and launcher for AppImages",
        f"Exec={quote_exec_arg(exe)} %F",
        f"TryExec={_escape_value(exe)}",
    ]
    if icon:
        lines.append(f"Icon={_escape_value(str(icon))}")
    lines += [
        "Terminal=false",
        "Categories=System;Utility;",
        "Keywords=AppImage;launcher;apps;",
        "StartupNotify=true",
        f"StartupWMClass={APP_ID}",
        f"{SELF_MARKER}=true",
        "",
    ]
    return "\n".join(lines)


def _is_ours(path: Path) -> bool:
    try:
        return re.search(rf"^{SELF_MARKER}=true\s*$", path.read_text("utf-8"), re.M) is not None
    except OSError:
        return False


def ensure_self_launcher(icon_source: str | os.PathLike | None, exec_path: str | os.PathLike | None = None,
                         directory: str | os.PathLike | None = None) -> bool:
    """Create/refresh ``appforge.desktop``. True if the file was written.

    Never touches a ``appforge.desktop`` that AppForge didn't write itself, and never raises.
    """
    try:
        exe = Path(exec_path) if exec_path else self_exec_path()
        if exe is None:
            return False
        target_dir = Path(directory) if directory else applications_dir()
        dest = target_dir / SELF_FILENAME
        if dest.exists() and not _is_ours(dest):
            log.info("Leaving the existing %s alone (not written by AppForge)", dest)
            return False
        icon = None
        if icon_source and Path(icon_source).is_file():
            icon_dest = data_dir() / f"{APP_ID}.png"
            try:
                if not icon_dest.is_file() or icon_dest.stat().st_size != Path(icon_source).stat().st_size:
                    shutil.copyfile(icon_source, icon_dest)
                icon = icon_dest
            except OSError:
                icon = None
        text = render_self_entry(exe, icon)
        if dest.is_file() and dest.read_text("utf-8") == text:
            return False
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(text, "utf-8")
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return True
    except Exception:  # noqa: BLE001 - housekeeping must never block startup
        log.warning("Couldn't write AppForge's own launcher", exc_info=True)
        return False
