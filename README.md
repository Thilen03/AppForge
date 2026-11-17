<p align="center">
  <img src="src/tuxshelf/resources/tuxshelf-512.png" alt="TuxShelf logo" width="160">
</p>

<h1 align="center">TuxShelf</h1>

<p align="center">
  <b>A library, launcher and updater for your AppImages and other standalone Linux executables.</b><br>
  Keep every portable app in one tidy window, launch it, put it in your application menu, and update it in one click.
</p>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.6.7-2B63D9">
  <img alt="platform" src="https://img.shields.io/badge/platform-Linux-informational">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Qt" src="https://img.shields.io/badge/Qt-6%20(PySide6)-41cd52">
</p>

> **AppForge is now TuxShelf!** Starting with version **0.6.6**, the project has
> a new name to give it a more distinctive identity and make it easier to tell
> apart from other applications. It's the same portable Linux app manager,
> with your existing library and settings preserved.

TuxShelf keeps portable Linux apps in one library: launch them, add desktop-menu
shortcuts, check for updates and restore previous versions. It supports AppImages,
standalone ELF binaries and `#!` scripts. Existing local files stay where they are;
TuxShelf reads their metadata without running them.

## What's new in 0.6.7

- **Custom icons from image links.** Paste a direct HTTP/HTTPS image URL when
  adding or editing an application. TuxShelf downloads and previews the image,
  then keeps the saved icon available offline in its managed cache.
- Downloads run in the background and can be cancelled. Invalid images and
  oversized downloads leave your existing icon unchanged.
- Release links, self-updates and publishing checks use the renamed TuxShelf
  GitHub repository.
- AppImage builds use the build environment's Python directly, avoiding broken
  launcher paths after the project folder is renamed.

