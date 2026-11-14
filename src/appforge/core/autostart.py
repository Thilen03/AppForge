"""Manage AppForge's per-user XDG desktop autostart entry."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from .desktop.selflauncher import self_exec_path
from .desktop.service import quote_exec_arg
from .selfintegration import self_exec_argv

MARKER = "X-AppForge-Autostart=true"


class AutostartError(Exception):
    """A user-visible startup configuration problem."""


def entry_path() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config.is_absolute():
        config = Path.home() / ".config"
    return config / "autostart" / "appforge.desktop"


def startup_command() -> list[str]:
    exe = self_exec_path()
    if exe is not None:
        return [str(exe)]
    if getattr(sys, "frozen", False):
        raise AutostartError("Could not find a permanent AppForge executable. Run the AppImage from its saved location first.")
    return self_exec_argv()


def render_entry(command: list[str]) -> str:
    if not command or any(any(ord(c) < 32 or ord(c) == 127 for c in arg) for arg in command):
        raise AutostartError("The AppForge startup command contains an unsupported control character.")
    command = [*command, "--autostart"]
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=AppForge",
        "Comment=Start AppForge at login",
        "Exec=" + " ".join(quote_exec_arg(arg) for arg in command),
        "Icon=appforge", "Terminal=false", "StartupNotify=false", MARKER, "",
    ])


def set_enabled(enabled: bool) -> None:
    """Create/refresh or remove only our own regular entry; never follow a symlink."""
    dest = entry_path()
    try:
        if dest.is_symlink():
            raise AutostartError(f"Startup entry is a symbolic link; it was left unchanged: {dest}")
        current = None
        if dest.exists():
            if not dest.is_file():
                raise AutostartError(f"Startup entry is not a regular file: {dest}")
            current = dest.read_text("utf-8")
            if MARKER not in current.splitlines():
                if enabled:
                    raise AutostartError(f"A startup entry not managed by AppForge already exists: {dest}")
                return
        if not enabled:
            if current is not None:
                dest.unlink()
            return
        text = render_entry(startup_command())
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
        raise AutostartError(f"Could not update the startup entry: {exc}") from exc
