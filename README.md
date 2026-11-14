<p align="center">
  <img src="src/appforge/resources/appforge-512.png" alt="AppForge logo" width="160">
</p>

<h1 align="center">AppForge</h1>

<p align="center">
  <b>A library, launcher and updater for your AppImages and other standalone Linux executables.</b><br>
  Keep every portable app in one tidy window, launch it, put it in your application menu, and update it in one click.
</p>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.5.5-2B63D9">
  <img alt="platform" src="https://img.shields.io/badge/platform-Linux-informational">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Qt" src="https://img.shields.io/badge/Qt-6%20(PySide6)-41cd52">
</p>

---

## Why AppForge?

AppImages are great: download one file, make it executable, run it. But once you have a dozen of them scattered across
`~/Downloads`, `~/Applications` and `/opt`, a few problems show up:

- They don't appear in your application menu, so you can't search for or pin them.
- Nothing tells you when a new version is out, and updating means re-downloading and renaming files by hand.
- If an update breaks something, the old version is gone.

AppForge solves this. You point it at your AppImages (wherever they are, nothing is moved or copied) and it gives you a
modern card-based library with launching, update checks, safe updates with automatic backups, one-click rollback, and
proper application-menu launchers.

**It isn't limited to AppImages.** Any standalone Linux program works too: a single ELF binary (for example a
downloaded CLI tool or game launcher) or a script starting with `#!`. They get the same library card, launcher,
update checks, backups and rollback.

| Supported type | What it is |
| --- | --- |
| AppImage | `.AppImage` files; name, version, description and icon are read from inside the file |
| Linux executable | A single ELF binary, no installer or archive needed |
| Script | A file starting with `#!` (shell, Python, ...) |

For plain executables and scripts, the name and version are taken from the file name (nothing is run to inspect them)
and AppForge shows a generated icon unless you pick one in *Edit*.

Built with **Python**, **PySide6 (Qt 6)** and **SQLite**. Developed on CachyOS / Arch Linux with KDE Plasma, but it
runs on any recent Linux desktop.

## Features

### Application discovery (new in 0.5.5)

See the [0.5.5 release notes](releases/RELEASE_NOTES_v0.5.5.md) and the
[discovery guide](docs/DISCOVERY.md) for the full workflow and limitations.

- Click **Discover apps…** beside the update-check control to scan `~/Applications`, `~/Downloads`,
  `/opt`, or folders you add. Remove any folder you do not want scanned; choices are saved.
- Scans run in a background worker with progress and cancellation. The preview shows application
  name, icon when available, version, format, file location and registration status.
- Check individual results, use **Select all** / **Select none**, then **Import selected**, or use
  **Import all eligible**. A confirmation is required before anything is registered.
- **Ignore selected** remembers unwanted file paths across scans and restarts. **Reset ignored files**
  makes them eligible again. Registered and ignored results remain visible but cannot be imported.
- Discovery reads files without running or changing them. It skips all symlinks (including folder
  aliases), hidden `.<name>.backups` directories, and non-executable ELF binaries/scripts. AppImages
  can be discovered without an executable bit; the existing **Make executable** action remains available.
- Overlapping folders and hard links are deduplicated. Imports recheck file identity and reject
  changed, missing or already-registered files. Desktop-menu integration is optional.
- Cancelling a scan retains any results found so far. Closing during a scan requests cancellation and
  waits for the current metadata read to finish. Bulk imports can be stopped between applications.

### Library and launcher
- **Add apps from anywhere**: by file picker or by dragging `.AppImage` files onto the window. Files are never
  moved or copied. To add a plain executable or script, choose *All files* in the file picker.
- **Reads the AppImage without running it**: name, version, description and icon are extracted from inside the file.
  File names such as `Dolphin-Emu-5.0-x86_64.AppImage` are cleaned up to a sensible suggested name ("Dolphin Emu").
