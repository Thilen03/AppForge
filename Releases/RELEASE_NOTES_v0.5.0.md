# AppForge v0.5.0 – Expanded Application Support & Update Management

AppForge 0.5.0 is a major update that expands application format support, introduces additional Git hosting providers, and adds background update management, notifications, categories, filtering, and a dedicated settings interface.

This release moves AppForge beyond AppImage-only management, making it possible to manage standalone Linux executables and scripts as well.

## ✨ New Features

### 🌐 Multiple Update Sources

AppForge now supports three Git hosting providers:

- **GitHub**
- **GitLab.com**
- **Codeberg**

Features include:

- Support for GitLab nested groups and projects.
- Multiple repository URL formats, including HTTPS, SSH, and shortened repository paths.
- Automatic provider detection.
- Provider-specific error messages for invalid repositories and missing projects.
- Release asset discovery across supported providers.
- Secure token handling: GitHub credentials are only sent to GitHub, never to GitLab or Codeberg.
- Non-HTTPS download links are ignored for safety.

### ⚙️ Standalone Executable Support

AppForge can now manage standalone Linux executables and scripts in addition to AppImages.

Supported formats:

- AppImage
- ELF Linux executables
- Executable scripts using a shebang (`#!`)

Features include:

- Import executable files directly into your library.
- Automatic file format detection.
- Metadata extraction without executing imported programs.
- Application launching through the existing library.
- Backup and rollback support for executables.
- Download validation before replacing installed files.
- Rejection of invalid downloads, including HTML error pages.
- Improved release asset selection for Linux executables.
- Exclusion of Windows, macOS, BSD files, archives, packages, and checksum files when selecting standalone executable updates.

Executable backups use `.bak` files, while AppImage backups retain their `.AppImage` extension.

### 🗂️ Categories, Filtering & Sorting

A new organization system makes managing larger application libraries easier.

Features include:

- Assign custom categories to applications.
- Automatically detect categories from application `.desktop` metadata.
- Default to **Other** when no category is available.
- Preserve manually selected categories during metadata refreshes.
- Filter applications by category.
- Filter by update status:
  - All applications
  - Updates available
  - Needs attention
  - No update source
- Sort applications by:
  - Name
  - Recently added
  - Update status
- Search applications by both name and category.

The filter controls automatically disappear when the library is empty.

### 🔄 Background Update Checks

AppForge can now check for updates automatically while running in the background.

Features include:

- Background checking timer that runs every 10 minutes.
- Configurable update-check intervals:
  - 1 hour
  - 3 hours
  - 6 hours
  - 12 hours
  - 24 hours
- Default update interval of 6 hours.
- Only checks applications whose last update check is older than the configured interval.
- Automatically skips background checks while updates or Update All operations are running.
- Background checking is disabled when automatic checks are turned off.
- Background timer is restricted to normal application operation, not test runs.

### 🔔 Update Notifications

AppForge now notifies you when new application updates are discovered.

Features include:

- Notifications when a new update becomes available.
- Each version is announced only once.
- Uses system tray notifications when available.
- Falls back to `notify-send` when the tray icon is unavailable.
- Avoids unnecessary notifications when AppForge is already in the foreground.
- Avoids notifications for manually triggered update checks.
- Combines multiple available updates into a single notification.
- Displays up to four application names, followed by a count of additional updates.
- Notification text is sanitized and truncated for safety.

### 🖥️ System Tray Integration

AppForge can optionally continue running in the system tray after its main window is closed.

Features include:

- Optional **Keep running in the system tray** setting.
- Closing the window hides it instead of exiting.
- Tray menu actions:
  - Open AppForge
  - Check for updates now
  - Quit AppForge
- Proper application shutdown when selecting Quit.
- Confirmation before quitting if a download is currently running.
- Tray functionality is disabled automatically when the desktop environment does not provide a system tray.

### ⚙️ New Settings Dialog

A dedicated Settings dialog is now available from the main window header.

Settings include:

- Enable or disable automatic update checks.
- Configure the automatic update-check interval.
- Enable or disable update notifications.
- Enable or disable system tray operation.
- Configure an optional GitHub API token.

Token handling:

- Tokens can be stored in the local application database.
- Database file permissions are restricted to the owner (`0600`).
- Supports the `GITHUB_TOKEN` and `GH_TOKEN` environment variables as fallbacks.
- Shows when an environment variable is being used instead of a saved token.
- Rejects tokens containing spaces or control characters.

**Note:** Stored tokens are not encrypted. Protect your local library database accordingly.

## 🔧 Improvements to Existing Features

### Add & Edit Dialogs

- Renamed **AppImage file** to **File**, reflecting the expanded format support.
- Renamed **GitHub repository** to **Update source**.
- Updated helper text to explain the supported hosting providers.
- Improved file validation messages to cover programs and scripts, not just AppImages.

### Update System

- Improved release asset detection for standalone executables.
- Added format-aware validation before installation.
- Preserved existing AppImage asset scoring behaviour.
- Improved provider-specific error handling.
- Automatic startup checks now respect the automatic-check setting.

### Interface & Theming

- Improved light and dark theme styling for combo boxes.
- Added category, status, and sorting controls.
- Added a dedicated Settings button.
- Improved application library organization.

### Version Information

- Updated application version to `0.5.0`.
- Updated version metadata in `__init__.py` and `pyproject.toml`.

## 🗄️ Database & Compatibility

- No database migration is required.
- Existing application databases remain compatible.
- The existing `github_repo` database column now stores update-source URLs for GitHub, GitLab, and Codeberg.
- Category and notification information are stored in existing JSON metadata.
- Settings use the existing settings table.
- Existing function signatures remain backwards compatible, with new optional parameters for format-aware operations.
- Existing GitHub repository parsing behaviour is preserved.
- Existing AppImage backup validation paths remain compatible with previous tests.

## 🧪 Testing & Verification

- 42 new Phase 5 tests added.
- 88 core tests passed in the development sandbox.
- Existing backup and launcher tests included in verification.
- GUI test coverage was extended with five additional tests.

**Testing limitations:**

- The UI was only smoke-tested against a stub Qt environment.
- GUI tests were not run with real Qt.
- System tray functionality has not yet been verified on a real desktop.
- Notifications have not yet been verified on a real system.
- GitLab and Codeberg integrations have not yet been tested against live repositories.

## 📦 Files & Architecture

New modules include:

- `core/settings.py`
- `core/organize.py`
- `core/formats/executable.py`
- `core/updates/providers.py`
- `services/notifier.py`
- `ui/settings_dialog.py`
- `ui/tray.py`
- `tests/test_phase5.py`

Existing modules were updated across the core, services, UI, application startup, and test infrastructure.

## 🚧 Not Included Yet

The following features remain planned:

- Automatic unpacking of archives containing standalone executables.
- Support for self-hosted GitLab and Forgejo servers.
- Start AppForge automatically at login.
- Secure API token storage through the system keyring.
- GPG and minisign signature verification.
- Rebuilding and publishing the AppForge AppImage for this release.

## 🎯 Release Summary

AppForge 0.5.0 significantly expands the application's capabilities.

With support for multiple Git hosting providers, standalone Linux executables, background update checks, notifications, system tray operation, and improved library organization, AppForge is becoming a more complete application management solution for Linux.

**Manage your applications. Automate your updates. Stay in control.**
