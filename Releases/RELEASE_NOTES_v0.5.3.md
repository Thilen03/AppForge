# AppForge 0.5.3

Bug-fix release (0.5.2 → 0.5.3).

## Bug fixes

- **Drop-down corners.** Menus (the card "⋯" menu, tray menu, text context menus) and combo-box lists
  (category / status / sort filters, Settings interval, Add/Edit application dialogs) had a rounded border drawn
  inside a square popup window, so the corners looked broken. These popups are now frameless and translucent
  (`ui/popups.py`), and the stylesheet gives the combo-box list matching rounded corners, padding and item shape.
- **Duplicate instances.** Starting AppForge a second time no longer opens another window / tray icon. The first
  instance holds a lock (`flock`) and listens on a local socket (`core/instance.py`); a later launch asks it to
  show itself and exits. This works when the running instance is in the tray, minimized or behind other windows.
  The lock is released by the kernel on crash, so AppForge can't get stuck as "already running".
- **Minimized / hidden window.** Restoring from the tray (and from a second launch) now handles minimized and
  hidden windows, requests activation from the window system, and keeps an open dialog on top instead of
  reloading the library underneath it (`MainWindow.bring_to_front`).
- **Pinning to the taskbar.** AppForge now writes its own `appforge.desktop` launcher (pointing at the running
  AppImage, rewritten at each start so moving/updating the AppImage keeps pins working) with
  `StartupWMClass=appforge`, so the desktop can match the window and offer *Pin to Task Manager*.
  A pre-existing `appforge.desktop` that AppForge did not write is never overwritten. Not written when AppForge
  runs from source. The bundled `packaging/appforge.desktop` also gained `StartupWMClass` / `StartupNotify`.

## New / changed functionality

- **AppForge can update itself.** The startup check (unchanged: every start) now offers *Update now* / *Later*.
  *Update now* downloads the release AppImage, validates it, verifies SHA-256 when the release publishes it, backs
  up the current build (newest 2 backups kept), replaces the running AppImage atomically and offers to restart.
  The file keeps its current name so launchers and pins stay valid. *Later* closes the popup and it is shown
  again at the next start. If AppForge isn't running from an AppImage, or the folder isn't writable, the popup
  offers the release page instead. Failures leave the running version untouched.
- Restart after a self-update releases the single-instance slot before launching the new build.

## Technical changes

- New: `core/instance.py`, `core/desktop/selflauncher.py`, `ui/popups.py`.
- `core/selfupdate.py`: `SelfUpdate` carries the release asset(s); added `install_self_update`, `install_blocker`,
  `prune_backups`, `relaunch` (reuses `core.updates.installer`).
- `ui/workers.py`: `SelfInstallJob`. `ui/main_window.py`: update dialog flow, `bring_to_front`.
- Version bumped to 0.5.3 (`__init__.py`, `pyproject.toml`, README).
- Tests: `tests/test_v053.py` (Qt-free) and `tests/test_v053_gui.py`.

## Notes

- A release must include the `AppForge-<version>-x86_64.AppImage` asset (and ideally `SHA256SUMS`) for in-place
  self-update; otherwise the popup falls back to opening the release page.
- Popup rounding needs a compositing window manager (KDE Plasma has one by default).
