"""AppForge's own application-menu launcher (``appforge.desktop``).

A desktop environment can only offer "Pin to Task Manager" for a window it can match to a
``.desktop`` file.  A bare AppImage has none, so AppForge writes one for itself, pointing at the
AppImage that is running right now, once the user opts in. Startup checks for changed
AppImage locations; updating a shortcut to a new location requires user approval.

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
import tempfile
from pathlib import Path

from ... import APP_DISPLAY_NAME, APP_ID
from ..paths import applications_dir, data_dir
from .service import _escape_value, quote_exec_arg

log = logging.getLogger(__name__)
SELF_FILENAME = f"{APP_ID}.desktop"
SELF_MARKER = "X-AppForge-Self"


class SelfLauncherError(Exception):
    """A user-visible problem changing AppForge's own menu shortcut."""


def launcher_installed() -> bool:
    dest = applications_dir() / SELF_FILENAME
    return not dest.is_symlink() and dest.is_file() and _is_ours(dest)


def moved_appimage() -> tuple[str, str] | None:
    """Return (saved location, current AppImage) when our shortcut needs consent to repair.

    Read only: never execute a desktop command or rewrite the entry. Source launches
    have no AppImage move to report. Missing/foreign/symlink entries are not adopted.
    """
    if not os.environ.get("APPIMAGE") or not launcher_installed():
        return None
    current = self_exec_path()
    if current is None:
        return None
    try:
        values = dict(line.split("=", 1) for line in
                      (applications_dir() / SELF_FILENAME).read_text("utf-8").splitlines()
                      if "=" in line)
    except (OSError, UnicodeError):
        return None
    saved = values.get("TryExec", "").replace("\\\\", "\\")
    if saved:
        if saved == str(current):
            return None
        return saved, str(current)
    # Older entries without TryExec can still be compared without executing/parsing Exec.
    command = values.get("Exec", "")
    expected = quote_exec_arg(str(current))
    if command in (expected, expected + " %F"):
        return None
    return command or "Unknown location", str(current)


def set_enabled(enabled: bool) -> None:
    """Create/refresh or remove only our own regular launcher, without hiding errors."""
    dest = applications_dir() / SELF_FILENAME
    try:
        if dest.is_symlink():
            raise SelfLauncherError(f"The shortcut is a symbolic link and was left unchanged: {dest}")
        current = None
        if dest.exists():
            if not dest.is_file():
                raise SelfLauncherError(f"The shortcut is not a regular file: {dest}")
            current = dest.read_text("utf-8")
            if f"{SELF_MARKER}=true" not in current.splitlines():
                if enabled:
                    raise SelfLauncherError(f"A shortcut not managed by AppForge already exists: {dest}")
                return
        if not enabled:
            if current is not None:
                dest.unlink()
            return
        from ..autostart import startup_command, AutostartError
        try:
            command = startup_command()
        except AutostartError as exc:
            raise SelfLauncherError(str(exc)) from exc
        if any(any(ord(c) < 32 or ord(c) == 127 for c in arg) for arg in command):
            raise SelfLauncherError("The launcher command contains an unsupported control character.")
        icon_source = Path(__file__).resolve().parents[2] / "resources" / "appforge.png"
        icon = None
        if icon_source.is_file():
            icon = data_dir() / f"{APP_ID}.png"
            if not icon.is_file() or icon.read_bytes() != icon_source.read_bytes():
                shutil.copyfile(icon_source, icon)
        executable = sys.executable if command[0] == "env" else command[0]
        text = render_self_entry(executable, icon, command=command)
        if current == text:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dest.parent,
                                             prefix=".appforge-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            temporary.chmod(0o644)
            os.replace(temporary, dest)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (OSError, UnicodeError) as exc:
        raise SelfLauncherError(f"Could not update the AppForge shortcut: {exc}") from exc


def self_exec_path() -> Path | None:
    """The file that starts this AppForge: the AppImage, or the frozen executable. None when run from source."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return Path(appimage).resolve()
    if getattr(sys, "frozen", False) and not os.environ.get("APPDIR"):
        exe = Path(sys.executable)
        return exe.resolve() if exe.is_file() else None
    return None


def render_self_entry(exec_path: str | os.PathLike, icon: str | os.PathLike | None,
                      *, command: list[str] | None = None) -> str:
    exe = str(exec_path)
    argv = command or [exe]
    exec_line = " ".join(quote_exec_arg(arg) for arg in argv)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_DISPLAY_NAME}",
        "GenericName=Application Manager",
        "Comment=Library and launcher for AppImages",
        f"Exec={exec_line} %F",
        f"TryExec={_escape_value(exe)}",
    ]
    if icon:
        lines.append(f"Icon={_escape_value(str(icon))}")
    lines += [
        "Terminal=false",
        "Categories=Utility;",
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
    except (OSError, UnicodeError):
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
