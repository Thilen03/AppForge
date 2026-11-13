"""Global preferences (Phase 5), stored in the ``settings`` key/value table.

Qt-free. Every getter validates and clamps, so a hand-edited or corrupt database value can never
break startup: it just falls back to the default.
"""
from __future__ import annotations

import logging
import os

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


class AppSettings:
    def __init__(self, db: Database):
        self.db = db

    # -- helpers ------------------------------------------------------------------------
    def _bool(self, key: str, default: bool) -> bool:
        raw = self.db.get_setting(key)
        return default if raw is None else raw == "1"

    def _set_bool(self, key: str, value: bool) -> None:
        self.db.set_setting(key, "1" if value else "0")

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

    # -- GitHub token -------------------------------------------------------------------
    @property
    def github_token(self) -> str:
        """The token saved in AppForge ('' if none). See :meth:`effective_github_token`."""
        return (self.db.get_setting(KEY_TOKEN) or "").strip()

    def set_github_token(self, token: str | None) -> None:
        token = (token or "").strip()
        if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("A GitHub token contains only visible ASCII characters, without spaces.")
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
