"""A desktop entry for AppForge itself, so the desktop can pin it to the taskbar / dock.

KDE Plasma (and GNOME) only offer "Pin to Task Manager" for a running window if the window can be
matched to an installed ``.desktop`` file. AppForge sets its application id to ``appforge``
(``QGuiApplication.setDesktopFileName``), so this module makes sure ``appforge.desktop`` exists in
the user's applications directory and points at the file that is currently running – also after the
AppImage was moved. Qt-free.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import APP_DISPLAY_NAME, APP_ID
from .desktop.service import quote_exec_arg
from .paths import applications_dir, data_dir

log = logging.getLogger(__name__)
SELF_MARKER = "X-AppForge-Self=true"
ENTRY_NAME = f"{APP_ID}.desktop"


def self_exec_argv() -> list[str]:
    """The command that starts this very AppForge installation."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return [appimage]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    src = str(Path(__file__).resolve().parents[2])          # the folder that contains the package
    return ["env", f"PYTHONPATH={src}", sys.executable, "-m", APP_ID]


def render_self_entry(argv: list[str], icon: str) -> str:
    exec_line = " ".join(quote_exec_arg(a) for a in argv)
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        f"Name={APP_DISPLAY_NAME}",
        "GenericName=AppImage Manager",
        "Comment=Library, launcher and updater for AppImages and other standalone apps",
        f"Exec={exec_line}",
        f"Icon={icon}",
        "Terminal=false",
        "Categories=Utility;System;",
        f"StartupWMClass={APP_ID}",
        SELF_MARKER,
        "",
    ])


def _install_icon(source: str | None) -> str:
    """Copy the icon out of the (possibly temporary) bundle; return the path to put in ``Icon=``."""
    if not source or not os.path.isfile(source):
        return "application-x-executable"
    dest = data_dir() / f"{APP_ID}.png"
    try:
        if not dest.is_file() or dest.stat().st_size != os.path.getsize(source):
            shutil.copyfile(source, dest)
        return str(dest)
    except OSError:
        log.debug("Could not copy the icon", exc_info=True)
        return source


def ensure_self_launcher(icon_source: str | None = None, directory: str | os.PathLike | None = None,
                         refresh: bool = False) -> bool:
    """Create/refresh ``appforge.desktop``. Returns True if the file was written.

    A file of that name that AppForge didn't create (no marker) is the user's own and is left alone.
    ``refresh`` asks KDE to rebuild its application cache so the entry is usable immediately.
    """
    if os.environ.get("APPFORGE_NO_SELF_LAUNCHER"):
        return False
    target_dir = Path(directory) if directory else applications_dir()
    dest = target_dir / ENTRY_NAME
    content = render_self_entry(self_exec_argv(), _install_icon(icon_source))
    try:
        if dest.is_file():
            current = dest.read_text("utf-8", "replace")
            if SELF_MARKER not in current:
                return False
            if current == content:
                return False
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{ENTRY_NAME}.tmp")
        tmp.write_text(content, "utf-8")
        os.replace(tmp, dest)
    except OSError:
        log.warning("Could not write %s", dest, exc_info=True)
        return False
    if refresh:
        for tool in ("kbuildsycoca6", "kbuildsycoca5"):
            exe = shutil.which(tool)
            if exe:
                try:
                    subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
                except OSError:
                    pass
                break
    return True
