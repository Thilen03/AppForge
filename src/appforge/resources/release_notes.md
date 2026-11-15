# AppForge 0.6.5

## New features

- On first launch, AppForge asks whether to add itself to your application menu.
  You can create or remove this shortcut later in Settings. Existing AppForge
  shortcuts are preserved when upgrading. New and refreshed shortcuts use the
  **Utilities** category.
- If AppForge's AppImage has moved or been renamed, startup asks whether to fix
  its application menu shortcut, showing the previous and current locations.
  Choosing No leaves the shortcut unchanged. Unchanged locations show no prompt.
- AppForge now shows this version's release notes when it first opens after an
  update. Notes are included with the app and can be read offline.
- Choose **Don't show again** to disable future release-notes popups. Untick
  **Don't show AppForge release notes after updates** in Settings to show the
  current notes again and enable them for future updates.

## Improvements

- Application cards now use the same solid blue style for **Update** and
  **Retry update** as **Launch**, making available updates easier to spot.

## Known issues

- Saved KDE Plasma menu-editor overrides can hide AppForge or exclude it from
  Utilities even when the shortcut uses the correct category. With the shortcut
  enabled, use KDE Menu Editor's **Show hidden entries** option, move AppForge
  into **Utilities** and save. AppForge does not change custom KDE menu rules.

## Installation/upgrade instructions

Once published, use AppForge's self-update or download
`AppForge-0.6.5-x86_64.AppImage`, make it executable and launch it. Existing
applications and preferences are retained; no database migration is required.
The launcher choice and release-notes popup settings can be changed in Settings.
