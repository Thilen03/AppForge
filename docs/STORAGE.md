# Storage manager

Choose **Storage…** beside the library's discovery control. The blue/teal donut
compares current application file bytes with AppForge-managed backup bytes. It
also shows registered app count, measured backup count, the largest application
and the application with the largest backup collection. Empty libraries show an
empty ring. Nothing is executed while measuring.

Use the sort menu or sortable column headers to rank current files, backup sizes
and combined totals. **With backups only** filters the application table. Select
an application to see its saved backup versions, dates and file sizes. Unavailable
files/folders appear in Status (hover for the full notice); their missing sizes
are excluded, so reported totals may be incomplete. Refresh to retry. A stopped
scan explicitly labels its results as partial.

## Removing backups

Check individual saved backups. **Select older than retention** selects only
versions beyond the existing newest-N setting; unlimited retention selects none.
It does not change retention or delete anything. **Clear selection** clears all
checks. Explicit selection can remove newer backups too, just as in the existing
Backups & rollback dialog.

The footer previews the number selected and the maximum estimated savings.
**Delete selected…** presents a confirmation with a detailed list. Cancel is the
default. Cleanup rechecks identity and managed-directory membership immediately
before deletion. It refuses symlink files/directories and installed files,
including hard links to any registered application's current file. A changed,
missing, inaccessible or busy application/backup requires refreshing or is reported
as a per-file failure. Other approved files may still be removed; errors never
undo completed deletions. Stop takes effect between files. Closing waits for the
active operation to stop. SQLite updates remain on the GUI thread.

Only the expected `.<filename stem>.backups` folder beside the application's
registered path is inspected; stored paths outside it are excluded from shared
backup listing, pruning and rollback. No symlink directory component is followed.
This intentionally excludes backups left at an older location after an application
is moved. Keep those files or manage them separately after checking their identity.

## Measurement limits

Totals are logical regular-file sizes, not free disk capacity or an application's
configuration/cache folders. Hard links appear in each applicable file total.
Estimated savings exclude files with multiple hard links; actual recovered space
also depends on sparse files, compression, snapshots and open file handles.
Refresh is manual, and the snapshot is retained only while this dialog is open.
It may become stale when another process changes files; cleanup revalidates each
approved file. Operations use pinned directory descriptors and no-follow file
checks. Linux does not offer atomic compare-identity-and-unlink, so a malicious
process replacing files in the final check/unlink interval remains a filesystem
race limitation. No database migration or extra Qt module is required.
