# AppForge 0.5.7

## New features

- Read release notes inside AppForge before updating. Open **Release notes…** from
  an application's card menu or details view after checking for updates, or from
  the **Update All** confirmation.
- See the release version, title, publication date, stable or prerelease status,
  and formatted description. Follow links or open the original release page in
  your browser.
- Release notes work with GitHub, GitLab, Codeberg and self-hosted Forgejo/Gitea/
  GitLab sources using their existing release APIs.
- Transfer your application library configuration between Linux installations
  with **Export Library…** and **Import Library…** in Settings. The JSON export
  includes application details, repositories, categories, update and menu
  preferences, and icons.
- Preview and select applications before importing. Duplicate files are skipped;
  conflicting IDs can be assigned new IDs without changing existing entries.
  Missing applications keep their configuration for reconnection with **Locate
  file…**. Import summaries show successes, missing files, skips and errors.

## Improvements

- Notes are saved for the selected repository and release, so cached descriptions
  remain available after restarting AppForge. Refresh runs in the background and
  keeps cached text visible if the provider cannot be reached.
- Missing descriptions have a clear explanation. Reading notes never installs an
  update or changes the installed application.
- Export and import file work runs in the background with cancellation. Completed
  imports are kept when an operation is stopped. Application files are never
  executed, moved or changed by a transfer.
- AppForge access tokens and runtime update data are excluded from exports.
  Per-application environment variables are optional and disabled by default on
  both export and import.

## Known issues

- Embedded images and raw HTML are disabled in release descriptions. HTTP(S)
  links can be opened in your browser.
- If an older release is no longer among the provider's recent API results, use
  the original release page or check for updates again.
- Library exports contain configuration and icons, not application files or
  backups. Copy applications separately, then use Locate file if their paths
  differ. Global Settings preferences are not transferred. Exports are limited
  to 32 MiB and 10,000 applications.

## Installation/upgrade instructions

- Existing libraries need no database migration. Older records load descriptions
  when their release notes are first opened, or during the next update check.
