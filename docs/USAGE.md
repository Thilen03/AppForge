# Using AppForge

[Back to the README](../README.md)

Detailed guidance for everyday use, update behavior and troubleshooting. For
adding downloads, discovery, categories, launch options, library transfer, storage
and update controls, see the [documentation index](../README.md#documentation).

## Library and launcher
- **Add apps from anywhere**: by file picker, repository download or by dragging `.AppImage` files onto the window.
  Existing local files are never moved or copied; repository downloads are saved in your chosen folder. To add a plain executable or script, choose *All files* in the file picker.
- **Reads the AppImage without running it**: name, version, description and icon are extracted from inside the file.
  File names such as `Dolphin-Emu-5.0-x86_64.AppImage` are cleaned up to a sensible suggested name ("Dolphin Emu").
- **Application cards** show icon, name, version, format, update status and file location.
  Badges share a soft tinted background, colored outline and matching text in both
  themes: green for up to date, blue for available updates, yellow for paused
  updates, red for errors and gray for unavailable or skipped updates by default.
  Expand **Application badge colors** at the bottom of **Settings** to choose a
  color separately for each format and status badge. Previews show matching text
  and outlines with a softly tinted background in both themes. The section starts
  collapsed each time Settings opens.
  **Reset** restores one badge; **Reset all badge colors** restores the original
  light/dark defaults. **Save** applies and remembers changes; **Cancel** discards them.
- **Launch from a card.** Apps are started detached, so they keep running if you close AppForge. If an app exits
  right after launch, AppForge shows its output and keeps a log. For terminal launches,
  application output appears in the terminal; AppForge may only capture terminal-process
  output and exit status. See the [launch options guide](LAUNCH_OPTIONS.md).
  Use the arrow beside **Launch** to choose a launch profile or **Edit profiles…**.
  Default keeps the existing Add/Edit settings; named profiles can use different
  environment variables, arguments, working directories and terminal settings.
- **Search, categories, filters and sorting**: filter by category or by status (updates available, needs attention,
  no update source) and sort by name, date added or update status.
- **One shared category**: the **Category** dropdown in Add/Edit uses the standard KDE/desktop
  menu categories. Your choice groups the app in AppForge and places its launcher in the same
  category when menu integration is enabled. **Automatic** uses the application's metadata.
  Existing menu choices take precedence over old library-only categories. Older custom categories
  are preserved until you choose a replacement. See the [category guide](CATEGORIES.md).
- **Light and dark theme**: click the sun/moon button immediately to the right of
  Settings to switch instantly. The sun switches to light mode; the moon switches
  to dark mode. Your choice is remembered across restarts. Until you choose a mode,
  AppForge follows your desktop's appearance.
- **Standalone executables too**: besides AppImages you can add any single Linux program (ELF binary) or `#!`
  script. They get cards, launchers, update checks, backups and rollback just like AppImages. For updates, the
  release must publish the raw binary (see [Current limitations](#current-limitations)).


## Working with several applications

Click **Select apps** above the library, then click anywhere on a card except its
buttons to select or deselect it. The corner checkbox shows the selection and
can still be clicked directly. Card buttons keep their normal actions.
**Select visible** selects every app matching the current search and filters;
**Clear** deselects them. Sorting and card refreshes preserve selection. Changing
filters deselects apps that become hidden. **Done selecting** exits selection mode.

Open **Actions for selected** to:

- **Change category…** — apply the shared library/menu category, or choose
  **Automatic** to use each app's own metadata. Existing menu shortcuts are updated.
- **Update settings…** — pause/resume checks, choose stable or pre-release/nightly
  releases, change the release asset pattern or clear skipped versions. Fields
  default to **Leave unchanged** so mixed settings are preserved. To restore
  automatic asset matching, enable **Change release asset pattern** and leave it
  blank. Repository sources remain unchanged. Channel/pattern changes clear old
  update results; use **Check for updates** afterward.
- **Create menu shortcuts** — add or refresh desktop-menu launchers. Missing or
  non-executable files are reported without creating a launcher.
- **Remove from library…** — review the confirmation and expand its details to
  see the selected names. Application files and backups remain on disk; AppForge's
  menu shortcuts and stored icons are removed with their entries.

Actions show progress and can be cancelled between apps. Completed changes remain
saved. Apps currently being checked or updated are skipped. Failures do not stop
the remaining apps; the result reports failed/skipped entries and any unprocessed
apps after cancellation. Double-clicking a card in selection mode does not launch it.

## Application details

- Choose **Details…** from an application's card menu to see its description, format,
  installed version, location, file size and date added, alongside update status,
  repository, last check, update channel and backup storage information.
- Launch, check for updates, update, edit, open the installation folder, or manage
  backups using the same actions as the library. **Release notes…** opens the
  in-app viewer; **View release page** opens the known release in your browser.
- Details refresh after library changes and every few seconds. **Refresh** also
  rechecks the file and backups. Missing files offer **Locate file…**; files without
  execute permission offer **Make executable**. Filesystem inspection runs in the
  background and never launches an application.

## Release notes

- Choose **Release notes…** from a card menu or application details after checking
  for updates. **Update All** also offers release notes before you approve updates.
- Read the selected release's version, title, publication date, stable/prerelease
  status and formatted description in a scrollable viewer. HTTP(S) links open in
  your browser; embedded images are omitted.
- Notes are cached with the repository and exact release tag, including across
  restarts. **Refresh** reloads that tag through the existing GitHub, GitLab,
  Codeberg or self-hosted Forgejo/Gitea/GitLab API in the background. Refresh errors
  keep cached notes visible. Reading notes never starts an update.
- Releases without descriptions show an explicit message. Older library records
  fetch notes on first opening. If the tag is no longer among the provider's recent
  releases, use **Open release page** or check for updates again.

## Enhanced system tray

- Enable **Minimize or close to the system tray** in Settings on a desktop with tray support.
  The tray menu shows available update counts and current download/check activity,
  with **Check for updates** and **Update All** using the existing confirmation workflow.
- Use **Open AppForge** to return to the library, or open Settings directly from the tray.
  **Exit AppForge** quits; minimizing or closing the window hides it from the taskbar
  and keeps background checks and updates running while background mode is enabled.
- On KDE Plasma Wayland, AppForge uses a temporary KWin observer to receive
  titlebar/taskbar minimize notifications that Qt may not receive. It observes only
  AppForge's own main window while tray mode is enabled, and is unloaded when tray
  mode is disabled or AppForge exits. No KDE configuration is changed. If KWin's
  scripting interface is unavailable, AppForge reports it; closing to tray still works.
- Launch from **Applications**, **Favorites** or **Recently used**. Use **Choose favorites**
  to select favorites. Recent launches remember the last eight apps launched through
  AppForge; external desktop launches are not recorded. Missing/non-executable or busy
  apps are disabled. Launches use each app's existing environment preferences.
- Availability notifications remain once per new version. Hidden updates report success
  or failure, with a single summary per Update All batch. Repeated identical background
  check errors are suppressed for the session. Notification preferences apply throughout.
- In each library card's menu beside **Edit**, choose **Add to favorites** or
  **Remove from favorites**. Favorites appear first with a small gold star in the
  top-right corner. Hover over a card to reveal a gray star in that same spot;
  click it to add a favorite, or click the gold star to remove one. The stars have
  a fuller, rounded shape, and the card layout stays still as they appear.
  The selected sort order applies within favorites and other apps;
  search and filters continue to apply. Favorites are shared with the tray in both directions.
- Favorites and recent launches are saved locally and excluded from library exports.
  Tray support and native menu appearance depend on your desktop; without a tray host,
  continue using the main window.

## Start at login

- In Settings, enable **Start AppForge at login** to launch it when you log in to
  your Linux desktop. Optionally enable **Start minimized to the system tray**;
  this also enables background mode. Ordinary launches still open the window.
- Without tray support, AppForge opens visibly. Startup self-update prompts wait
  until you open the hidden window. A duplicate login launch leaves an existing
  instance alone; an ordinary second launch brings it forward.
- Save writes AppForge's own entry under `$XDG_CONFIG_HOME/autostart/appforge.desktop`
  (normally `~/.config/autostart/appforge.desktop`). Disabling startup removes that
  entry. Files not managed by AppForge are preserved, and save errors are shown.
- Keep the AppImage at its saved location. If you move it, open it once from its
  new location to refresh the startup entry. Source installations point to their
  current Python environment and source folder, which must remain available.
- Settings scrolls on smaller screens while Save and Cancel stay visible.

## Detected update sources

- The Add form has a persistent **Automatic update-source detection** panel above
  **Add to library**. Selecting a local file starts **Checking…** with a progress
  indicator, then reports **Update source found**, **No automatic update source
  found**, or **Source detection failed**. The panel stays visible while scrolling
  and editing fields. Other executable formats explain that AppImage detection
  does not apply.
- When adding a local AppImage, AppForge reads its embedded update information and
  prefills a supported repository when one can be identified. The source is marked
  as suggested; review, change or clear it before choosing **Add to library**.
- Manual and watched-folder discovery previews include an editable **Update source**
  column. Sources shown there are saved only when you confirm importing the apps.
  Clear a field to import that app without an update source.
- A source you entered yourself or selected for a repository download takes
  precedence. Existing library entries are not automatically relinked.
- If no supported source is found, Add explicitly says **No automatic update source
  found**, and discovery shows **No source detected**. A filename or a GitHub download
  alone does not identify the repository owner. Paste the repository URL manually
  when the file contains no usable source metadata.
- Detection also checks matching embedded AppStream component metadata: explicit
  source-code repository URLs, then repository-root homepages on GitHub, GitLab
  or Codeberg. Conflicting URLs and unrelated bundled components are not used.
  Suggestions say which embedded metadata provided them.
- Detection supports GitHub's embedded release information and recognizable HTTPS
  release-download URLs for supported Git repositories. Generic zsync servers,
  Pling, deprecated Bintray information, missing data and malformed data do not
  produce repository guesses; add a source manually when appropriate.
- Detection works offline without executing the AppImage. A suggestion comes from
  the package and is not proof that the repository exists or is trustworthy.
  Normal update checks still use AppForge's release APIs and full-file downloads;
  embedded tags, filename patterns and prerelease preferences are not applied.

## Updates
- **Link a repository** to any app and AppForge checks its releases for a newer version. Supported sources:
  - **GitHub**, **GitLab.com** and **Codeberg**
  - **Any self-hosted Forgejo, Gitea or GitLab server**, e.g. `https://git.example.dev/owner/repo`
- **Smart release matching.** AppForge picks the right AppImage from a release and ignores source archives, `.zsync`
  files, checksums and other CPU architectures. If several files look equally good it asks once and remembers your
  choice. You can also set a file pattern per app (for example `MyApp-*-x86_64.AppImage`) and opt single apps into
  pre-releases.
- **More reliable update detection (0.6.1).** For rolling tags such as `continuous`,
  AppForge also looks for a version in the release title and selected filename.
  Date versions, underscore-separated versions and names containing product digits
  are handled more reliably. Saved asset patterns stay with the selected variant;
  if it disappears, choose a replacement instead of silently switching files.
- **Checksum fallback.** When versions cannot be compared, AppForge compares your
  installed file with the selected asset's published SHA-256/SHA-512 checksum, if
  available. Matching bytes mean up to date. Different bytes offer the release
  with an explicit warning that version ordering is unknown; review before installing.
  Rolling releases with the same filename version also use this check when possible.
  Ambiguous assets require choosing a file first. Checks never download or execute
  the application itself. Without usable versions or published checksums, set the
  installed version in Edit; choosing an asset alone cannot establish its age.
  See the [0.6.1 release notes](../releases/RELEASE_NOTES_v0.6.1.md).
- **Understands real-world version numbers**: `v1.2.3`, `5.0-1234`, `2024-05-01`, `2.0-rc1`, and so on.
- For nightly-only repositories, choose **Enable pre-releases** in the app's card menu,
  or enable **Include pre-releases when checking for updates** in **Edit information…**.
  If the card says **Pre-releases available**, choosing a nightly release asset now offers
  to enable pre-releases for that app and checks again. A newer eligible build gets the
  normal **Update** button; choosing an asset does not start a download.
  Choose **Use stable releases only** in the card menu to turn the option off again.
  These settings apply to that app only and do not resume paused updates.
  Numbered nightly builds are compared by build number, not commit hash.
- **Update** a single app or use **Update All**.
- **Safe by design.** Downloads go to a hidden temporary file, are validated, and are checksum-verified when the
  release publishes a SHA-256 (GitHub's asset digest, `*.sha256` or `SHA256SUMS`). Only then is the new file swapped
  in atomically. Your app's file name and executable bit are preserved so launchers keep working. A failed, corrupt or
  cancelled download never touches the working version.
- **Background checks and notifications.** While AppForge is open it re-checks apps on your schedule (every 1 to 24
  hours) and notifies you once per new version. Optionally it keeps running in the **system tray** after the window is
  closed.

## Backups and rollback
- Every update keeps the previous version in a hidden `.<name>.backups` folder next to the app.
- **Backups & rollback** (card menu) lists saved versions with version, date and size. **Restore this version**
  swaps one in, and the version you leave is saved first, so a rollback can itself be undone.
- Keep the newest *N* backups per app (default 3, or unlimited). AppForge only ever deletes `.AppImage` files inside
  a `.<name>.backups` folder.

## Application menu integration
- **Add to application menu** creates a standard `.desktop` launcher, so the app shows up in KDE's launcher or the
  GNOME overview and can be pinned. It keeps working without AppForge running.
- The launcher is keyed on the library id, so renaming, changing the icon, moving the file or updating only rewrites
  its contents. **Pins and favourites survive.** The entry is hidden while the file is missing or not executable.
- Choose the shared **Category** (Development, Games, Graphics, Internet, Multimedia, Office, ...) and set
  **environment variables** (`NAME=value`, one per line) per app. They are applied both in the launcher and when you
  press *Launch* inside AppForge.
- AppForge repairs missing or outdated launchers at startup and only deletes `.desktop` files it created itself
  (named `appforge-<id>.desktop` with its own marker).

## Moved or missing files
- Cards for missing, moved or non-executable files are clearly marked, with **Locate file...** and **Make
  executable** actions.
- *Locate file...* first searches for likely matches (same name apart from version and architecture) in the old
  folder, your other apps' folders and common places such as `~/Applications`, `~/Downloads` and `/opt`, and offers
  one-click reconnection.

## AppForge itself
- **Self-update**: AppForge checks its own releases at startup and offers *Update now* or *Later*. The update is
  verified, the old build is kept as a backup, and it is swapped in atomically.
- **What changed after an update**: the first visible launch of each AppForge version
  shows its bundled release notes, including when offline. Closing the popup keeps
  notes enabled for future versions. **Don't show again** disables these popups.
  To restore them, untick **Don't show AppForge release notes after updates** in
  Settings and Save; the current notes open again. Login startup hidden in the tray
  waits until you open AppForge before showing notes.
- **Single instance**: starting AppForge while it is already running just brings the existing window forward.
- **AppForge application menu shortcut**: on first visible launch, AppForge asks
  whether to create its own menu launcher. Choose No to continue without it; the
  question will not repeat. In Settings, tick **Add AppForge to the application menu**
  and Save to add it later, or untick and Save to remove it. This also lets the
  desktop offer "Pin to Task Manager". Existing AppForge-created launchers are
  preserved on upgrade and placed in **Utilities**. When you launch an AppImage
  from a different location, AppForge shows the saved and current paths and asks
  whether to fix the shortcut. **Yes** points it at the new location; **No** leaves
  it unchanged and asks again next launch. Unchanged locations show no repair prompt.
  Removed shortcuts stay removed. Unrelated launchers are never overwritten or deleted.
  This setting is independent of **Start AppForge at login**.
  On KDE Plasma, saved menu-editor rules can override the Utilities category or
  hide AppForge. With the shortcut enabled, open KDE Menu Editor, enable **Show
  hidden entries** in its settings, move AppForge into **Utilities** and save.
  AppForge preserves custom KDE menu rules.
- **Settings** (gear icon to the right of **Add Application**): automatic checks and interval, notifications, tray behaviour,
  login startup and an optional GitHub token to raise the API rate limit.

## Where your data lives

| What | Where |
| --- | --- |
| Library database | `~/.local/share/appforge/library.db` |
| App icons and logs | `~/.local/share/appforge/` |
| AppForge log | `~/.local/share/appforge/appforge.log` |
| Launchers | `~/.local/share/applications/appforge-<id>.desktop` |
| Backups | `.<name>.backups/` next to each app |

Set `APPFORGE_DATA_DIR` to use a throw-away library for experiments. Launchers then go to
`$APPFORGE_DATA_DIR/applications`, so your real menu is never touched.

## Privacy and security

- No telemetry. Network access is to the release APIs and application/checksum download URLs of sources you choose,
  plus AppForge's own releases for self-update.
- AppImages are inspected without being executed.
- Updates are verified (valid file, SHA-256 where published) before replacing anything.
- Only `https://` download links are used.
- Your GitHub token (optional) is only ever sent to `api.github.com`, never to GitLab, Codeberg or self-hosted
  servers. If you save it in Settings it is stored **unencrypted** in the library file (mode 0600). The
  `GITHUB_TOKEN` or `GH_TOKEN` environment variable works too and avoids storing it.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `dlopen(): error loading libfuse.so.2` | `sudo pacman -S fuse2`, or run with `--appimage-extract-and-run`, or set `APPIMAGE_EXTRACT_AND_RUN=1`. |
| `Could not load the Qt platform plugin "xcb"` | `sudo pacman -S xcb-util-cursor` (and `libxcb`, `xcb-util-*` on a minimal install). |
| Blurry or wrong theme under Wayland | Start with `QT_QPA_PLATFORM=wayland` or `=xcb` to compare, and please report it. |
| An app "closes unexpectedly" after launch | AppForge shows the app's output. Full log: `~/.local/share/appforge/logs/<id>.log`. |
| Icon or name not detected | Some AppImages use unsupported compression or the Type 1 format; the file name is used instead. The reason is shown in the Add dialog. |
| `Couldn't reach ...` / rate limit | Check your connection. For GitHub, add a token in Settings (or set `GITHUB_TOKEN`) to raise the limit. |
| Self-hosted source says "not found" | Check the URL and that the repository has public releases. The server must run Forgejo, Gitea or GitLab and be reachable over `https://`. |
| Plasma minimize-to-tray still uses the taskbar | Exit the old AppForge instance from the tray before launching a rebuilt AppImage. Tray mode must be enabled. Check `~/.local/share/appforge/appforge.log` for `KWin minimize observer active for AppForge` or a KWin/D-Bus error. |
| No notifications | Enable them in Settings. Without the tray option AppForge uses `notify-send` (`sudo pacman -S libnotify`). Background availability checks and update completion notify while the window isn't in front. |
| *Checksum mismatch* during an update | The download was discarded and your app is untouched. Retry; if it persists, the release's published checksum is wrong. |
| App missing from the application menu | Use the card menu, *Add to application menu*. The entry is hidden while the file is missing or not executable. Some desktops need a minute (or `kbuildsycoca6`) to notice new launchers. |

## Current limitations

- Linux only.
- Discovery offers manual scans and optional watching of selected discovery folders
  while AppForge is running. New apps still require review/import. Symlink paths are excluded.
- Discovery cancellation takes effect between file reads. Very large individual AppImages can delay it.
- Updates for standalone executables work when a release publishes the **raw binary**; releases that only ship
  `.tar.gz`, `.zip`, `.deb` or `.rpm` show "no matching file".
- Only checksums are verified, not GPG or minisign signatures.
- Login startup requires a desktop that supports XDG autostart; it starts after login, not before it.
