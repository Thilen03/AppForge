# TuxShelf 0.5.9

## New features

- Manage updates from the system tray: see available update counts, current activity
  and download progress, check for updates, or start Update All with the usual confirmation.
- Launch applications from the tray's Applications, Favorites and Recently used menus.
  Favorites and the last eight applications launched through TuxShelf are remembered
  between sessions.
- Add or remove favorites from each application's card menu. Favorites appear first
  in the library with a rounded gold star in the top-right corner. Hover over a card
  to reveal a gray star you can click to add a favorite; click a gold star to remove it.
  Library and tray favorites stay in sync, and search, filters and sorting still apply.
- Start TuxShelf automatically at desktop login, with an option to start hidden in
  the system tray. Without tray support, the window opens visibly.

## Improvements

- Open TuxShelf or Settings directly from the tray, with one action for returning
  to the library. Exit TuxShelf quits even when background mode is enabled.
- Hidden updates report individual results or a single completion summary for an
  Update All batch. Background check errors are grouped, and identical errors are
  not repeatedly announced during the same session. Notification preferences apply
  to these messages and the close-to-tray hint.
- Missing, non-executable or busy applications have disabled tray launch shortcuts.
  Tray failures return TuxShelf to the main window.
- Settings scrolls on smaller screens, with Save and Cancel always available.
- Self-update prompts wait until you open TuxShelf when it is running hidden.

## Bug fixes

- Minimizing now sends TuxShelf to the tray when background mode is enabled,
  including on KDE Plasma Wayland. Repeated minimize/restore cycles clear the old
  minimized state so the window can be opened normally again.
- Rechecking from the tray no longer claims everything is up to date when updates
  were already announced or an update source could not be checked.

## Known issues

- Tray availability and menu appearance depend on desktop support. Enable
  Minimize or close to the system tray in Settings to use background mode.
- Plasma Wayland minimize-to-tray requires the session D-Bus connection and KWin
  scripting interface. Its temporary helper observes only TuxShelf's main window
  and does not change KDE settings. If unavailable, TuxShelf reports the error and
  closing to the tray still works.
- Login startup requires desktop autostart support. If you move the AppImage,
  open it from its new location once to refresh the startup entry.
- Recent launches track launches through TuxShelf; external desktop launchers are
  not tracked. Favorites and launch history are local preferences and are not
  included in library exports.

## Installation/upgrade instructions

- Exit any running TuxShelf instance using Exit TuxShelf in the tray before
  launching the new TuxShelf-0.5.9-x86_64.AppImage. Otherwise, a second launch can
  reopen the older process instead of starting the new build.
- Your existing library and preferences are preserved; no database migration is required.
- To start at login, open Settings and enable Start TuxShelf at login. Optionally
  enable Start minimized to the system tray, which also enables background mode.
