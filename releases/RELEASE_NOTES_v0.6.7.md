# TuxShelf 0.6.7

## New features

- Use **Image link…** when adding or editing an application to download your own
  custom icon from a direct HTTP or HTTPS image link. Saved icons stay available
  offline in TuxShelf's managed icon cache, including after metadata refreshes.

## Improvements

- Image downloads show progress and can be cancelled without changing your current
  icon. Invalid links, unreadable images and oversized downloads display an error
  so you can try another link.
- Release links, self-update checks and publishing now use the renamed
  `Thilen03/TuxShelf` GitHub repository.

## Bug fixes

- Building from a project folder renamed from AppForge to TuxShelf no longer
  fails because pip or PyInstaller launchers still reference the old folder.

## Installation/upgrade instructions

Build or download `TuxShelf-0.6.7-x86_64.AppImage`, make it executable and launch it.
Existing library entries and custom icons are preserved. No database migration is
required.

For an image link, use the image's direct URL rather than a web page. Downloads
must fit within 10 MB and 16 million pixels. Downloaded images are converted to
PNG, which must also fit within 10 MB. Local image selection remains available;
**Use default** restores the application's embedded icon or a placeholder.
