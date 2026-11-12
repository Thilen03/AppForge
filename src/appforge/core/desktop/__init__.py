"""Phase 4: freedesktop.org launcher integration (``.desktop`` entries)."""
from .service import (
    DesktopError, DesktopService, ManagedEntry, SyncReport, entry_filename, quote_exec_arg,
    render_entry,
)

__all__ = ["DesktopService", "DesktopError", "ManagedEntry", "SyncReport", "entry_filename",
           "quote_exec_arg", "render_entry"]
