"""Library service: the only entry point the UI uses to change application data.

It is deliberately free of Qt so it can be unit-tested and reused (CLI, background updater …).
"""
from __future__ import annotations

import enum
import logging
import os
import shutil
import time
from pathlib import Path

from .database import Database, DuplicatePathError
from .desktop import MENU_CATEGORIES, MENU_CATEGORY_KEY, DesktopError, DesktopService, SyncReport
from .envvars import ENV_KEY, EnvVarError, validate_pair
from .formats import AppMetadata, FormatError, detect_format, get_format
from .models import AppEntry, UpdateStatus
from .organize import CATEGORY_KEY, clean_category
from .relocate import find_candidates
from .updates.providers import SUPPORTED_HINT, parse_source

log = logging.getLogger(__name__)


class LibraryError(Exception):
    """A user-presentable problem (invalid input, duplicate, …)."""


def _check_menu_category(value: str | None) -> str | None:
    value = (value or "").strip() or None
    if value is not None and value not in {k for k, _ in MENU_CATEGORIES}:
        raise LibraryError(f"“{value}” is not an application-menu category.")
    return value


def _check_env(env) -> dict[str, str]:
    """Validate a ``{name: value}`` mapping from the UI; raises LibraryError."""
    out: dict[str, str] = {}
    try:
        for k, v in dict(env or {}).items():
            name, value = validate_pair(str(k), str(v))
            out[name] = value
    except EnvVarError as exc:
        raise LibraryError(str(exc)) from exc
    return out


class FileState(enum.Enum):
    OK = "ok"
    MISSING = "missing"
    NOT_A_FILE = "not_a_file"
    NOT_EXECUTABLE = "not_executable"


def normalize_path(path: str | os.PathLike) -> str:
    """Absolute path *without* resolving symlinks, so the user's chosen location is preserved."""
    return os.path.abspath(os.path.expanduser(str(path)))


def inspect_file(path: str | os.PathLike) -> AppMetadata:
    """Detect the format of ``path`` and read its metadata. Safe to call from a worker thread."""
    p = Path(normalize_path(path))
    if not p.exists():
        raise LibraryError(f"File not found: {p}")
    if not p.is_file():
        raise LibraryError("That path is not a file.")
    fmt = detect_format(p)
    if fmt is None:
        raise LibraryError("AppForge can't use this file. Choose an AppImage, a Linux program (ELF binary) "
                           "or a script that starts with #!.")
    try:
        return fmt.extract_metadata(p)
    except FormatError as exc:
        raise LibraryError(str(exc)) from exc


def normalize_repo(text: str | None) -> str | None:
    """Return the canonical repository URL (GitHub, GitLab or Codeberg), ``None`` for blank input,
    or raise LibraryError."""
    if text is None or not text.strip():
        return None
    ref = parse_source(text)
    if ref is None:
        raise LibraryError(f"Enter a repository like {SUPPORTED_HINT}.")
    return ref.url


ICON_EXTS = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".bmp", ".ico", ".xpm")
MAX_ICON_BYTES = 10 * 1024 * 1024
SETTING_DESKTOP_DEFAULT = "desktop_default"   # "1"/"0": pre-tick "Add to the application menu" when adding
DESKTOP_FLAG = "desktop_entry"                # entry.metadata key: this app has an AppForge launcher


def file_state(entry: AppEntry) -> FileState:
    p = Path(entry.path)
    if not p.exists():
        return FileState.MISSING
    if not p.is_file():
        return FileState.NOT_A_FILE
    if not os.access(p, os.X_OK):
        return FileState.NOT_EXECUTABLE
    return FileState.OK


