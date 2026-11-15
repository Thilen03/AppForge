"""Single-entry commands shared by the bulk UI; no Qt or worker-owned SQLite."""
from __future__ import annotations

from dataclasses import dataclass

from .library import FileState, LibraryError, LibraryService, file_state
from .update_policy import PAUSED_KEY, SKIPPED_KEY
from .updates.service import UpdateService


@dataclass(frozen=True)
class UpdatePreferences:
    paused: bool | None = None
    include_prereleases: bool | None = None
    # None leaves each app's pattern unchanged; blank restores automatic matching.
    asset_pattern: str | None = None
    clear_skipped: bool = False


class BulkActions:
    def __init__(self, library: LibraryService):
        self.library = library
        self.updates = UpdateService(library)

    def apply(self, app_id: str, action: str, value=None) -> None:
        entry = self.library.get(app_id)
        if entry is None:
            raise LibraryError("This application is no longer in the library.")
        if action == "category":
            # Clear the legacy library-only override too, as the Edit dialog does.
            self.library.update_application(app_id, menu_category=value, category=None)
        elif action == "updates":
            prefs: UpdatePreferences = value
            settings = {}
            if prefs.paused is not None:
                settings[PAUSED_KEY] = prefs.paused
            if prefs.clear_skipped:
                settings[SKIPPED_KEY] = None
            invalidate = False
            if prefs.include_prereleases is not None:
                settings["include_prereleases"] = prefs.include_prereleases
                invalidate |= bool(entry.metadata.get("include_prereleases")) != prefs.include_prereleases
            if prefs.asset_pattern is not None:
                pattern = prefs.asset_pattern.strip()
                settings["asset_pattern"] = pattern or None
                invalidate |= (entry.metadata.get("asset_pattern") or "") != pattern
            # Invalidate before saving preferences: a failed save must never leave
            # an old install target enabled under a newly chosen release channel.
            if invalidate:
                self.updates.clear_update_state(app_id)
            if settings:
                self.library.update_application(app_id, settings=settings)
        elif action == "shortcuts":
            if file_state(entry) is not FileState.OK:
                raise LibraryError("The application file is missing or isn't executable.")
            self.library.set_desktop_integration(app_id, True)
        elif action == "remove":
            self.library.remove_application(app_id)
        else:
            raise ValueError(f"Unknown bulk action: {action}")
