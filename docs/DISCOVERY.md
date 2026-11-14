# Discovering applications in AppForge 0.5.7

Discovery finds portable applications already on your computer and lets you review
and import them into your library. It does not download or install applications.

## Scan folders

1. Click **Discover apps…** beside **Check for updates** in the library window.
2. Review the scan folders. The defaults are `~/Applications`, `~/Downloads`, and
   `/opt`. Use **Add folder…**, **Remove folder**, or **Default folders** as needed.
   Your chosen folders are remembered for later scans. The selected folder uses a
   compact highlight with spacing between entries in both light and dark themes.
3. Click **Scan folders**. AppForge scans these folders and their subfolders in the
   background, reporting progress. **Cancel scan** stops between file reads and
   keeps results found so far.

The scanner recognizes AppImages and executable ELF binaries and shebang scripts.
AppImages can be discovered without an executable bit. Plain binaries and scripts
must be executable. Application files are inspected without being launched.

## Review and import

Results show the application name, available icon and version, format, location,
and status: **New**, **Already registered**, or **Ignored**. Missing metadata may
appear as **Unknown**. Overlapping folders and hard links do not create repeated
results; already-registered applications cannot be imported again.

- Check individual new results, or use **Select all** and **Select none**.
- Choose **Import selected** or **Import all eligible** and confirm before importing.
- Choose whether to add imported applications to the desktop application menu.
- Use **Stop importing** to stop a bulk import between applications. Applications
  already imported remain in your library.

Import keeps application files at their original locations. Before each import,
AppForge checks for changed or missing files, executable permissions where needed,
and duplicate library entries. Errors are displayed; other applications can still
be processed. If a file changed, scan again before retrying it.

## Ignore results

Select unwanted new results and click **Ignore selected**. Ignored paths remain
visible but cannot be imported, and the ignore list survives restarts.
**Reset ignored files** clears that list and makes eligible results selectable again.

## Scan limitations

- Discovery is an explicit scan, not continuous folder monitoring.
- Symlinked files and folders, including symlinked roots or ancestor folders, are
  skipped. Select the actual folder path instead of a symlink.
- AppForge-managed hidden backup folders are excluded from discovery.
- Inaccessible or changing files can produce errors; review them before retrying.
- Cancellation and closing during a scan wait for the current metadata read to
  finish, which may take time for large files.

The discovery update uses the existing settings storage and does not require a
library database migration. See the original [0.5.5 discovery release notes](../releases/RELEASE_NOTES_v0.5.5.md)
and the [0.5.6 release notes](../releases/RELEASE_NOTES_v0.5.6.md) for the latest refinements.
