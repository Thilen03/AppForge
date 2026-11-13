"""Launcher integration: write, update and remove per-user ``.desktop`` entries.

An application that is "added to the application menu" gets one file,
``<applications dir>/appforge-<app id>.desktop``.  Design rules:

* The file name is keyed on the *library id*, not on the app's name or path, so renaming an app
  or moving its AppImage rewrites the **contents** but never the file name. Menu favourites and
  taskbar pins (which KDE/GNOME key on the desktop-file id) therefore survive renames and moves.
* ``Exec`` points straight at the AppImage – launching from the menu doesn't need AppForge to be
  running. ``TryExec`` points at the same file, so the menu hides the entry while the file is
  missing or not executable and shows it again once it is back.
* AppForge only ever deletes files that carry its own ``X-AppForge-Id`` marker *and* whose file name
  matches ``appforge-<id>.desktop`` (see ``DesktopService.remove``).
* Writes are atomic (temp file + ``os.replace``) and skipped when nothing changed, so a desktop's
  menu cache is not rebuilt needlessly.

Qt-free and database-free: the :class:`~appforge.core.library.LibraryService` owns the "is this app
integrated" flag (``entry.metadata["desktop_entry"]``) and calls into this module.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..envvars import env_of
from ..formats import get_format
from ..models import AppEntry
from ..paths import applications_dir

log = logging.getLogger(__name__)

MARKER_KEY = "X-AppForge-Id"
FILE_PREFIX = "appforge-"
_FILE_RE = re.compile(r"^appforge-([A-Za-z0-9_-]+)\.desktop$")
DEFAULT_ICON = "application-x-executable"
DEFAULT_CATEGORIES = "Utility;"
_MAX_COMMENT = 200

# Characters that force quoting of an Exec argument (Desktop Entry spec, "The Exec key").
_EXEC_RESERVED = frozenset(' \t\n"\'\\><~|&;$*?#()`')
_CATEGORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# The freedesktop "Main Categories" and the heading KDE's application launcher files them under.
# (desktop-file key, label shown in AppForge). A launcher needs one of these to show up in a section.
MENU_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Development", "Development"), ("Education", "Education"), ("Game", "Games"),
    ("Graphics", "Graphics"), ("Network", "Internet"), ("AudioVideo", "Multimedia"),
    ("Office", "Office"), ("Science", "Science & Math"), ("Settings", "Settings"),
    ("System", "System"), ("Utility", "Utilities"),
)
MENU_CATEGORY_KEY = "menu_category"     # entry.metadata key holding the user's choice
_MAIN_KEYS = frozenset(k for k, _ in MENU_CATEGORIES)
_FIELD_CODE_RE = re.compile(r"^%[fFuU]$")


class DesktopError(Exception):
    """User-presentable problem while creating or removing a launcher entry."""


@dataclass
class ManagedEntry:
    app_id: str
    path: Path
    try_exec: str | None = None


@dataclass
class SyncReport:
    """What :meth:`LibraryService.sync_desktop_entries` did (all lists hold app names or file names)."""

    repaired: list[str] = field(default_factory=list)    # missing/outdated entries rewritten
    adopted: list[str] = field(default_factory=list)     # entries found on disk without a flag
    removed: list[str] = field(default_factory=list)     # orphaned entries whose app file is gone
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.repaired or self.adopted or self.removed)


# -- text helpers ---------------------------------------------------------------------------------
def entry_filename(app_id: str) -> str:
    return f"{FILE_PREFIX}{app_id}.desktop"


def _escape_value(text: str) -> str:
    """Escape a ``string`` value: one line, backslashes doubled (spec: "Value types")."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()
    return text.replace("\\", "\\\\")


def quote_exec_arg(arg: str) -> str:
    """Quote one argument for the ``Exec`` key exactly as the Desktop Entry spec requires.

    ``%`` is doubled (it would otherwise start a field code); arguments containing reserved
    characters are wrapped in double quotes with ``" ` $ \\`` backslash-escaped, and finally every
    backslash is doubled again for the string-value layer (hence four backslashes for a literal one).
    """
    arg = arg.replace("%", "%%")
    if arg == "" or any(c in _EXEC_RESERVED for c in arg):
        arg = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
        arg = arg.replace("\\", "\\\\")
    return arg


def _categories(raw: str | None) -> str:
    cats = [c for c in (raw or "").split(";") if _CATEGORY_RE.match(c.strip())]
    cats = [c.strip() for c in cats]
    return (";".join(cats) + ";") if cats else DEFAULT_CATEGORIES


def menu_category_of(entry: AppEntry) -> str | None:
    """The main category the user picked for the application menu, or ``None`` = automatic."""
    value = entry.metadata.get(MENU_CATEGORY_KEY)
    return value if value in _MAIN_KEYS else None


def _entry_categories(entry: AppEntry) -> str:
    """``Categories=`` value: the user's main category first, then the app's own extra categories.

    The app's own *main* categories are dropped when the user picked one (otherwise KDE would list
    the app in several sections); additional categories such as ``Qt`` or ``Emulator`` are kept.
    """
    chosen = menu_category_of(entry)
    base = _categories(entry.metadata.get("categories"))
    if not chosen:
        return base
    extra = [c for c in base.split(";") if c and c not in _MAIN_KEYS]
    return ";".join([chosen, *extra]) + ";"


def _field_code(desktop_exec: str | None) -> str | None:
    """Reuse the AppImage's own ``%U``/``%F`` (so "Open with…" keeps working); nothing else is copied."""
    if not desktop_exec:
        return None
    for token in reversed(desktop_exec.split()):
        if _FIELD_CODE_RE.match(token):
            return token
    return None


