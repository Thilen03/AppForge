"""Format abstraction. Each executable format (AppImage, later others) implements AppFormat."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class FormatError(Exception):
    """The file is not usable for this format (message is user-presentable)."""


@dataclass
class AppMetadata:
    """Everything we could learn from inside an application file."""

    format_id: str
    name_suggestion: str
    version: str | None = None
    description: str | None = None
    icon_data: bytes | None = None
    icon_ext: str | None = None  # "png", "svg", "xpm"
    extra: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class AppFormat(abc.ABC):
    """Strategy object for one application format."""

    id: str = ""
    display_name: str = ""

    @abc.abstractmethod
    def detect(self, path: Path) -> bool:
        """Return True if ``path`` is an application of this format."""

    @abc.abstractmethod
    def extract_metadata(self, path: Path) -> AppMetadata:
        """Read name, version, icon … from the file. Must not execute the application."""

    def launch_command(self, path: Path) -> list[str]:
        """Command line used to start the application."""
        return [str(path)]

    # Future phases hook in here (kept as documentation, not implemented):
    #   update_provider_for(entry) -> UpdateProvider      (Phase 2)
    #   backup_dir_for(entry) -> Path                     (Phase 3)
