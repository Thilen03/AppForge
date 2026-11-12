# AppForge

**A modern AppImage manager for Linux.**

AppForge makes managing standalone Linux applications easier. Import AppImages from anywhere on your system, organize them in a clean graphical library, track updates through GitHub Releases, and install new versions safely without losing the ability to roll back.

Instead of manually hunting for updates, downloading files, and replacing applications yourself, AppForge brings everything together in one place.

### ✨ Features

- **AppImage Library** – Import AppImages from anywhere without moving or copying the original files. Manage your applications through a searchable graphical library.
- **GitHub Integration** – Associate applications with GitHub repositories and automatically check their latest releases.
- **Automatic Update Detection** – See which applications are up to date, have updates available, or encountered an issue.
- **One-Click Updates** – Update individual applications or your entire library with Update All.
- **Safe Installation** – Validate downloaded AppImages, verify available SHA-256/SHA-512 checksums, and use atomic file replacement to protect existing installations.
- **Automatic Backups** – Keep previous versions of your applications so updates don't have to be permanent.
- **Rollback & Restore** – Restore previous versions with a built-in backup manager. Rollbacks are reversible.
- **Desktop Integration** – Generate desktop entries for easier access through your Linux application launcher.
- **Application Management** – Rename and move applications while maintaining their integration.
- **Custom Update Settings** – Include pre-releases and configure release asset matching for individual applications.
- **Modern Interface** – A clean graphical interface with light and dark themes, drag-and-drop importing, and clear update status indicators.

### 🛡️ Designed with safety in mind

AppForge is built around the idea that updating software shouldn't mean risking a working installation.

- Existing applications are backed up before replacement.
- Downloads are validated before installation.
- Checksums are verified when available.
- Updates use atomic replacement to avoid partially installed files.
- Failed updates leave the existing installation intact.
- Previous versions can be restored at any time.

### 🛠️ Built with

- **Python**
- **PySide6 / Qt** – Graphical interface
- **SQLite** – Local application library and settings
- **GitHub Releases API** – Release and update information
- **PySquashfsImage** – AppImage metadata and icon extraction
- **pytest** – Automated testing

### 🚧 Development status

AppForge is under active development.

**Current version: v0.4.0**

AppForge currently supports AppImage library management, GitHub release integration, automatic update detection, safe installation, backups, rollback, desktop entry generation, and application rename/move handling.

Planned improvements include:

- Support for additional application formats
- Background update checks and notifications
- Additional release providers and application categories
- Dedicated settings interface

### 🐧 Platform

Currently developed and tested primarily on Ubuntu 24.04. Testing on other Linux distributions and desktop environments is ongoing.

### 📌 Project goal

AppForge aims to make managing AppImages feel like managing applications through a traditional package manager, while keeping the flexibility and portability that make AppImages useful.

**Manage your apps. Keep them updated. Stay in control.**
