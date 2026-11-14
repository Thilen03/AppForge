# AppForge 0.5.8

## New features

- Open Storage from the library to see a modern pie-chart overview of application
  and backup storage, app and backup counts, and your biggest space consumers.
- Sort applications by file size, backup storage or combined usage, and filter to
  applications with backups.
- Review saved backup versions, dates and sizes, select the older versions beyond
  your retention setting, and preview estimated savings before confirming deletion.
- Refresh or stop storage measurement and cleanup while the interface stays responsive.

## Improvements

- Check for updates, Discover apps and Storage now use the same blue button styling
  as Add Application and Settings in the library, with matching gaps between buttons.
- Backup listing and cleanup now reject paths outside each application's expected
  backup folder and skip symlinks. Cleanup protects installed files and refuses
  backups that changed after the storage preview.
- The storage overview supports both light and dark themes and reports unavailable
  files or folders without hiding that totals may be incomplete.

## Known issues

- Storage totals measure application files and managed backups, not application
  data folders or free disk space. Shared hard links can make logical totals larger
  than physical disk usage; estimated cleanup savings are an upper bound.
- Backups remaining at an application's old location after relocation are excluded
  from backup management. Their files remain on disk.