See the [full 0.6.7 release notes](releases/RELEASE_NOTES_v0.6.7.md) and
[custom icon guide](docs/USAGE.md#custom-application-icons).

## Features

- **Add locally or download from a link.** Choose a release file and save it to a
  discovery folder, or add an existing file by browsing, discovery or AppImage drag-and-drop.
  Search discovery results and click column headings to sort them. Watch selected
  discovery folders and review new arrivals before adding them.
- **Keep apps updated.** GitHub, GitLab.com, Codeberg and self-hosted Forgejo/Gitea/GitLab
  sources; embedded AppImage source suggestions, release-asset matching, optional nightlies,
  per-app pause/skip controls and Update All.
- **Update safely.** File validation, published SHA-256/SHA-512 checksums, atomic
  replacement, automatic backups and rollback. New downloads never overwrite existing files.
- **Organize and launch.** Search, categories, filters, sorting, favorites, desktop-menu
  shortcuts, custom icons and named launch profiles with their own environment,
  arguments, working directory and terminal settings.
- **Manage your library.** App details, in-app release notes, export/import, storage
  overview and backup cleanup, plus tools to locate moved files and fix execute permissions.
  Select several apps to change categories or update settings, create menu shortcuts,
  or remove library entries together.
- **Stay in the background.** Scheduled checks, notifications, optional tray mode and
  login startup, light/dark themes, customizable card badge colors and TuxShelf self-updates.
  Read bundled release notes after each TuxShelf update, with an option to hide them.
  Choose whether to add TuxShelf to Utilities on first launch or in Settings. If its
  AppImage moves, TuxShelf asks before updating the shortcut to the new location.

## Install

The application and GitHub repository are now named **TuxShelf**. Older releases
retain their original filenames. See the
[upgrade notes](docs/USAGE.md#upgrading-from-an-earlier-name) for data compatibility.

Download `TuxShelf-<version>-x86_64.AppImage` from
[GitHub Releases](https://github.com/Thilen03/TuxShelf/releases), then:

```bash
chmod +x TuxShelf-*-x86_64.AppImage
./TuxShelf-*-x86_64.AppImage
```

Run these commands in the folder containing the downloaded AppImage. Python and Qt
are bundled. If FUSE is unavailable, launch with `--appimage-extract-and-run`; see
[troubleshooting](docs/USAGE.md#troubleshooting) for other startup issues.

## Quick start

1. Click **Add Application** and choose **Add a local file…** or **Download from a link…**.
   For a local binary or script, select *All files* in the file picker. **Discover apps…**
   scans all saved discovery folders for AppImages and common Linux executables,
   skipping unrelated files such as ROMs. Checkboxes control background watching only.
2. For downloads, paste a repository/release link, select a file and destination, then
   review the Add form. **Add folder…** saves a new destination for discovery too.
   If the selected file already exists, TuxShelf checks it and continues to the Add
   form automatically, including after cancellation or restarting TuxShelf.
3. Review the name, icon, category and optional **Add to the application menu** choice.
   Use **Change icon…** for a local image or **Image link…** to download a custom icon
   from a direct HTTP/HTTPS image URL (up to 10 MB and 16 million pixels). Both options
   are also available when editing an app. Saved icons stay in TuxShelf’s icon cache;
   **Use default** restores the original icon or a placeholder.
   Local AppImages may suggest an update-source repository; review, change or clear it.
4. Launch from the card; its arrow selects or edits launch profiles.
   Use **Update** or **Update All** when updates are available;
   **Backups & rollback** restores an earlier version.

For nightlies, choose **Enable pre-releases** in the app's card menu. Choosing an
excluded nightly asset also offers to enable them. Selecting an asset checks for an
update; downloading starts when you choose **Update**.

## Supported sources

| Source | Example |
| --- | --- |
| GitHub | `https://github.com/owner/repo` or `owner/repo` |
| GitLab.com | `https://gitlab.com/group/project` (subgroups supported) |
| Codeberg | `https://codeberg.org/owner/repo` |
| Self-hosted Forgejo / Gitea / GitLab | `https://git.example.dev/owner/repo` |

Repository and release links are supported; self-hosted sources require HTTPS.
TuxShelf uses release APIs, not website scraping. Downloads and updates require an
AppImage or raw executable; archives and packages are not unpacked.

## Documentation

| Topic | Guide |
| --- | --- |
| Everyday use, tray/startup, backups, data locations and troubleshooting | [Using TuxShelf](docs/USAGE.md) |
| Download from a repository | [Downloading applications](docs/DOWNLOADING.md) |
| Scan folders and import existing apps | [Discovery](docs/DISCOVERY.md) |
| Shared library/desktop-menu categories | [Categories](docs/CATEGORIES.md) |
| Launch profiles, arguments, working directories and terminal launches | [Launch options](docs/LAUNCH_OPTIONS.md) |
| Pause updates and skip versions | [Update controls](docs/UPDATE_CONTROLS.md) |
| Export and import configuration | [Library transfer](docs/LIBRARY_TRANSFER.md) |
| Measure storage and clean up backups | [Storage](docs/STORAGE.md) |

## Privacy and limitations

No telemetry. Network access is limited to release APIs and download/checksum URLs
for chosen sources, TuxShelf's own releases, and custom image links you choose.
Files are inspected without execution; checksums are verified where published,
but GPG/minisign signatures are not.

An optional GitHub token is sent only to `api.github.com`. A token saved in Settings
is stored **unencrypted** in the local library database (mode 0600); `GITHUB_TOKEN`
or `GH_TOKEN` avoids storing it there.

Linux only. Discovery supports manual scans and optional folder watching while TuxShelf
is running; symlink paths are excluded. Tray/login behavior
depends on desktop support. If neither usable versions nor published checksums are
available, TuxShelf cannot determine whether an update is needed. Different
checksums identify different files, not which version is newer.

## Development

Built with Python 3.10+, PySide6 (Qt 6) and SQLite.

<details>
<summary>Run from source, build and test</summary>

```bash
git clone https://github.com/Thilen03/TuxShelf.git TuxShelf
cd TuxShelf
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src python -m tuxshelf
```

On Arch/CachyOS, Qt may also need `xcb-util-cursor`.

Build the AppImage with `./scripts/build_appimage.sh`. It uses PyInstaller and
appimagetool, requires `squashfs-tools` and `curl`, and writes
`dist/TuxShelf-<version>-x86_64.AppImage`.
The build invokes pip and PyInstaller through the build environment’s Python, so
old launcher paths left by renaming the project folder do not break the build.

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest -q -ra
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m tuxshelf --selftest
```

Real AppImage fixtures need appimagetool and squashfs-tools. Set `APPIMAGETOOL` to
choose the tool and `APPIMAGE_RUNTIME_FILE` for an offline local Type 2 runtime.
Socket-dependent tests report skips on restricted hosts. Use `TUXSHELF_DATA_DIR`
for a temporary library and isolated desktop launchers.

See the [integration verification report](docs/PHASE_7_PLAN.md) and
[publishing guide](docs/PUBLISHING.md). Automated checks do not replace manual
testing of the final AppImage.

</details>
