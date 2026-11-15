# AppForge 0.6.2

## New features

- Customize each application card badge separately, including AppImage, Executable,
  update statuses and file warnings. Expand **Application badge colors** at the
  bottom of Settings to open the color pickers and previews.
- Badge colors are saved locally and apply immediately when you choose **Save**.
  **Cancel** discards unsaved changes. Reset a single badge or restore all defaults.
- Watch selected folders from **Discover apps…** for new applications while
  AppForge is running. A **new apps found — Review…** prompt opens the existing
  preview so you choose what gets imported; nothing is added automatically.
- Watching includes subfolders, waits for unchanged files between checks, skips
  temporary downloads, and excludes registered or ignored apps. Folder watch
  choices are remembered and can be turned off individually.
- Local AppImage imports can suggest an update-source repository from embedded
  update information. Review, change or clear the source before adding the app.
- Discovery and watched-folder previews include editable update sources for each
  new app. Confirmed imports save the sources shown in the preview. Manual and
  repository-download source choices take precedence.

## Improvements

- Custom badge colors keep matching text and outlines with a softly tinted
  background in light and dark themes. The original colors remain the defaults.
- Badge color controls start collapsed so everyday settings stay easy to reach.
- Source detection also considers matching AppStream repository metadata when
  dedicated update information is unavailable. The suggestion identifies its origin.

## Bug fixes

- Local Add now shows source-detection progress and a found, not-found or failed
  result in a persistent panel above **Add to library**. Scrolling or editing
  fields no longer hides the result. Discovery also reports when no source was found.
- Prevented details from an earlier file selection appearing after choosing a
  file that is already in the library.

## Known issues

- Update-source detection requires recognizable embedded source metadata.
  Generic download servers and unsupported transports still need a manually
  supplied repository. Suggestions are package metadata, not online verification;
  AppForge's normal update checks and channel settings still apply.
- Folder watching runs only while AppForge is running and checks periodically.
  A paused download that appears unchanged may be listed; importing rechecks that
  the file still matches the preview.

## Installation/upgrade instructions

Once published, use AppForge's self-update or download
`AppForge-0.6.2-x86_64.AppImage`, make it executable and launch it. Existing
applications and preferences are retained; no database migration is required.
