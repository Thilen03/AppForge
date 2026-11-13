"""Standalone executables: a single ELF binary or a script with a ``#!`` line.

Covers the many tools that are published as one file. Like the AppImage reader this never runs the
file: the name and version come from the file name, and there is no embedded icon (AppForge shows a
generated one, or the icon you pick in Edit).

Updates work when a release publishes the *raw* binary; releases that only contain archives
(``.tar.gz``, ``.zip``) or packages (``.deb``, ``.rpm``) are reported as "no matching file".
"""
from __future__ import annotations

import re
from pathlib import Path

from .appimage import appimage_type, suggest_name_from_filename, version_from_filename
from .base import AppFormat, AppMetadata, FormatError

_SUFFIXES = re.compile(r"\.(sh|bash|py|pl|rb|run|bin|x86_64|x64|amd64|appimage)$", re.IGNORECASE)


def executable_kind(path: Path) -> str | None:
    """``"elf"``, ``"script"`` or ``None``. AppImages are *not* reported here."""
    try:
        if not path.is_file():
            return None
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return None
    if head == b"\x7fELF":
        return None if appimage_type(path) is not None else "elf"
    if head[:2] == b"#!":
        return "script"
    return None


def _strip(filename: str) -> str:
    prev = None
    while prev != filename:           # "tool.sh", "tool-linux.x86_64.bin" ...
        prev, filename = filename, _SUFFIXES.sub("", filename)
    return filename


class ExecutableFormat(AppFormat):
    id = "executable"
    display_name = "Executable"

    def detect(self, path: Path) -> bool:
        return executable_kind(path) is not None

    def extract_metadata(self, path: Path) -> AppMetadata:
        kind = executable_kind(path)
        if kind is None:
            raise FormatError("This file is not an executable program or script.")
        stem = _strip(path.name)
        version = version_from_filename(stem)
        return AppMetadata(
            format_id=self.id,
            name_suggestion=suggest_name_from_filename(stem) or path.name,
            version=version,
            extra={"executable_kind": kind, "version_source": "filename" if version else None},
            warnings=[] if version else ["The version isn't part of the file name; set it in Edit "
                                         "if you want update checks."])