- **Application cards** show icon, name, version, format, update status and file location.
- **Launch from a card.** Apps are started detached, so they keep running if you close AppForge. If an app exits
  right after launch, AppForge shows its output and keeps a log.
- **Search, categories, filters and sorting**: filter by category or by status (updates available, needs attention,
  no update source) and sort by name, date added or update status.
- **Light and dark theme** that follows your system.
- **Standalone executables too**: besides AppImages you can add any single Linux program (ELF binary) or `#!`
  script. They get cards, launchers, update checks, backups and rollback just like AppImages. For updates, the
  release must publish the raw binary (see [Current limitations](#current-limitations)).

### Updates
- **Link a repository** to any app and AppForge checks its releases for a newer version. Supported sources:
  - **GitHub**, **GitLab.com** and **Codeberg**
  - **Any self-hosted Forgejo, Gitea or GitLab server**, e.g. `https://git.example.dev/owner/repo`
- **Smart release matching.** AppForge picks the right AppImage from a release and ignores source archives, `.zsync`
  files, checksums and other CPU architectures. If several files look equally good it asks once and remembers your
  choice. You can also set a file pattern per app (for example `MyApp-*-x86_64.AppImage`) and opt single apps into
  pre-releases.
- **Understands real-world version numbers**: `v1.2.3`, `5.0-1234`, `2024-05-01`, `2.0-rc1`, and so on.
- **Update** a single app or use **Update All**.
- **Safe by design.** Downloads go to a hidden temporary file, are validated, and are checksum-verified when the
  release publishes a SHA-256 (GitHub's asset digest, `*.sha256` or `SHA256SUMS`). Only then is the new file swapped
  in atomically. Your app's file name and executable bit are preserved so launchers keep working. A failed, corrupt or
  cancelled download never touches the working version.
- **Background checks and notifications.** While AppForge is open it re-checks apps on your schedule (every 1 to 24
  hours) and notifies you once per new version. Optionally it keeps running in the **system tray** after the window is
  closed.

### Backups and rollback
- Every update keeps the previous version in a hidden `.<name>.backups` folder next to the app.
- **Backups & rollback** (card menu) lists saved versions with version, date and size. **Restore this version**
  swaps one in, and the version you leave is saved first, so a rollback can itself be undone.
- Keep the newest *N* backups per app (default 3, or unlimited). AppForge only ever deletes `.AppImage` files inside
  a `.<name>.backups` folder.

### Application menu integration
- **Add to application menu** creates a standard `.desktop` launcher, so the app shows up in KDE's launcher or the
  GNOME overview and can be pinned. It keeps working without AppForge running.
- The launcher is keyed on the library id, so renaming, changing the icon, moving the file or updating only rewrites
  its contents. **Pins and favourites survive.** The entry is hidden while the file is missing or not executable.
- Choose the **menu category** (Development, Games, Graphics, Internet, Multimedia, Office, ...) and set
  **environment variables** (`NAME=value`, one per line) per app. They are applied both in the launcher and when you
  press *Launch* inside AppForge.
- AppForge repairs missing or outdated launchers at startup and only deletes `.desktop` files it created itself
  (named `appforge-<id>.desktop` with its own marker).

### Moved or missing files
- Cards for missing, moved or non-executable files are clearly marked, with **Locate file...** and **Make
  executable** actions.
- *Locate file...* first searches for likely matches (same name apart from version and architecture) in the old
  folder, your other apps' folders and common places such as `~/Applications`, `~/Downloads` and `/opt`, and offers
  one-click reconnection.

### AppForge itself
- **Self-update**: AppForge checks its own releases at startup and offers *Update now* or *Later*. The update is
  verified, the old build is kept as a backup, and it is swapped in atomically.
- **Single instance**: starting AppForge while it is already running just brings the existing window forward.
- **Pin to taskbar**: AppForge writes its own launcher so the desktop can offer "Pin to Task Manager".
- **Settings** (gear icon, bottom-right): automatic checks and interval, notifications, tray behaviour, and an
  optional GitHub token to raise the API rate limit.

## Install

### AppImage (recommended)

Download the latest `AppForge-<version>-x86_64.AppImage` from the
[Releases](https://github.com/Thilen03/AppForge/releases) page, then:

```bash
chmod +x AppForge-*-x86_64.AppImage
./AppForge-*-x86_64.AppImage
```

The AppImage bundles Python and Qt, so you need neither. If it complains about FUSE, see
[Troubleshooting](#troubleshooting).

### From source

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Thilen03/AppForge.git
cd AppForge
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src python -m appforge
```

On Arch/CachyOS you may need Qt's xcb helper library (normally already present with Plasma):
`sudo pacman -S xcb-util-cursor`.

## Quick start

1. Use **Discover apps…** to find and review applications in selected folders, or click **Add Application** (or drag an AppImage onto the window) and review the detected name, version and icon.
   For a plain binary or script, pick it with the *All files* filter.
2. Optionally paste an **update source**, such as `https://github.com/owner/repo` or
   `https://git.example.dev/owner/repo`.
3. Leave **Add to the application menu** ticked if you want a launcher in your desktop menu.
4. Launch it from its card. When an update is available, press **Update** on the card or **Update All**.

### Supported update sources

| Source | Example URL |
| --- | --- |
| GitHub | `https://github.com/owner/repo` (or just `owner/repo`) |
| GitLab.com | `https://gitlab.com/group/project` (subgroups work) |
| Codeberg | `https://codeberg.org/owner/repo` |
| Self-hosted Forgejo / Gitea / GitLab | `https://git.example.dev/owner/repo` |

You can paste the repository URL, a release page URL, a `.git` URL or `git@host:owner/repo.git`; AppForge trims it
down to the repository. Self-hosted servers must use `https://`. AppForge only talks to the official release APIs and
never scrapes web pages.

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

- No telemetry. The only network traffic is to the release APIs of the sources you linked (and to AppForge's own
  releases for self-update).
- AppImages are inspected without being executed.
- Updates are verified (valid file, SHA-256 where published) before replacing anything.
- Only `https://` download links are used.
- Your GitHub token (optional) is only ever sent to `api.github.com`, never to GitLab, Codeberg or self-hosted
  servers. If you save it in Settings it is stored **unencrypted** in the library file (mode 0600). The
  `GITHUB_TOKEN` or `GH_TOKEN` environment variable works too and avoids storing it.

## Building the AppImage

```bash
./scripts/build_appimage.sh
# -> dist/AppForge-<version>-x86_64.AppImage
```

The script creates a build virtualenv, runs PyInstaller (bundling Python and Qt), assembles an AppDir and runs
`appimagetool` (downloaded on first use into `build/tools/`, or use your own on `PATH`). It needs `squashfs-tools`
(`sudo pacman -S squashfs-tools`) and `curl`.

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
| No notifications | Enable them in Settings. Without the tray option AppForge uses `notify-send` (`sudo pacman -S libnotify`). They only appear for updates found by background checks while the window isn't in front. |
| *Checksum mismatch* during an update | The download was discarded and your app is untouched. Retry; if it persists, the release's published checksum is wrong. |
| App missing from the application menu | Use the card menu, *Add to application menu*. The entry is hidden while the file is missing or not executable. Some desktops need a minute (or `kbuildsycoca6`) to notice new launchers. |

## Current limitations

- Linux only.
- Discovery is user-initiated; it does not monitor folders continuously. Symlink paths are excluded.
- Discovery cancellation takes effect between file reads. Very large individual AppImages can delay it.
- Updates for standalone executables work when a release publishes the **raw binary**; releases that only ship
  `.tar.gz`, `.zip`, `.deb` or `.rpm` show "no matching file".
- Only checksums are verified, not GPG or minisign signatures.
- AppForge does not yet start automatically at login.
