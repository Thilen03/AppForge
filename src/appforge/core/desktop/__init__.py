"""Phase 4: freedesktop.org launcher integration (``.desktop`` entries)."""
from .service import (
    MENU_CATEGORIES, MENU_CATEGORY_KEY, DesktopError, DesktopService, ManagedEntry, SyncReport,
    entry_filename, menu_category_of, quote_exec_arg, render_entry,
)

__all__ = ["DesktopService", "DesktopError", "ManagedEntry", "SyncReport", "entry_filename",
           "quote_exec_arg", "render_entry", "MENU_CATEGORIES", "MENU_CATEGORY_KEY",
           "menu_category_of"]
