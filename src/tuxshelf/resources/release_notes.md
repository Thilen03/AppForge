# TuxShelf 0.6.6

## Improvements

- AppForge is now **TuxShelf**. The new name gives the project a more distinctive
  identity and makes it easier to tell apart from other applications. The name is
  updated throughout its windows, settings, notifications, application-menu
  entries and documentation.
- New installations use the `tuxshelf` command and data directory. New library
  exports and future AppImage builds also use the TuxShelf name.
- Existing libraries, settings, icons and backup records remain available.
  Earlier library exports can still be imported, and existing managed menu and
  login shortcuts are refreshed with the new application name.

## Bug fixes

- The main window title shows only `TuxShelf 0.6.6`, without an extra application
  name appended on desktops that add Qt's application display name.

## Breaking changes

- The command for starting the application is now `tuxshelf`, and source launches
  use `python -m tuxshelf`. Update any scripts that invoke the previous name.

## Installation/upgrade instructions

Build or download `TuxShelf-0.6.6-x86_64.AppImage`, make it executable and launch it.
Existing application files stay where they are. An existing library is reused in
its original data folder so saved paths remain valid; new installations use
`~/.local/share/tuxshelf/`.

When running from source, use `PYTHONPATH=src python -m tuxshelf`. Portable setups
can use `TUXSHELF_DATA_DIR`; the earlier environment override is also accepted.
If the AppImage location has changed, approve the shortcut repair prompt to update
its target. The GitHub repository still uses its existing address.
