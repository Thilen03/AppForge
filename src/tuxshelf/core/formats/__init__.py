"""Format registry. Add new formats by instantiating them in ``FORMATS``."""
from __future__ import annotations

from pathlib import Path

from .appimage import AppImageFormat
from .base import AppFormat, AppMetadata, FormatError
from .executable import ExecutableFormat

# Order matters for detection: AppImage first, the generic executable format last.
FORMATS: list[AppFormat] = [AppImageFormat(), ExecutableFormat()]


def get_format(format_id: str) -> AppFormat | None:
    return next((f for f in FORMATS if f.id == format_id), None)


def detect_format(path: Path) -> AppFormat | None:
    return next((f for f in FORMATS if f.detect(path)), None)


__all__ = ["FORMATS", "AppFormat", "AppMetadata", "FormatError", "get_format", "detect_format"]
