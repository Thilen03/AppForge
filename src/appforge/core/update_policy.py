"""Persisted per-application update controls, independent of cached check results."""
from .models import AppEntry

PAUSED_KEY = "updates_paused"
SKIPPED_KEY = "skipped_update"


def updates_paused(entry: AppEntry) -> bool:
    return entry.metadata.get(PAUSED_KEY) is True


def version_skipped(entry: AppEntry) -> bool:
    skipped = entry.metadata.get(SKIPPED_KEY)
    info = entry.metadata.get("update") or {}
    return (isinstance(skipped, dict) and bool(info.get("tag"))
            and skipped.get("source") == entry.github_repo
            and skipped.get("tag") == info["tag"])


def updates_suppressed(entry: AppEntry) -> bool:
    return updates_paused(entry) or version_skipped(entry)
