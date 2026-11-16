"""Starting applications as fully detached processes."""
from __future__ import annotations

import logging
import os
import stat
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.envvars import env_of
from ..core.launch_options import TERMINAL, LaunchOptionsError, options_of, command_for, directory_for
from ..core.launch_profiles import DEFAULT_PROFILE, entry_for_profile
from ..core.library import FileState, file_state
from ..core.models import AppEntry
from ..core.paths import logs_dir

log = logging.getLogger(__name__)

# Variables set by AppImage runtimes / PyInstaller that must not leak into launched apps.
_LEAKY_VARS = ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "APPIMAGE_EXTRACT_AND_RUN",
               "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
               "QML2_IMPORT_PATH", "QML_IMPORT_PATH", "_MEIPASS2", "PYINSTALLER_RESET_ENVIRONMENT")


class LaunchError(Exception):
    def __init__(self, message: str, state: FileState | None = None):
        super().__init__(message)
        self.state = state


@dataclass
class LaunchHandle:
    process: subprocess.Popen
    log_path: Path

    def early_exit_code(self) -> int | None:
        """Exit code if the process has already ended, else None (still running)."""
        return self.process.poll()

    def log_tail(self, max_chars: int = 600) -> str:
        try:
            return self.log_path.read_text("utf-8", "replace")[-max_chars:].strip()
        except OSError:
            return ""


def clean_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for child processes: undo TuxShelf's own bundle/AppImage settings."""
    env = dict(os.environ if env is None else env)
    # PyInstaller saves the user's original value in *_ORIG before prepending its own.
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        orig = env.pop(f"{key}_ORIG", None)
        if orig is not None:
            env[key] = orig
        elif env.get("_TUXSHELF_BUNDLED") == "1":
            env.pop(key, None)
    for key in _LEAKY_VARS + ("_TUXSHELF_BUNDLED",):
        env.pop(key, None)
    return env


def make_executable(path: str | os.PathLike) -> None:
    p = Path(path)
    mode = p.stat().st_mode
    p.chmod(mode | stat.S_IXUSR | (stat.S_IXGRP if mode & stat.S_IRGRP else 0)
            | (stat.S_IXOTH if mode & stat.S_IROTH else 0))


def terminal_command(argv: list[str], env: dict[str, str]) -> list[str]:
    """Prefer the desktop terminal helper, then known terminals; never invoke a shell."""
    candidates = [("xdg-terminal-exec", [])]
    desktop = env.get("XDG_CURRENT_DESKTOP", "").lower()
    if "kde" in desktop:
        candidates.append(("konsole", ["-e"]))
    candidates += [("gnome-terminal", ["--"]), ("konsole", ["-e"]),
                   ("xfce4-terminal", ["-x"]), ("kitty", ["--"]),
                   ("alacritty", ["-e"]), ("foot", ["--"]), ("xterm", ["-e"])]
    for program, flags in candidates:
        executable = shutil.which(program, path=env.get("PATH", os.defpath))
        if executable:
            return [executable, *flags, *argv]
    raise LaunchError("No supported terminal was found. Install a terminal such as Konsole, "
                      "or turn off Run in terminal in Launch options.")


def launch(entry: AppEntry, profile_id: str = DEFAULT_PROFILE) -> LaunchHandle:
    try:
        entry = entry_for_profile(entry, profile_id)
    except LaunchOptionsError as exc:
        raise LaunchError(f"Invalid launch profile for “{entry.name}”: {exc}") from exc
    state = file_state(entry)
    if state is FileState.MISSING:
        raise LaunchError(f"The file for “{entry.name}” was not found:\n{entry.path}", state)
    if state is FileState.NOT_A_FILE:
        raise LaunchError(f"“{entry.path}” is not a file.", state)
    if state is FileState.NOT_EXECUTABLE:
        raise LaunchError(f"“{entry.name}” is not marked as executable.", state)

    try:
        options = options_of(entry)
        cmd = command_for(entry, options)
        directory = directory_for(entry, options)
    except LaunchOptionsError as exc:
        raise LaunchError(f"Invalid launch options for “{entry.name}”: {exc}") from exc
    try:
        directory_exists = Path(directory).is_dir()
    except OSError as exc:
        raise LaunchError(f"Could not access the working directory for “{entry.name}”: {exc}") from exc
    if not directory_exists:
        raise LaunchError(f"The working directory for “{entry.name}” was not found:\n{directory}\n"
                          "Choose another folder in Launch options, or leave it blank.")
    log_path = logs_dir() / f"{entry.id}.log"
    # the user's own variables go on top of the cleaned environment, so they always win
    env = {**clean_environment(), **env_of(entry)}
    if options.get(TERMINAL):
        cmd = terminal_command(cmd, env)
    try:
        with open(log_path, "wb") as logf:
            proc = subprocess.Popen(  # noqa: S603 - the user explicitly asked to run this file
                cmd,
                cwd=directory,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # survives TuxShelf closing
            )
    except OSError as exc:
        raise LaunchError(f"Could not start “{entry.name}”: {exc.strerror or exc}") from exc
    return LaunchHandle(proc, log_path)
