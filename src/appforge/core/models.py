"""Plain data model shared by every layer."""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class UpdateStatus(str, enum.Enum):
    """Update states from the specification. Phase 1 only ever uses UNAVAILABLE."""

    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    CHECKING = "checking"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class AppEntry:
    """One managed application. Mirrors the ``apps`` table."""

    name: str
    path: str
    format: str = "appimage"
    id: str = field(default_factory=new_id)
    installed_version: str | None = None
    latest_version: str | None = None  # Phase 2
    github_repo: str | None = None
    icon_path: str | None = None
    description: str | None = None
    last_update_check: float | None = None  # Phase 2
    update_status: UpdateStatus = UpdateStatus.UNAVAILABLE
    backup_info: dict[str, Any] = field(default_factory=dict)  # Phase 3
    metadata: dict[str, Any] = field(default_factory=dict)
    added_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
