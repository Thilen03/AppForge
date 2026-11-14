"""Versioned portable library configuration. No Qt, SQLite, execution or downloads."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from .. import __version__
from .desktop import MENU_CATEGORIES
from .envvars import MAX_VARS, validate_pair
from .formats import detect_format
from .library import ICON_EXTS, MAX_ICON_BYTES, LibraryError, normalize_path, normalize_repo
from .models import AppEntry, new_id
from .organize import MAX_CATEGORY_LEN

FORMAT = "appforge-library"
SCHEMA_VERSION = 1
MAX_BYTES = 32 * 1024 * 1024
MAX_APPS = 10000
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
META_TEXT = {"category": MAX_CATEGORY_LEN, "categories": 2048, "menu_category": 40,
             "asset_pattern": 1024, "executable_kind": 16, "generic_name": 512,
             "startup_wm_class": 512, "desktop_exec": 8, "installed_version_source": 32}
META_BOOL = {"include_prereleases", "desktop_entry", "custom_icon"}
FIELDS = {"id", "name", "path", "format", "installed_version", "github_repo", "description",
          "added_at", "metadata", "icon"}


class TransferError(LibraryError):
    pass


class TransferCancelled(TransferError):
    pass


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise TransferCancelled("Operation cancelled.")


def _text(value, label, limit=4096, *, nullable=False, multiline=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise TransferError(f"{label} must be text of at most {limit} characters.")
    allowed = '\n\r\t' if multiline else ''
    if any((ord(c) < 32 and c not in allowed) or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise TransferError(f"{label} contains invalid characters.")
    return value


def validate_record(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) - FIELDS:
        raise TransferError("Invalid application fields in the export.")
    result = {}
    for key in ('id', 'name', 'path', 'format'):
        result[key] = _text(raw.get(key), key)
    if not _ID.fullmatch(result['id']):
        raise TransferError("Application ID is invalid (letters, numbers, _ and - only).")
    if not result['name'].strip():
        raise TransferError("Application name cannot be empty.")
    if not os.path.isabs(result['path']):
        raise TransferError("Application paths must be absolute Linux paths.")
    result['path'] = normalize_path(result['path'])
    if result['format'] not in ('appimage', 'executable'):
        raise TransferError("Unsupported application format.")
    result['installed_version'] = _text(raw.get('installed_version'), 'Installed version', 512, nullable=True)
    result['description'] = _text(raw.get('description'), 'Description', 65536, nullable=True, multiline=True)
    repo = _text(raw.get('github_repo'), 'Repository', 4096, nullable=True)
    try:
        result['github_repo'] = normalize_repo(repo)
    except (ValueError, LibraryError) as exc:
        raise TransferError(f"Invalid repository: {exc}") from exc
    added = raw.get('added_at', time.time())
    if type(added) not in (int, float) or not math.isfinite(added) or not 0 <= added <= 253402300799:
        raise TransferError("Date added must be a valid timestamp.")
    result['added_at'] = added
    metadata = raw.get('metadata', {})
    if not isinstance(metadata, dict) or set(metadata) - set(META_TEXT) - META_BOOL - {'env_vars'}:
        raise TransferError("Unsupported configuration metadata (credentials and runtime state are not imported).")
    md = {}
    for key, value in metadata.items():
        if key in META_BOOL:
            if type(value) is not bool:
                raise TransferError(f"{key} must be true or false.")
            md[key] = value
        elif key in META_TEXT:
            md[key] = _text(value, key, META_TEXT[key])
        else:
            if not isinstance(value, dict) or len(value) > MAX_VARS:
                raise TransferError("Invalid environment variables.")
            env = {}
            for name, val in value.items():
                name = _text(name, 'Environment name', 256)
                val = _text(val, 'Environment value', 4096)
                try:
                    clean, val = validate_pair(name, val)
                except ValueError as exc:
                    raise TransferError(str(exc)) from exc
                if clean != name:
                    raise TransferError("Environment names cannot contain surrounding whitespace.")
                env[name] = val
            md[key] = env
    if 'menu_category' in md and md['menu_category'] not in dict(MENU_CATEGORIES):
        raise TransferError("Invalid application-menu category.")
    if 'executable_kind' in md and md['executable_kind'] not in ('elf', 'script'):
        raise TransferError("Invalid executable kind.")
    if 'installed_version_source' in md and md['installed_version_source'] not in ('file', 'manual', 'github_release', 'rollback'):
        raise TransferError("Invalid installed-version source.")
    if 'desktop_exec' in md and md['desktop_exec'] not in ('%f', '%F', '%u', '%U'):
        raise TransferError("Only a desktop file argument marker can be imported.")
    result['metadata'] = md
    icon = raw.get('icon')
    if icon is not None:
        if not isinstance(icon, dict) or set(icon) != {'extension', 'data'}:
            raise TransferError("Invalid embedded icon.")
        if icon['extension'] not in ICON_EXTS:
            raise TransferError("Unsupported embedded icon extension.")
        encoded = _text(icon['data'], 'Icon data', (MAX_ICON_BYTES + 2) // 3 * 4)
        try:
            blob = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TransferError("Invalid embedded icon encoding.") from exc
        if not blob or len(blob) > MAX_ICON_BYTES:
            raise TransferError("Embedded icon is empty or exceeds 10 MiB.")
        result['icon'] = dict(icon)
    else:
        result['icon'] = None
    return result


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TransferError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def read_export(path, *, cancel=None, progress=None) -> list[dict]:
    _cancel(cancel)
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode):
            raise TransferError('Choose a regular JSON file.')
        if info.st_size > MAX_BYTES:
            raise TransferError('Library export exceeds 32 MiB.')
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise TransferError("Library export exceeds 32 MiB.")
        document = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_keys)
        if not isinstance(document, dict) or document.get('format') != FORMAT:
            raise TransferError("This is not an AppForge library export.")
        if type(document.get('schema_version')) is not int or document['schema_version'] != SCHEMA_VERSION:
            raise TransferError("Unsupported library export schema version.")
        if set(document) - {'format', 'schema_version', 'appforge_version', 'applications'}:
            raise TransferError("Unsupported export fields; global settings and credentials cannot be imported.")
        _text(document.get('appforge_version'), 'AppForge version', 128)
        records = document.get('applications')
        if not isinstance(records, list) or len(records) > MAX_APPS:
            raise TransferError(f"Applications must be a list of at most {MAX_APPS} entries.")
        validated = []
        for i, record in enumerate(records):
            _cancel(cancel)
            try:
                validated.append(validate_record(record))
            except TransferError as exc:
                raise TransferError(f"Application {i + 1}: {exc}") from exc
            if progress:
                progress(i + 1, len(records))
        return validated
    except (OSError, UnicodeError, ValueError, RecursionError, OverflowError, TypeError) as exc:
        raise TransferError(f"Could not read the library export: {exc}") from exc


def export_library(entries, path, *, protected=(), include_environment=False, cancel=None, progress=None):
    """Snapshot records are passed by the UI. Atomic write; no database access."""
    destination = Path(path)
    _cancel(cancel)
    try:
        if destination.is_symlink():
            raise TransferError("Choose a regular JSON file, not a symbolic link.")
        forbidden = [*protected, *(e.path for e in entries), *(e.icon_path for e in entries if e.icon_path)]
        for value in forbidden:
            if (normalize_path(destination) == normalize_path(value) or
                    (destination.exists() and Path(value).exists() and os.path.samefile(destination, value))):
                raise TransferError("The export cannot replace an application, icon or library database.")
        if len(entries) > MAX_APPS:
            raise TransferError(f"At most {MAX_APPS} applications can be exported.")
        records, warnings = [], []
        total_bytes = 256
        for i, entry in enumerate(entries):
            _cancel(cancel)
            md = {k: deepcopy(v) for k, v in entry.metadata.items() if (k in META_TEXT or k in META_BOOL) and v is not None}
            # A desktop command itself is never portable configuration; retain only its file marker.
            if 'desktop_exec' in md:
                marker = next((s for s in reversed(str(md['desktop_exec']).split()) if s in ('%f', '%F', '%u', '%U')), None)
                if marker:
                    md['desktop_exec'] = marker
                else:
                    md.pop('desktop_exec')
            if include_environment and entry.metadata.get('env_vars'):
                md['env_vars'] = deepcopy(entry.metadata['env_vars'])
            raw = {k: getattr(entry, k) for k in FIELDS - {'metadata', 'icon'}}
            raw.update(metadata=md, icon=None)
            if entry.icon_path:
                try:
                    ext = Path(entry.icon_path).suffix.lower()
                    if not Path(entry.icon_path).is_file():
                        raise ValueError('icon file is missing or not a regular file')
                    with open(entry.icon_path, 'rb') as stream:
                        blob = stream.read(MAX_ICON_BYTES + 1)
                    if ext not in ICON_EXTS or not blob or len(blob) > MAX_ICON_BYTES:
                        raise ValueError('unsupported, empty or oversized icon')
                    raw['icon'] = dict(extension=ext, data=base64.b64encode(blob).decode('ascii'))
                except (OSError, ValueError) as exc:
                    warnings.append(f"{entry.name}: icon omitted ({exc}).")
                    md.pop('custom_icon', None)
            validated = validate_record(raw)
            total_bytes += len(json.dumps(validated, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            if total_bytes > MAX_BYTES:
                raise TransferError("Library export exceeds 32 MiB; reduce embedded icon sizes.")
            records.append(validated)
            if progress:
                progress(i + 1, len(entries))
        payload = json.dumps(dict(format=FORMAT, schema_version=SCHEMA_VERSION,
                                  appforge_version=__version__, applications=records),
                             ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        if len(payload) > MAX_BYTES:
            raise TransferError("Library export exceeds 32 MiB; reduce embedded icon sizes.")
        _cancel(cancel)
        fd, name = tempfile.mkstemp(prefix='.appforge-export-', suffix='.tmp', dir=destination.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _cancel(cancel)
            os.replace(name, destination)
        finally:
            Path(name).unlink(missing_ok=True)
        return warnings
    except OSError as exc:
        raise TransferError(f"Could not save the library export: {exc}") from exc


def _file_info(path):
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode):
            return None, 'Not a regular file'
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns), ''
    except FileNotFoundError:
        return None, 'Missing file — use Locate file after import'
    except OSError:
        return None, 'File unavailable — configuration can still be imported'


@dataclass
class ImportCandidate:
    record: dict
    fingerprint: tuple | None = None
    status: str = ''
    duplicate: bool = False
    id_conflict: bool = False
    invalid_file: bool = False
    same_name: bool = False
    imported: bool = False


def preview_import(records, existing, *, cancel=None, progress=None):
    """Read-only preview. Existing entries are plain snapshots, never a live service."""
    paths = {normalize_path(e.path) for e in existing}
    ids = {e.id for e in existing}
    names = {e.name.casefold() for e in existing}
    identities = set()
    for entry in existing:
        _cancel(cancel)
        fingerprint, _ = _file_info(entry.path)
        if fingerprint:
            identities.add(fingerprint[:2])
    candidates = []
    for i, record in enumerate(records):
        _cancel(cancel)
        record = validate_record(record)
        path = record['path']
        fingerprint, state = _file_info(path)
        duplicate = path in paths or bool(fingerprint and fingerprint[:2] in identities)
        conflict = record['id'] in ids
        same_name = record['name'].casefold() in names
        invalid = state == 'Not a regular file'
        if fingerprint:
            fmt = detect_format(Path(path))
            invalid = fmt is None or fmt.id != record['format']
            if invalid:
                state = 'File format does not match — not eligible'
        details = ['Duplicate file — skipped'] if duplicate else []
        if conflict and not duplicate:
            details.append('ID conflict — choose new IDs to import')
        if same_name and not duplicate:
            details.append('Same name — separate application')
        if state:
            details.append(state)
        candidates.append(ImportCandidate(record, fingerprint, '; '.join(details) or 'Ready',
                                           duplicate, conflict, invalid, same_name))
        paths.add(path)
        ids.add(record['id'])
        names.add(record['name'].casefold())
        if fingerprint:
            identities.add(fingerprint[:2])
        if progress:
            progress(i + 1, len(records))
    return candidates


@dataclass
class PreparedImport:
    record: dict
    icon_path: str | None = None
    missing: bool = False
    warnings: list[str] = field(default_factory=list)
    existing_keys: frozenset = field(default_factory=frozenset)


def prepare_import(candidate, existing, icons_dir, *, new_ids=False, environment=False, launchers=True, cancel=None):
    """Revalidate the selected row and write its icon on a worker before DB registration."""
    _cancel(cancel)
    record = validate_record(candidate.record)
    current = preview_import([record], existing, cancel=cancel)[0]
    if current.duplicate:
        raise TransferError('Duplicate file — already registered.')
    if current.invalid_file:
        raise TransferError('File format no longer matches the exported application.')
    if candidate.fingerprint and current.fingerprint and candidate.fingerprint != current.fingerprint:
        raise TransferError('The application file changed after the preview; load the export again.')
    if current.id_conflict:
        if not new_ids:
            raise TransferError('Application ID is already in use; choose new IDs to import it separately.')
        record['id'] = new_id()
    if not environment:
        record['metadata'].pop('env_vars', None)
    if not launchers:
        record['metadata'].pop('desktop_entry', None)
    prepared = PreparedImport(record, missing=current.fingerprint is None,
                              existing_keys=frozenset((e.id, e.path) for e in existing))
    icon = record['icon']
    if icon:
        # Never use an imported file name as a destination. UUID + validated extension only.
        destination = Path(icons_dir) / f"{record['id']}-import-{new_id()}{icon['extension']}"
        try:
            blob = base64.b64decode(icon['data'], validate=True)
            with destination.open('xb') as stream:
                stream.write(blob)
            prepared.icon_path = str(destination)
            _cancel(cancel)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return prepared


def entry_from_record(record):
    record = validate_record(record)
    return AppEntry(**{k: record[k] for k in FIELDS - {'metadata', 'icon'}}, metadata=deepcopy(record['metadata']))
