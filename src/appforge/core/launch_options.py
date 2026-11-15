"""Shared, shell-free launch configuration for AppForge and desktop launchers."""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from .formats import get_format

ARGUMENTS = "launch_arguments"
DIRECTORY = "launch_directory"
TERMINAL = "run_in_terminal"
LAUNCH_KEYS = frozenset((ARGUMENTS, DIRECTORY, TERMINAL))
MAX_ARGUMENT_TEXT = 8192
MAX_ARGUMENTS = 256


class LaunchOptionsError(ValueError):
    """A user-correctable launch configuration problem."""


def _text(value, label, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise LaunchOptionsError(f"{label} must be text of at most {limit} characters.")
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise LaunchOptionsError(f"{label} cannot contain control characters.")
    return value


def parse_arguments(text: str) -> list[str]:
    _text(text, "Arguments", MAX_ARGUMENT_TEXT)
    try:
        args = shlex.split(text, posix=True)
    except ValueError as exc:
        raise LaunchOptionsError(f"Invalid arguments: {exc}. Check your quotes and backslashes.") from exc
    if len(args) > MAX_ARGUMENTS:
        raise LaunchOptionsError(f"Use at most {MAX_ARGUMENTS} arguments.")
    return args


def validate_launch_options(options: dict) -> dict:
    if not isinstance(options, dict) or set(options) - LAUNCH_KEYS:
        raise LaunchOptionsError("Unsupported launch options.")
    arguments = _text(options.get(ARGUMENTS, ""), "Arguments", MAX_ARGUMENT_TEXT).strip()
    parse_arguments(arguments)
    directory = _text(options.get(DIRECTORY, ""), "Working directory", 4096).strip()
    if directory:
        directory = os.path.expanduser(directory)
        if not os.path.isabs(directory):
            raise LaunchOptionsError("Choose an absolute working-directory path, or leave it blank.")
        directory = os.path.normpath(directory)
    terminal = options.get(TERMINAL, False)
    if type(terminal) is not bool:
        raise LaunchOptionsError("Run in terminal must be true or false.")
    return {key: value for key, value in ((ARGUMENTS, arguments), (DIRECTORY, directory),
                                        (TERMINAL, terminal)) if value}


def options_of(entry) -> dict:
    return validate_launch_options({k: v for k, v in entry.metadata.items() if k in LAUNCH_KEYS})


def command_for(entry, options: dict) -> list[str]:
    fmt = get_format(entry.format)
    argv = fmt.launch_command(Path(entry.path)) if fmt else [entry.path]
    return [*argv, *parse_arguments(options.get(ARGUMENTS, ""))]


def directory_for(entry, options: dict) -> str:
    return options.get(DIRECTORY) or str(Path(entry.path).parent)
