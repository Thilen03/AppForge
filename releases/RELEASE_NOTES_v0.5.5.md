# AppForge 0.5.5

## New features

- **Discover applications already on your computer.** Use **Discover apps…** in the
  library to scan `~/Applications`, `~/Downloads`, `/opt`, or folders you choose for
  AppImages, executable Linux binaries, and executable scripts.
- **Review results before importing.** See names, available icons and versions,
  file types, locations, and whether an application is already registered or ignored.
  Import selected applications or all eligible results after confirming your choice.
- **Remember your scanning preferences.** Added and removed scan folders are saved.
  Ignore unwanted results across scans, or reset the ignored list when needed.
- **Choose desktop-menu integration.** Optionally create application-menu entries
  when importing discovered applications.

## Improvements

- Scans run in the background with progress and cancellation. Results found before
  cancellation remain available for review. Bulk imports can be stopped between
  applications.
- Discovery leaves application files in place and does not run them to identify
  them. Overlapping folders and hard links are deduplicated, and files are checked
  again before import to reject changed, missing, or already-registered applications.
- Scanning and import errors are reported without preventing other eligible
  applications from being processed.

## Known issues

- Discovery runs when you request a scan; it does not continuously monitor folders.
- Symlinked files and folders, including scan roots reached through symlinks, are
  skipped. Choose the actual folder path when you want to scan its contents.
- Cancelling waits for the current file's metadata read to finish. Very large
  AppImages can delay cancellation or closing the discovery window.

## Installation and upgrade

- Use `AppForge-0.5.5-x86_64.AppImage` for Linux x86_64. Make it executable before
  launching it. Keep your existing library and settings; no database migration or
  manual re-import is required for this update.
- After upgrading, open **Discover apps…** to review additional applications.
  Existing library entries remain registered.
