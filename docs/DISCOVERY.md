# Discovering applications

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

These folders are also offered as download destinations when they are writable.
**Add Application → Download from a link… → Add folder…** saves a new location
here too. See the [download guide](DOWNLOADING.md).

The scanner recognizes AppImages and executable ELF binaries and shebang scripts.
AppImages can be discovered without an executable bit. Plain binaries and scripts
must be executable. Application files are inspected without being launched.

## Watch folders for new apps

In **Discover apps…**, check the boxes beside the discovery folders you want to
watch. Leave other folders unchecked for manual scanning only. Watch choices are
saved immediately and remembered across restarts. Removing a discovery folder
also stops watching it. Newly added folders start unchecked.

While AppForge is running, selected folders and their subfolders are checked in
the background about every 10 seconds. A file must remain unchanged between two
checks before it is offered, so newly completed downloads normally appear within
about 20 seconds (large folders or slow metadata reads can take longer). Existing
unregistered apps are offered too when watching first starts. Unchanged files use
cached inspection results. Hidden files and common temporary download suffixes
such as `.part`, `.crdownload` and `.tmp` are skipped.

The library shows **3 new apps found — Review…** with the current count. Click it
to open the normal discovery preview with all rows unchecked, then select and
confirm the apps you want to import. Watching never adds apps automatically.
Registered and ignored files are excluded; the count updates as files are imported,
ignored or removed. The count remains available if you close the preview without
importing. Use the preview's normal ignore/reset controls for unwanted files.

Watching continues when AppForge is hidden in the tray, and stops when you quit.
It is disabled by default. Missing or temporarily inaccessible folders are retried
on later checks; use **Scan folders** to see detailed filesystem errors. Files are
never executed by watching, and the normal import checks still reject files that
changed or disappeared after the preview was generated.

## Review and import

Results show the application name, available icon and version, format, location,
and status: **New**, **Already registered**, or **Ignored**. An editable **Update
source** column suggests repositories from supported embedded AppImage update
information or matching AppStream repository metadata. **No source detected**
means no supported source could be read; paste a repository manually if known.
Review, replace or clear these fields before importing; a blank field
means no update source. Invalid sources must be corrected before import. These
choices apply to new imports only. Missing metadata may
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

- Folder watching runs only while AppForge is running and only for checked
  discovery folders. It polls periodically rather than reacting instantly.
- Files that are still changing are deferred; a paused download that appears stable
  between checks may be offered. Import rechecks that the file still matches the preview.
- Symlinked files and folders, including symlinked roots or ancestor folders, are
  skipped. Select the actual folder path instead of a symlink.
- AppForge-managed hidden backup folders are excluded from discovery.
- Inaccessible or changing files can produce errors; review them before retrying.
- Cancellation and closing during a scan wait for the current metadata read to
  finish, which may take time for large files.

The discovery update uses the existing settings storage and does not require a
library database migration. See the original [0.5.5 discovery release notes](../releases/RELEASE_NOTES_v0.5.5.md)
and the [0.6.1 release notes](../releases/RELEASE_NOTES_v0.6.1.md) for download-folder integration.
