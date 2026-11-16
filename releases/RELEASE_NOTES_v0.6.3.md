# TuxShelf 0.6.3

## New features

- Choose named launch profiles from the arrow beside each application's **Launch**
  button. Default keeps your existing settings; additional profiles can use their
  own environment variables, arguments, working directory and terminal setting.
- Create, rename, edit or delete profiles through **Edit profiles…** in the Launch
  dropdown. New profiles start as copies of Default. Save all edits together or
  cancel without changing the application. Tray, details and desktop-menu launches
  keep Default.
- Library exports and imports retain launch profiles. Environment variables in
  every profile follow the existing opt-in environment transfer controls.
- Select several applications and change their shared library/menu category,
  configure update settings, create menu shortcuts or remove library entries
  together. Click **Select apps**, click the cards and open **Actions for selected**.
- Bulk update settings let you pause or resume updates, choose stable or
  pre-release/nightly releases, change release asset patterns and clear skipped
  versions. Unspecified settings and each application's repository are preserved.

## Improvements

- Your chosen launch profile stays selected while the TuxShelf window is open,
  including after card refreshes. New sessions start with Default.
- Use **Select visible** to select apps matching the current search and filters.
  Sorting and card refreshes preserve selection; apps hidden by a filter are
  deselected. Click anywhere on a card except its buttons to select or deselect
  it; the corner checkbox still shows and controls selection. Card buttons keep
  their normal actions, and double-clicking in selection mode does not launch apps.
- Bulk actions show progress and support cancellation between apps, preserving
  completed changes. Busy apps are skipped and individual failures are reported
  without stopping the remaining apps.
- Removing selected entries requires confirmation and preserves application files
  and backups. TuxShelf's menu shortcuts and stored icons are removed with the
  entries.
- Changing update channels or asset patterns clears cached update targets. Use
  **Check for updates** afterward to find releases matching the new settings.

## Installation/upgrade instructions

Once published, use TuxShelf's self-update or download
`TuxShelf-0.6.3-x86_64.AppImage`, make it executable and launch it. Existing
applications and preferences are retained; no database migration is required.
Older TuxShelf versions may reject library exports containing launch profiles.
