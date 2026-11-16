# TuxShelf 0.6.5

## New features

- On first launch, TuxShelf asks whether to add itself to your application menu.
  You can create or remove this shortcut later in Settings. Existing TuxShelf
  shortcuts are preserved when upgrading. New and refreshed shortcuts use the
  **Utilities** category.
- If TuxShelf's AppImage has moved or been renamed, startup asks whether to fix
  its application menu shortcut, showing the previous and current locations.
  Choosing No leaves the shortcut unchanged. Unchanged locations show no prompt.
- TuxShelf now shows this version's release notes when it first opens after an
  update. Notes are included with the app and can be read offline.
- Choose **Don't show again** to disable future release-notes popups. Untick
  **Don't show TuxShelf release notes after updates** in Settings to show the
  current notes again and enable them for future updates.

## Improvements

- Application cards now use the same solid blue style for **Update** and
  **Retry update** as **Launch**, making available updates easier to spot.

## Known issues

- Saved KDE Plasma menu-editor overrides can hide TuxShelf or exclude it from
  Utilities even when the shortcut uses the correct category. With the shortcut
  enabled, use KDE Menu Editor's **Show hidden entries** option, move TuxShelf
  into **Utilities** and save. TuxShelf does not change custom KDE menu rules.

## Installation/upgrade instructions

Once published, use TuxShelf's self-update or download
`TuxShelf-0.6.5-x86_64.AppImage`, make it executable and launch it. Existing
applications and preferences are retained; no database migration is required.
The launcher choice and release-notes popup settings can be changed in Settings.