def render_entry(entry: AppEntry) -> str:
    """The complete text of the ``.desktop`` file for ``entry``."""
    path = Path(entry.path)
    if any(ord(c) < 32 or ord(c) == 127 for c in entry.path):
        raise DesktopError("The file path contains control characters, so it can't be used in a launcher.")
    fmt = get_format(entry.format)
    argv = fmt.launch_command(path) if fmt else [str(path)]
    env = env_of(entry)
    if env:   # same as KDE's menu editor: Exec=env NAME=value … command
        argv = ["env", *(f"{k}={v}" for k, v in env.items()), *argv]
    exec_line = " ".join(quote_exec_arg(a) for a in argv)
    code = _field_code(entry.metadata.get("desktop_exec"))
    if code:
        exec_line += " " + code

    icon = entry.icon_path if entry.icon_path and os.path.isfile(entry.icon_path) else DEFAULT_ICON
    name = _escape_value(entry.name) or "Application"
    lines = [
        "# Managed by AppForge. Changes made here are overwritten; use AppForge to remove this entry.",
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        f"Name={name}",
    ]
    generic = _escape_value(entry.metadata.get("generic_name") or "")
    if generic:
        lines.append(f"GenericName={generic}")
    comment = _escape_value(entry.description or "")[:_MAX_COMMENT].rstrip()
    if comment:
        lines.append(f"Comment={comment}")
    lines += [
        f"Exec={exec_line}",
        f"TryExec={_escape_value(str(path))}",
        f"Path={_escape_value(str(path.parent))}",
        f"Icon={_escape_value(icon)}",
        "Terminal=false",
        f"Categories={_entry_categories(entry)}",
    ]
    wm_class = _escape_value(entry.metadata.get("startup_wm_class") or "")
    if wm_class:
        lines.append(f"StartupWMClass={wm_class}")
    lines.append(f"{MARKER_KEY}={entry.id}")
    return "\n".join(lines) + "\n"


def _read_marker(path: Path) -> tuple[str | None, str | None]:
    """(marker id, TryExec) from an existing file; ``(None, None)`` if unreadable."""
    marker = try_exec = None
    try:
        for line in path.read_text("utf-8", "replace").splitlines():
            if line.startswith(MARKER_KEY + "="):
                marker = line.split("=", 1)[1].strip()
            elif line.startswith("TryExec="):
                try_exec = line.split("=", 1)[1].strip().replace("\\\\", "\\")
    except OSError:
        return None, None
    return marker, try_exec


# -- the service ----------------------------------------------------------------------------------
class DesktopService:
    def __init__(self, directory: str | os.PathLike | None = None):
        self._directory = Path(directory) if directory else None

    @property
    def directory(self) -> Path:
        return self._directory or applications_dir()

    def entry_path(self, app_id: str) -> Path:
        return self.directory / entry_filename(app_id)

    def exists(self, app_id: str) -> bool:
        return self.entry_path(app_id).is_file()

    def write_entry(self, entry: AppEntry) -> bool:
        """Create or update the launcher. Returns True if the file was (re)written."""
        text = render_entry(entry)
        dest = self.entry_path(entry.id)
        try:
            if dest.is_file() and dest.read_text("utf-8") == text:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
            try:
                tmp.write_text(text, "utf-8")
                os.chmod(tmp, 0o644)
                os.replace(tmp, dest)
            finally:
                tmp.unlink(missing_ok=True)
        except OSError as exc:
            raise DesktopError(f"Couldn't write the launcher in {dest.parent}: {exc.strerror or exc}") from exc
        return True

    def remove(self, app_id: str) -> bool:
        """Delete this app's launcher. Only ever deletes a file that is clearly ours."""
        dest = self.entry_path(app_id)
        if not dest.is_file():
            return False
        marker, _ = _read_marker(dest)
        if marker != app_id or not _FILE_RE.match(dest.name):
            log.warning("Refusing to delete %s: it is not an AppForge launcher for %s", dest, app_id)
            return False
        try:
            dest.unlink()
        except OSError as exc:
            raise DesktopError(f"Couldn't remove the launcher {dest}: {exc.strerror or exc}") from exc
        return True

    def list_managed(self) -> list[ManagedEntry]:
        """Every AppForge-owned launcher currently on disk (file name *and* marker must agree)."""
        found: list[ManagedEntry] = []
        try:
            names = sorted(os.listdir(self.directory))
        except OSError:
            return found
        for name in names:
            m = _FILE_RE.match(name)
            if not m:
                continue
            p = self.directory / name
            marker, try_exec = _read_marker(p)
            if marker == m.group(1):
                found.append(ManagedEntry(marker, p, try_exec))
        return found

    def remove_orphans(self, known_ids: set[str]) -> list[str]:
        """Delete launchers of apps that are not in the library *and* whose file is gone.

        A launcher whose AppImage still exists is left alone – it still works, and it may belong to
        another AppForge library.
        """
        removed = []
        for m in self.list_managed():
            if m.app_id in known_ids:
                continue
            if m.try_exec and os.path.exists(m.try_exec):
                continue
            try:
                m.path.unlink()
                removed.append(m.path.name)
            except OSError:
                log.warning("Could not remove orphaned launcher %s", m.path, exc_info=True)
        return removed


__all__ = ["DesktopService", "DesktopError", "ManagedEntry", "SyncReport", "entry_filename",
           "quote_exec_arg", "render_entry", "MARKER_KEY", "MENU_CATEGORIES", "MENU_CATEGORY_KEY",
           "menu_category_of"]
