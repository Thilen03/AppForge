"""Categories, filtering and sorting of the library (Phase 5). Qt-free and database-free.

Category of an app = the one the user chose (``metadata["category"]``), otherwise the main one from the
application's own ``.desktop`` ``Categories`` (``metadata["categories"]``, read from inside the
AppImage), otherwise "Other". The user's choice is never overwritten by a metadata refresh.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable

from .models import AppEntry, UpdateStatus

CATEGORY_KEY = "category"
OTHER = "Other"
MAX_CATEGORY_LEN = 40

# freedesktop "Main Categories" -> label shown in AppForge (order = priority when an app lists several)
_MAIN = (
    ("Development", "Development"), ("Graphics", "Graphics"), ("AudioVideo", "Multimedia"),
    ("Audio", "Multimedia"), ("Video", "Multimedia"), ("Game", "Games"), ("Network", "Internet"),
    ("Office", "Office"), ("Education", "Education"), ("Science", "Science"), ("System", "System"),
    ("Settings", "System"), ("Utility", "Utilities"),
)
DEFAULT_CATEGORIES = tuple(dict.fromkeys(label for _, label in _MAIN)) + (OTHER,)


def clean_category(text: str | None) -> str | None:
    """Normalised user category, or ``None`` for blank/automatic."""
    cat = " ".join((text or "").split())[:MAX_CATEGORY_LEN].strip()
    return cat or None


def derived_category(entry: AppEntry) -> str:
    raw = entry.metadata.get("categories") or ""
    present = {c.strip().lower() for c in str(raw).split(";") if c.strip()}
    for key, label in _MAIN:
        if key.lower() in present:
            return label
    return OTHER


def category_of(entry: AppEntry) -> str:
    return clean_category(entry.metadata.get(CATEGORY_KEY)) or derived_category(entry)


def categories_in_use(entries: Iterable[AppEntry]) -> list[str]:
    """Categories that at least one app has, alphabetically, with "Other" last."""
    found = {category_of(e) for e in entries}
    return sorted(found - {OTHER}, key=str.lower) + ([OTHER] if OTHER in found else [])


def category_suggestions(entries: Iterable[AppEntry]) -> list[str]:
    """What the Edit dialog offers: the standard names plus anything the user typed before."""
    custom = {clean_category(e.metadata.get(CATEGORY_KEY)) for e in entries} - {None}
    base = [c for c in DEFAULT_CATEGORIES if c != OTHER]
    return base + sorted((c for c in custom if c not in base), key=str.lower) + [OTHER]


# -- status filters ---------------------------------------------------------------------------
ALL = "all"
UPDATES = "updates"          # an update is available
ATTENTION = "attention"      # file missing / not executable / last update failed
UNLINKED = "unlinked"        # no update source configured

STATUS_FILTERS = ((ALL, "All applications"), (UPDATES, "Updates available"),
                  (ATTENTION, "Needs attention"), (UNLINKED, "No update source"))

SORT_NAME, SORT_RECENT, SORT_STATUS = "name", "recent", "status"
SORTS = ((SORT_NAME, "Name"), (SORT_RECENT, "Recently added"), (SORT_STATUS, "Update status"))


@dataclass(frozen=True)
class Filter:
    query: str = ""
    category: str | None = None      # None = every category
    status: str = ALL

    @property
    def active(self) -> bool:
        return bool(self.query.strip() or self.category or self.status != ALL)


def matches(entry: AppEntry, flt: Filter, *, file_ok: Callable[[AppEntry], bool] | None = None,
            ) -> bool:
    """Does ``entry`` pass ``flt``?  ``file_ok`` says whether its file is present and runnable."""
    q = flt.query.strip().lower()
    if q and q not in entry.name.lower() and q not in entry.path.lower() \
            and q not in category_of(entry).lower():
        return False
    if flt.category and category_of(entry) != flt.category:
        return False
    if flt.status == UPDATES:
        return entry.update_status is UpdateStatus.UPDATE_AVAILABLE
    if flt.status == ATTENTION:
        healthy_file = file_ok(entry) if file_ok else os.access(entry.path, os.X_OK)
        return (not healthy_file) or entry.update_status is UpdateStatus.FAILED
    if flt.status == UNLINKED:
        return not entry.github_repo
    return True


_STATUS_RANK = {UpdateStatus.UPDATE_AVAILABLE: 0, UpdateStatus.FAILED: 1, UpdateStatus.CHECKING: 2,
                UpdateStatus.UNAVAILABLE: 3, UpdateStatus.UP_TO_DATE: 4}


def sort_entries(entries: Iterable[AppEntry], key: str = SORT_NAME) -> list[AppEntry]:
    items = list(entries)
    by_name = lambda e: (e.name.lower(), e.id)                       # noqa: E731
    if key == SORT_RECENT:
        return sorted(items, key=lambda e: (-e.added_at, e.name.lower()))
    if key == SORT_STATUS:
        return sorted(items, key=lambda e: (_STATUS_RANK.get(e.update_status, 9), by_name(e)))
    return sorted(items, key=by_name)


__all__ = ["Filter", "matches", "sort_entries", "category_of", "derived_category", "clean_category",
           "categories_in_use", "category_suggestions", "CATEGORY_KEY", "OTHER", "STATUS_FILTERS",
           "SORTS", "ALL", "UPDATES", "ATTENTION", "UNLINKED", "SORT_NAME", "SORT_RECENT",
           "SORT_STATUS"]
