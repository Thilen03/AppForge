"""Applies update results to the database. Main-thread only (SQLite connection is not shared)."""
from __future__ import annotations

import logging
import re
import time

from ..backups import BackupService
from ..library import LibraryService
from ..models import AppEntry, UpdateStatus
from ..update_policy import PAUSED_KEY, SKIPPED_KEY, updates_paused, updates_suppressed
from .checker import CheckOutcome
from .installer import InstallResult
from .version import display_version
from ..formats.appimage import version_from_filename

log = logging.getLogger(__name__)
NOTIFIED_KEY = "notified_version"     # entry.metadata: latest version the user was already told about


def pattern_from_asset(asset_name: str, tag: str | None) -> str:
    """Turn a chosen asset name into a reusable glob by replacing its version with ``*``."""
    versions = [version_from_filename(asset_name)]
    if tag:
        versions += [tag, display_version(tag)]
    for version in versions:
        if not version:
            continue
        match = re.search(r"(?<![A-Za-z0-9])v?(?P<version>" + re.escape(version)
                          + r")(?![A-Za-z0-9])", asset_name)
        if match:
            # Escape literal glob metacharacters, including bracketed flavors.
            before, after = asset_name[:match.start("version")], asset_name[match.end("version"):]
            return _literal_pattern(before) + "*" + _literal_pattern(after)
    return _literal_pattern(asset_name)


def _literal_pattern(text: str) -> str:
    return "".join({"[": "[[]", "*": "[*]", "?": "[?]"}.get(c, c) for c in text)



class UpdateService:
    def __init__(self, library: LibraryService):
        self.library = library
        self.db = library.db
        self.backups = BackupService(library)

    def set_paused(self, app_id: str, paused: bool) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        if paused:
            entry.metadata[PAUSED_KEY] = True
        else:
            entry.metadata.pop(PAUSED_KEY, None)
        return self.db.update(entry)

    def skip_version(self, app_id: str) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None or not can_update(entry):
            return None
        tag = (entry.metadata.get("update") or {}).get("tag")
        if not tag or not entry.github_repo:
            return None
        entry.metadata[SKIPPED_KEY] = {"source": entry.github_repo, "tag": tag}
        return self.db.update(entry)

    def clear_skipped_version(self, app_id: str) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        entry.metadata.pop(SKIPPED_KEY, None)
        return self.db.update(entry)

    # -- checks -------------------------------------------------------------------------
    def apply_check(self, app_id: str, outcome: CheckOutcome) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None or updates_paused(entry):
            return entry
        entry.update_status = outcome.status
        entry.last_update_check = outcome.checked_at
        if outcome.status is not UpdateStatus.FAILED:
            entry.latest_version = outcome.latest_version
        prev = entry.metadata.get("update", {}) if outcome.status is UpdateStatus.FAILED else {}
        entry.metadata["update"] = {**prev, "message": outcome.message} if prev else {
            "message": outcome.message, "tag": outcome.tag, "release_url": outcome.release_url,
            "asset": outcome.asset, "ambiguous": outcome.ambiguous, "candidates": outcome.candidates,
            "assets": outcome.release_assets, "prereleases_only": outcome.prereleases_only,
            "notes": outcome.notes, "comparison": outcome.comparison}
        return self.db.update(entry)

    # -- notifications (Phase 5) ---------------------------------------------------------
    @staticmethod
    def should_notify(entry: AppEntry) -> bool:
        """True when an update is available that the user hasn't been told about yet."""
        return (not updates_suppressed(entry) and entry.update_status is UpdateStatus.UPDATE_AVAILABLE
                and bool(entry.latest_version)
                and entry.metadata.get(NOTIFIED_KEY) != entry.latest_version)

    def mark_notified(self, app_id: str) -> None:
        entry = self.db.get(app_id)
        if entry is not None and entry.latest_version:
            entry.metadata[NOTIFIED_KEY] = entry.latest_version
            self.db.update(entry)

    def pending_notifications(self) -> list[AppEntry]:
        return [e for e in self.db.list_all() if self.should_notify(e)]

    def clear_update_state(self, app_id: str) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        entry.update_status = UpdateStatus.UNAVAILABLE
        entry.latest_version = None
        entry.last_update_check = None
        entry.metadata.pop("update", None)
        return self.db.update(entry)

    # -- installs -----------------------------------------------------------------------
    def apply_install(self, app_id: str, result: InstallResult, outcome_tag: str | None) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        info = entry.metadata.get("update", {})
        new_version = entry.latest_version or display_version(outcome_tag or info.get("tag") or "")
        backups = entry.backup_info.setdefault("backups", [])
        if result.backup_path:
            backups.append({"file": result.backup_path, "version": entry.installed_version,
                            "created": time.time()})
        entry.installed_version = new_version or entry.installed_version
        entry.metadata["installed_version_source"] = "github_release"
        entry.metadata["last_install"] = {"time": time.time(), "tag": outcome_tag, "checksum": result.checksum}
        entry.update_status = UpdateStatus.UP_TO_DATE
        entry.metadata.setdefault("update", {})["message"] = ""
        entry.metadata["update"].pop("install_error", None)
        self.db.update(entry)
        try:                                   # retention: drop the oldest backups beyond the limit
            self.backups.prune(app_id)
        except Exception:                      # noqa: BLE001 - never fail an install over housekeeping
            log.warning("Backup pruning failed for %s", app_id, exc_info=True)
        try:                                   # new icon/description; keeps our version
            return self.library.refresh_metadata(app_id)
        except Exception:                      # noqa: BLE001 - metadata refresh is best-effort
            return self.db.get(app_id)

    def apply_install_failure(self, app_id: str, message: str) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        entry.update_status = UpdateStatus.FAILED
        entry.metadata.setdefault("update", {})["install_error"] = message
        entry.metadata["update"]["message"] = message
        return self.db.update(entry)

    # -- manual asset choice ------------------------------------------------------------
    def set_asset_pattern(self, app_id: str, asset_name: str) -> AppEntry | None:
        entry = self.db.get(app_id)
        if entry is None:
            return None
        info = entry.metadata.get("update", {})
        entry.metadata["asset_pattern"] = pattern_from_asset(asset_name, info.get("tag"))
        chosen = next((a for a in info.get("assets", []) if a["name"] == asset_name), None)
        if chosen:
            info["asset"], info["ambiguous"] = chosen, False
        return self.db.update(entry)


def can_update(entry: AppEntry) -> bool:
    """True when an update (or a retry of a failed one) can be started for this entry."""
    if updates_suppressed(entry):
        return False
    info = entry.metadata.get("update") or {}
    if not info.get("asset") or entry.latest_version is None:
        return False
    if entry.update_status is UpdateStatus.UPDATE_AVAILABLE:
        return True
    return entry.update_status is UpdateStatus.FAILED and bool(info.get("install_error"))


__all__ = ["UpdateService", "can_update", "pattern_from_asset", "NOTIFIED_KEY"]
