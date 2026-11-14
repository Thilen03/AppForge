# AppForge 0.5.6

## New features

- **Application details.** Choose **Details…** from an application's card menu
  to see its icon, name, description, format, installed version, file location,
  current file size, and date added to AppForge.
- **Update information in one place.** See the linked repository, latest known
  version, update status, last check time, and stable or prerelease preference.
  Open the known release page in your browser when one is available.
- **Backup overview.** See the number of available backups, their total storage
  size, and the most recent backup date, with access to backup management and
  rollback.

## Improvements

- Move Settings beside **Add Application** in the library header, with a gear
  button that matches the other header buttons' height, blue background, and
  text colour.
- Launch, check for updates, update, edit, open the installation folder, and manage
  backups directly from the details window using AppForge's existing workflows.
- Details refresh after edits, updates, relocation, and rollback. Periodic refreshes
  and a **Refresh** button also pick up file and backup changes on disk.
- File and backup inspection runs in the background without launching application
  files. Missing files, unavailable metadata, and inaccessible backup information
  are shown with clear fallback messages.
- Missing applications offer **Locate file…**; files without execute permission
  offer **Make executable**. The details window supports light and dark themes.

## Bug fixes

- Keep the selected scan folder's highlight separated from neighbouring entries
  in **Discover apps…**, with a more compact highlight and consistent spacing
  in light and dark themes.
- Repositories that publish only prereleases now show **Pre-releases available**
  and explain how to enable them in Edit, instead of reporting that no releases
  exist. The known release page remains accessible while prereleases are disabled.
- Recognize numbered nightly versions in filenames such as
  `Longshot-nightly-144-a636846b-x86_64.AppImage`. Update checks can use that
  filename when the installed version is otherwise unknown.
- Compare numbered nightly builds by build number without treating their commit
  hashes as version numbers, avoiding incorrect update results.

## Known issues

- Release information opens in your browser. An in-app release-notes viewer is
  planned for a later update.

## Installation and upgrade

- The AppImage filename for this version is `AppForge-0.5.6-x86_64.AppImage`.
  Make it executable before launching it.
- Existing library records and settings are preserved. This update requires no
  database migration or manual re-import.
