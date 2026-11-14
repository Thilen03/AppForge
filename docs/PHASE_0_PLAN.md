# Phase 0 inspection and implementation plan

Inspected for the 0.5.5 discovery update, 14 November 2026.

## Existing architecture

- `app.py` initializes SQLite, LibraryService, startup launcher repair, the Qt window,
  single-instance control and self-update restart handling.
- `core/database.py` applies append-only migrations using SQLite user_version. There
  are two migrations: application records and a global settings key/value table.
  AppEntry stores extensible per-app metadata and backup information as JSON.
- `core/formats` detects AppImages before generic ELF/shebang executables. Existing
  metadata readers inspect bytes and embedded SquashFS without executing files.
- `LibraryService` owns library writes, normalized paths, icon storage and desktop
  integration. The SQLite connection belongs to the main thread.
- Cards/dialogs use the shared theme. QRunnable workers emit Qt signals for network
  work; cancellation uses threading.Event. Check and installation pools are separate.
- Providers normalize GitHub/GitLab/Codeberg/custom-host releases. The installer
  validates downloads, optionally checks hashes, preserves backups and swaps files
  atomically. BackupService manages retention and reversible rollback.
- Tray functionality currently provides Open, Check and Quit. Settings and update
  notifications already persist. None of these workflows needs replacement.
- Tests include core, GUI, provider, installer, backup and desktop checks. Real
  AppImage fixtures require appimagetool. Packaging uses PyInstaller/appimagetool.

## Phase 1 plan

1. Add Qt-free discovery models/scanning and preference helpers in core/discovery.py.
   Scan explicit default/custom roots recursively without following symlinks; exclude
   managed backup folders, deduplicate by normalized path and device/inode, report
   errors, progress and cancellation, and reuse inspect_file.
2. Add a dedicated discovery dialog with configurable roots, a worker, preview table,
   checkboxes, select all/none, import selected/all, ignore, progress and cancellation.
   Keep DB writes on the UI thread, one candidate per event-loop turn. Require an
   explicit import confirmation and revalidate each candidate before registering it.
3. Add the entry point beside the library update controls; refresh the library after
   the dialog closes. Reuse LibraryService and its desktop integration preference.
4. Add scanner/import/GUI tests, run regression checks, update README/version/roadmap,
   and package only changed files plus versioned release notes.

No schema migration: discovery roots and ignored paths use the existing settings
store; old application records and preferences remain untouched. Risks include
filesystem races, restricted directories, huge directory trees and worker lifetime.
Use non-followed symlinks, identity checks, bounded progress reporting, cooperative
cancellation and deferred dialog closure until the worker finishes. Cancellation
cannot interrupt an individual metadata read already in progress.

## Later phases: likely components (not implemented in this update)

| Phase | Likely components |
| --- | --- |
| 2 Details | New details dialog; app_card/main_window actions; existing library/update/backup services |
| 3 Release notes | Release model and provider mappings; cached metadata; new async viewer |
| 4 Export/import | New validated JSON service/dialog; settings actions; library persistence |
| 5 Storage | New background size service/overview; BackupService cleanup reuse |
| 6 Enhanced tray | tray/main_window, settings, launch service, notification coordination |
| 7 Integration | Existing test modules plus feature tests and database upgrade fixtures |
