"""Local tray shortcut preferences; no schema changes or executable inspection."""
from __future__ import annotations

import json

FAVORITES_KEY = "tray_favorites"
RECENT_KEY = "tray_recent"
RECENT_LIMIT = 8


class TrayShortcuts:
    def __init__(self, db):
        self.db = db

    def _read(self, key):
        try:
            values = json.loads(self.db.get_setting(key) or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        return list(dict.fromkeys(v for v in values if isinstance(v, str) and v))

    @property
    def favorites(self):
        return self._read(FAVORITES_KEY)

    @property
    def recent(self):
        return self._read(RECENT_KEY)[:RECENT_LIMIT]

    def set_favorite(self, app_id, enabled):
        ids = [i for i in self.favorites if i != app_id]
        if enabled:
            ids.append(app_id)
        self.db.set_setting(FAVORITES_KEY, json.dumps(ids))

    def launched(self, app_id):
        ids = [app_id] + [i for i in self.recent if i != app_id]
        self.db.set_setting(RECENT_KEY, json.dumps(ids[:RECENT_LIMIT]))