class LibraryService:
    def __init__(self, db: Database, icons_dir: Path, desktop: DesktopService | None = None):
        self.db = db
        self.icons_dir = Path(icons_dir)
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.desktop = desktop or DesktopService()   # resolves the applications dir lazily

    # -- queries ------------------------------------------------------------------------
    def list_applications(self) -> list[AppEntry]:
        return self.db.list_all()

    def get(self, app_id: str) -> AppEntry | None:
        return self.db.get(app_id)

    def find_by_path(self, path: str) -> AppEntry | None:
        return self.db.find_by_path(normalize_path(path))

    # -- commands -----------------------------------------------------------------------
    def add_application(
        self,
        path: str,
        name: str | None = None,
        github_repo: str | None = None,
        metadata: AppMetadata | None = None,
        custom_icon: str | None = None,
        integrate_desktop: bool = False,
        menu_category: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> AppEntry:
        """Add an application. ``integrate_desktop`` also creates its application-menu launcher;
        a failure there never fails the add – check :meth:`desktop_enabled` on the result."""
        norm = normalize_path(path)
        if self.db.find_by_path(norm):
            raise LibraryError("This application is already in your library.")
        menu_category = _check_menu_category(menu_category)
        env_vars = _check_env(env_vars)
        md = metadata or inspect_file(norm)
        entry = AppEntry(
            name=(name or "").strip() or md.name_suggestion,
            path=norm,
            format=md.format_id,
            installed_version=md.version,
            github_repo=normalize_repo(github_repo),
            description=md.description,
            metadata={**md.extra, "warnings": md.warnings},
        )
        if menu_category:
            entry.metadata[MENU_CATEGORY_KEY] = menu_category
        if env_vars:
            entry.metadata[ENV_KEY] = env_vars
        entry.icon_path = self._store_icon(entry.id, md)
        if custom_icon:
            try:
                entry.icon_path = self._store_custom_icon(entry.id, custom_icon, entry.icon_path)
            except LibraryError:
                self._remove_icon(entry.icon_path)
                raise
            entry.metadata["custom_icon"] = True
        try:
            self.db.add(entry)
        except DuplicatePathError as exc:
            self._remove_icon(entry.icon_path)
            raise LibraryError("This application is already in your library.") from exc
        if integrate_desktop:
            try:
                entry = self.set_desktop_integration(entry.id, True)
            except LibraryError as exc:
                log.warning("Added %s but couldn't create its launcher: %s", entry.name, exc)
        return entry

    def update_application(
        self,
        app_id: str,
        *,
        name: str | None = None,
        path: str | None = None,
        github_repo: str | None = ...,  # type: ignore[assignment]  (Ellipsis = leave unchanged)
        installed_version: str | None = ...,  # type: ignore[assignment]
        settings: dict | None = None,
        icon: str | None = ...,  # type: ignore[assignment]  (path = set custom, None = reset to built-in)
        category: str | None = ...,  # type: ignore[assignment]  (text = set, None/blank = automatic)
        menu_category: str | None = ...,  # type: ignore[assignment]  (freedesktop key; None = automatic)
        env_vars: dict[str, str] | None = ...,  # type: ignore[assignment]  (empty/None = none)
    ) -> AppEntry:
        entry = self._require(app_id)
        if menu_category is not ...:
            chosen_menu = _check_menu_category(menu_category)
            if chosen_menu:
                entry.metadata[MENU_CATEGORY_KEY] = chosen_menu
            else:
                entry.metadata.pop(MENU_CATEGORY_KEY, None)
        if env_vars is not ...:
            checked_env = _check_env(env_vars)
            if checked_env:
                entry.metadata[ENV_KEY] = checked_env
            else:
                entry.metadata.pop(ENV_KEY, None)
        if category is not ...:
            chosen = clean_category(category)
            if chosen:
                entry.metadata[CATEGORY_KEY] = chosen
            else:
                entry.metadata.pop(CATEGORY_KEY, None)
        if icon is not ...:
            if icon:
                entry.icon_path = self._store_custom_icon(entry.id, icon, entry.icon_path)
                entry.metadata["custom_icon"] = True
            else:
                self._reset_icon(entry)
        if name is not None:
            if not name.strip():
                raise LibraryError("The application name can't be empty.")
            entry.name = name.strip()
        if path is not None and normalize_path(path) != entry.path:
            new_path = normalize_path(path)
            other = self.db.find_by_path(new_path)
            if other and other.id != entry.id:
                raise LibraryError("Another library entry already uses that file.")
            fmt = detect_format(Path(new_path))
            if fmt is None:
                raise LibraryError("That file isn't an AppImage, Linux program or script AppForge can use.")
            entry.path, entry.format = new_path, fmt.id
        if github_repo is not ...:
            new_repo = normalize_repo(github_repo)
            if new_repo != entry.github_repo:
                entry.github_repo = new_repo
                self._reset_update_state(entry)
        if installed_version is not ...:
            new_version = (installed_version or "").strip() or None
            if new_version != entry.installed_version:
                entry.installed_version = new_version
                entry.metadata["installed_version_source"] = "manual"
                self._reset_update_state(entry)
        if settings:
            # per-app update settings: include_prereleases (bool), asset_pattern (glob or None)
            for key, val in settings.items():
                if val in (None, "", False):
                    entry.metadata.pop(key, None)
                else:
                    entry.metadata[key] = val.strip() if isinstance(val, str) else val
        try:
            updated = self.db.update(entry)
        except DuplicatePathError as exc:
            raise LibraryError("Another library entry already uses that file.") from exc
        self._sync_desktop(updated)   # new name / location / icon -> keep the launcher in step
        return updated

    @staticmethod
    def _reset_update_state(entry: AppEntry) -> None:
        entry.update_status = UpdateStatus.UNAVAILABLE
        entry.latest_version = None
        entry.last_update_check = None
        entry.metadata.pop("update", None)

    def refresh_metadata(self, app_id: str, overwrite_version: bool | None = None) -> AppEntry:
        """Re-read icon, version and description from the file on disk.

        The version is only overwritten when ``overwrite_version`` is True, or when it was
        read from the file in the first place (not set manually or by an update).
        """
        entry = self._require(app_id)
        md = inspect_file(entry.path)
        if not entry.metadata.get("custom_icon"):  # a user-chosen icon is never overwritten
            old_icon = entry.icon_path
            new_icon = self._store_icon(entry.id, md)
            if new_icon:
                entry.icon_path = new_icon
                if old_icon and old_icon != new_icon:
                    self._remove_icon(old_icon)
        source = entry.metadata.get("installed_version_source")
        if overwrite_version is None:
            overwrite_version = source not in ("manual", "github_release", "rollback")
        if md.version and overwrite_version:
            entry.installed_version = md.version
            entry.metadata["installed_version_source"] = "file"
        entry.description = md.description or entry.description
        custom = entry.metadata.get("custom_icon")
        entry.metadata = {**entry.metadata, **md.extra, "warnings": md.warnings}
        if custom:
            entry.metadata["custom_icon"] = True
        updated = self.db.update(entry)
        self._sync_desktop(updated)   # icon / description / categories may have changed
        return updated

    def remove_application(self, app_id: str) -> None:
        """Remove from the library only. The application file itself is never touched.

        The application-menu launcher AppForge created for it is removed too.
        """
        entry = self._require(app_id)
        self.db.delete(app_id)
        self._remove_icon(entry.icon_path)
        try:
            self.desktop.remove(app_id)
        except DesktopError as exc:
            log.warning("Could not remove launcher for %s: %s", entry.name, exc)

    # -- application-menu launchers (Phase 4) -------------------------------------------
    @staticmethod
    def desktop_enabled(entry: AppEntry) -> bool:
        return bool(entry.metadata.get(DESKTOP_FLAG))

    def set_desktop_integration(self, app_id: str, enabled: bool) -> AppEntry:
        """Add the app to (or remove it from) the desktop's application menu."""
        entry = self._require(app_id)
        try:
            if enabled:
                self.desktop.write_entry(entry)
                entry.metadata[DESKTOP_FLAG] = True
            else:
                self.desktop.remove(app_id)
                entry.metadata.pop(DESKTOP_FLAG, None)
        except DesktopError as exc:
            raise LibraryError(str(exc)) from exc
        return self.db.update(entry)

    def desktop_default(self) -> bool:
        """Whether "Add to the application menu" is pre-ticked in the Add dialog (default: yes)."""
        return self.db.get_setting(SETTING_DESKTOP_DEFAULT, "1") != "0"

    def set_desktop_default(self, value: bool) -> None:
        self.db.set_setting(SETTING_DESKTOP_DEFAULT, "1" if value else "0")

    def _sync_desktop(self, entry: AppEntry) -> None:
        """Best-effort: rewrite this app's launcher if it has one. Never raises."""
        if not self.desktop_enabled(entry):
            return
        try:
            self.desktop.write_entry(entry)
        except DesktopError as exc:
            log.warning("Could not update launcher for %s: %s", entry.name, exc)

    def sync_desktop_entries(self) -> SyncReport:
        """Reconcile launchers with the library (call at startup).

        * integrated apps whose launcher is missing or outdated are rewritten;
        * a launcher on disk for a library app that has no flag is adopted (flag set);
        * launchers of apps that are not in the library and whose file is gone are deleted.
        """
        report = SyncReport()
        apps = self.db.list_all()
        for entry in apps:
            flagged = self.desktop_enabled(entry)
            if not flagged and not self.desktop.exists(entry.id):
                continue
            try:
                changed = self.desktop.write_entry(entry)
            except DesktopError as exc:
                report.failed.append((entry.name, str(exc)))
                continue
            if not flagged:
                entry.metadata[DESKTOP_FLAG] = True
                self.db.update(entry)
                report.adopted.append(entry.name)
            elif changed:
                report.repaired.append(entry.name)
        try:
            report.removed = self.desktop.remove_orphans({e.id for e in apps})
        except OSError:
            log.warning("Orphan launcher cleanup failed", exc_info=True)
        return report

    # -- moved / renamed files ----------------------------------------------------------
    def suggest_relocations(self, app_id: str) -> list[Path]:
        """Likely new locations for an application whose file has gone missing."""
        entry = self._require(app_id)
        others = [e for e in self.db.list_all() if e.id != entry.id]
        return find_candidates(
            entry, extra_dirs=[Path(e.path).parent for e in others],
            exclude=[e.path for e in others])

    # -- helpers ------------------------------------------------------------------------
    def _require(self, app_id: str) -> AppEntry:
        entry = self.db.get(app_id)
        if entry is None:
            raise LibraryError("That application is no longer in the library.")
        return entry

    def _store_icon(self, app_id: str, md: AppMetadata) -> str | None:
        if not md.icon_data or not md.icon_ext:
            return None
        dest = self.icons_dir / f"{app_id}.{md.icon_ext}"
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(md.icon_data)
        os.replace(tmp, dest)
        return str(dest)

    def _store_custom_icon(self, app_id: str, source: str, old_icon: str | None) -> str:
        """Copy a user-chosen image into the icon store. The original file is never modified."""
        src = Path(normalize_path(source))
        if not src.is_file():
            raise LibraryError("That icon file doesn't exist.")
        ext = src.suffix.lower()
        if ext not in ICON_EXTS:
            raise LibraryError("Choose a PNG, SVG, JPG, WebP, BMP or ICO image.")
        if src.stat().st_size > MAX_ICON_BYTES:
            raise LibraryError("That image is too large (10 MB maximum).")
        # unique name per change so Qt/pixmap caches never show a stale icon
        dest = self.icons_dir / f"{app_id}-custom-{int(time.time() * 1000)}{ext}"
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        except OSError as exc:
            raise LibraryError(f"Couldn't save the icon: {exc.strerror or exc}") from exc
        if old_icon and old_icon != str(dest):
            self._remove_icon(old_icon)
        return str(dest)

    def _reset_icon(self, entry: AppEntry) -> None:
        """Drop a custom icon and go back to the one inside the AppImage (or a placeholder)."""
        old = entry.icon_path
        entry.metadata.pop("custom_icon", None)
        entry.icon_path = None
        try:
            md = inspect_file(entry.path)
            entry.icon_path = self._store_icon(entry.id, md)
        except LibraryError:
            pass  # file missing/unreadable: fall back to the generated placeholder
        if old and old != entry.icon_path:
            self._remove_icon(old)

    def _remove_icon(self, icon_path: str | None) -> None:
        if not icon_path:
            return
        try:
            p = Path(icon_path)
            if p.parent == self.icons_dir:  # never delete anything outside our own icon store
                p.unlink(missing_ok=True)
        except OSError:
            log.debug("Could not remove icon %s", icon_path, exc_info=True)


__all__ = ["LibraryService", "LibraryError", "FileState", "ICON_EXTS", "DESKTOP_FLAG", "inspect_file",
           "file_state", "normalize_path", "normalize_repo", "get_format"]
