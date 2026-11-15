"""Global preferences (Phase 5), stored in the ``settings`` key/value table.

Qt-free. Every getter validates and clamps, so a hand-edited or corrupt database value can never
break startup: it just falls back to the default.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .database import Database
from .updates.github import default_token

log = logging.getLogger(__name__)

KEY_TOKEN = "github_token"
KEY_AUTO_CHECK = "auto_check"
KEY_INTERVAL = "check_interval_hours"
KEY_NOTIFY = "notifications"
KEY_BACKGROUND = "run_in_background"

INTERVAL_CHOICES = (1, 3, 6, 12, 24)      # hours offered in the settings dialog
DEFAULT_INTERVAL = 6

# Stable keys distinguish badges that happen to share the same default color.
CARD_BADGES = {
    "appimage": ("AppImage", "accent"),
    "executable": ("Executable", "accent"),
    "up_to_date": ("Up to date", "ok"),
    "update_available": ("Update available", "update"),
    "checking": ("Checking for updates…", "muted"),
    "failed": ("Update failed", "danger"),
    "unavailable": ("Update info unavailable", "muted"),
    "no_source": ("No update source", "muted"),
    "prereleases": ("Pre-releases available", "muted"),
    "paused": ("Update paused", "paused"),
    "skipped": ("Version skipped", "muted"),
    "missing": ("File not found", "danger"),
    "not_executable": ("Not executable", "danger"),
}


def valid_badge_color(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


class AppSettings:
    def __init__(self, db: Database):
        self.db = db

    @property
    def card_badge_colors(self) -> dict[str, str]:
        """Only overrides are stored; absent/invalid values retain theme defaults."""
        try:
            values = json.loads(self.db.get_setting("card_badge_colors") or "{}")
        except (ValueError, TypeError):
            return {}
        if not isinstance(values, dict):
            return {}
        return {key: value.upper() for key, value in values.items()
                if key in CARD_BADGES and valid_badge_color(value)}

    @card_badge_colors.setter
    def card_badge_colors(self, values: dict[str, str]) -> None:
        if any(key not in CARD_BADGES or not valid_badge_color(value)
               for key, value in values.items()):
            raise ValueError("Badge colors must use a known badge and a #RRGGBB color.")
        self.db.set_setting("card_badge_colors", json.dumps(
            {key: value.upper() for key, value in values.items()}, sort_keys=True))

    # -- helpers ------------------------------------------------------------------------
    def _bool(self, key: str, default: bool) -> bool:
        raw = self.db.get_setting(key)
        return default if raw is None else raw == "1"

    def _set_bool(self, key: str, value: bool) -> None:
        self.db.set_setting(key, "1" if value else "0")

    @property
    def theme_mode(self) -> str:
        """Follow the desktop until the user explicitly chooses light or dark."""
        value = self.db.get_setting("theme_mode")
        return value if value in ("light", "dark") else "system"

    @theme_mode.setter
    def theme_mode(self, value: str) -> None:
        if value not in ("system", "light", "dark"):
            raise ValueError("Theme must be system, light or dark.")
        self.db.set_setting("theme_mode", value)

    # -- update checks ------------------------------------------------------------------
    @property
    def auto_check(self) -> bool:
        """Check for updates at startup and periodically while AppForge is running."""
        return self._bool(KEY_AUTO_CHECK, True)

    @auto_check.setter
    def auto_check(self, value: bool) -> None:
        self._set_bool(KEY_AUTO_CHECK, bool(value))

    @property
    def check_interval_hours(self) -> int:
        raw = self.db.get_setting(KEY_INTERVAL)
        try:
            hours = int(raw) if raw is not None else DEFAULT_INTERVAL
        except ValueError:
            return DEFAULT_INTERVAL
        return max(1, min(168, hours))

    @check_interval_hours.setter
    def check_interval_hours(self, hours: int) -> None:
        self.db.set_setting(KEY_INTERVAL, str(max(1, min(168, int(hours)))))

    @property
    def check_interval_seconds(self) -> float:
        return self.check_interval_hours * 3600.0

    # -- notifications / background -----------------------------------------------------
    @property
    def notifications(self) -> bool:
        return self._bool(KEY_NOTIFY, True)

    @notifications.setter
    def notifications(self, value: bool) -> None:
        self._set_bool(KEY_NOTIFY, bool(value))

    @property
    def run_in_background(self) -> bool:
        """Keep running in the system tray when the window is closed (default: off)."""
        return self._bool(KEY_BACKGROUND, False)

    @run_in_background.setter
    def run_in_background(self, value: bool) -> None:
        self._set_bool(KEY_BACKGROUND, bool(value))

    @property
    def start_at_login(self) -> bool:
        return self._bool("start_at_login", False)

    @start_at_login.setter
    def start_at_login(self, value: bool) -> None:
        self._set_bool("start_at_login", bool(value))

    @property
    def start_minimized(self) -> bool:
        return self._bool("start_minimized", False)

    @start_minimized.setter
    def start_minimized(self, value: bool) -> None:
        self._set_bool("start_minimized", bool(value))

    # -- GitHub token -------------------------------------------------------------------
    @property
    def github_token(self) -> str:
        """The token saved in AppForge ('' if none). See :meth:`effective_github_token`."""
        return (self.db.get_setting(KEY_TOKEN) or "").strip()

    @staticmethod
    def validate_github_token(token: str | None) -> str:
        token = (token or "").strip()
        if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("A GitHub token contains only visible ASCII characters, without spaces.")
        return token

    def set_github_token(self, token: str | None) -> None:
        token = self.validate_github_token(token)
        self.db.set_setting(KEY_TOKEN, token)
        if token:                      # the token is stored in clear text: at least keep the file private
            try:
                os.chmod(self.db.path, 0o600)
            except OSError:
                log.debug("Could not restrict permissions on %s", self.db.path, exc_info=True)

    def effective_github_token(self) -> str | None:
        """Token used for api.github.com: the one saved here, else GITHUB_TOKEN / GH_TOKEN."""
        return self.github_token or default_token()

    def token_source(self) -> str:
        """'settings', 'environment' or 'none' (for the settings dialog)."""
        if self.github_token:
            return "settings"
        return "environment" if default_token() else "none"


__all__ = ["AppSettings", "INTERVAL_CHOICES", "DEFAULT_INTERVAL"]
