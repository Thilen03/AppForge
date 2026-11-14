# Exporting and importing your library

Open **Settings** beside **Add Application**. Use **Export Library…** to save an
AppForge JSON file, or **Import Library…** to preview a previously exported file.
These actions apply immediately; the Settings Save/Cancel buttons only apply to
the preferences above them.

## Export

1. Choose **Export Library…**.
2. Leave environment variables off unless you intend to transfer their values.
   They can contain passwords or API tokens. An export with those values is plain
   text and should be handled accordingly.
3. Choose **Export JSON…** and select a destination. Exported files are written
   atomically with user-only permissions.

The export includes application IDs, names, absolute paths, formats, installed
versions, descriptions, date added, repositories, categories, menu categories,
prerelease preferences, file-matching patterns, launcher preferences and embedded
icons. Missing/unreadable or unsupported icons are omitted with a warning; the
application still exports.

Application executables, backups, global Settings preferences, AppForge access
tokens, download URLs, update status and release-note caches are excluded.
Environment variables are excluded by default. Unknown internal metadata is not
copied into the portable file.

An export transfers configuration, not the applications themselves. Copy your
application files separately if you want them on another computer. Do not use an
application, icon or library database as the export destination.

## Import

1. Choose **Import Library…**, then **Choose JSON…**.
2. Review the preview. Nothing is registered during this step. Full paths and
   status messages are also available in the row tooltips.
3. Select individual applications, or use **Select all eligible** / **Select none**.
4. Decide whether to restore the exported menu preferences. Missing applications
   can have launchers, but the desktop hides them until their files are available.
5. If the export contains environment variables, inspect the JSON before enabling
   **Restore environment variables**. They affect future launches. This option is
   off by default, even for files explicitly exported with environment variables.
6. Choose **Import selected** and confirm. The summary reports imported, missing,
   skipped, duplicate, failed and unprocessed applications. Individual errors and
   launcher warnings appear below it.

Files are inspected without executing them. Imports never move, rewrite or make
application files executable, and they never start an update. File/JSON/icon work
runs in background workers; database changes occur on the main thread. You can
stop an operation or close the dialog while it is working. Completed imports are
kept; the current uncommitted row is discarded when cancellation takes effect.
Cancellation cannot interrupt an individual operating-system file read already
in progress.

## Conflicts and missing files

- **Duplicate file:** normalized paths, symbolic-link aliases and hard links of
  available files are recognized. Already registered files and repeated files
  within the export are skipped. Existing configuration is never overwritten.
- **ID conflict:** the row is unavailable by default. Enable **Assign new IDs to
  conflicting entries** to import it as a separate application. The existing
  application retains its ID, settings and launcher.
- **Same name:** applications at different locations can share a display name.
  The preview identifies this and allows you to select them independently.
- **Missing or inaccessible file:** the configuration can still be imported.
  The card reflects the file's availability. Use **Locate file…** to connect a
  copied or moved application later.
- **Directory or unsupported/mismatched file format:** the row is unavailable.
  Correct its path/file and load the export again.
- **Changes during import:** files are checked again before registration. A file
  changed since preview is rejected. A file that disappeared can still be kept as
  a missing entry. If library paths or IDs change while a row is being prepared,
  that row stops with an explanation; load the export again to review it.

Menu creation failures do not lose the imported application. They appear as
warnings, and the saved preference allows normal launcher repair to retry later.
Backups are not transferred, but AppForge's existing backup management can discover
local backups beside the reconnected application file.

## Format and limits

The JSON envelope identifies `format: "appforge-library"`, `schema_version: 1`,
`appforge_version`, and an `applications` list. Schema versions are separate from
AppForge's application version. Unsupported schemas, duplicate JSON keys, unknown
fields and malformed configuration are rejected before any import begins.

Exports are limited to 32 MiB and 10,000 applications; each embedded icon is limited
to 10 MiB. Icons store a supported extension and base64 data, never a destination
path. Application paths must be absolute Linux paths; imported paths are not
rewritten for another user's home directory. Import the missing entries and use
Locate file when necessary.

Existing databases need no migration. Import does not restore global preferences
or overwrite saved tokens. Check for updates after import to obtain fresh release
metadata and available download files.
