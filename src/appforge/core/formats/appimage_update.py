"""Bounded, non-executing AppImage update-info reads and offline source suggestions.

AppImageSpec: https://github.com/AppImage/AppImageSpec/blob/master/draft.md
This detects repository hints only; it does not implement the zsync transport.
"""
from __future__ import annotations

import os
import re
import struct
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..updates.providers import parse_source

MAX_UPDATE_BYTES = 4096
MAX_SECTION_NAMES = 1024 * 1024
MAX_SECTIONS = 8192
SUGGESTED_SOURCE_KEY = "suggested_update_source"
SOURCE_ORIGIN_KEY = "update_source_origin"


def _update_text(data: bytes) -> str | None:
    # Only zero padding may follow the string; never accept two conflicting values.
    text, separator, padding = data.partition(b'\0')
    if separator and padding.strip(b'\0'):
        return None
    try:
        value = text.decode('ascii').strip()
    except UnicodeDecodeError:
        return None
    if not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
        return None
    return value


def read_update_information(path: Path, kind: int) -> str | None:
    """Read the specified AppImage field only, with strict size/range bounds."""
    try:
        with path.open('rb') as stream:
            size = os.fstat(stream.fileno()).st_size

            def read(offset, length, limit):
                if offset < 0 or not 0 < length <= limit or offset + length > size:
                    raise ValueError('Invalid AppImage section range')
                stream.seek(offset)
                data = stream.read(length)
                if len(data) != length:
                    raise ValueError('Truncated AppImage section')
                return data

            if kind == 1:
                return _update_text(read(33651, 512, MAX_UPDATE_BYTES))
            header = read(0, 52, 64)
            if (header[:4] != b'\x7fELF' or header[4] not in (1, 2)
                    or header[5] not in (1, 2) or header[6] != 1):
                return None
            endian = '<' if header[5] == 1 else '>'
            is64 = header[4] == 2
            if is64:
                header = read(0, 64, 64)
                table_offset = struct.unpack_from(endian + 'Q', header, 40)[0]
                stride, count, names_index = struct.unpack_from(endian + 'HHH', header, 58)
                section_format = endian + 'IIQQQQIIQQ'
            else:
                table_offset = struct.unpack_from(endian + 'I', header, 32)[0]
                stride, count, names_index = struct.unpack_from(endian + 'HHH', header, 46)
                section_format = endian + 'IIIIIIIIII'
            entry_size = struct.calcsize(section_format)
            if table_offset < len(header) or not entry_size <= stride <= 4096:
                return None

            def section(index):
                return struct.unpack(section_format,
                                     read(table_offset + index * stride, entry_size, 64))

            # ELF extended section numbering uses section zero's size/link fields.
            if count == 0 or names_index == 0xFFFF:
                zero = section(0)
                if count == 0:
                    count = zero[5]
                if names_index == 0xFFFF:
                    names_index = zero[6]
            if (not 0 < count <= MAX_SECTIONS or not 0 < names_index < count
                    or table_offset + count * stride > size):
                return None
            names_header = section(names_index)
            if names_header[1] != 3:  # SHT_STRTAB
                return None
            names = read(names_header[4], names_header[5], MAX_SECTION_NAMES)
            update_data = None
            for index in range(1, count):
                entry = section(index)
                start = entry[0]
                if start >= len(names):
                    continue
                if names[start:start + 10] == b'.upd_info\0':
                    if update_data is not None or entry[1] != 1:  # SHT_PROGBITS
                        return None
                    update_data = read(entry[4], entry[5], MAX_UPDATE_BYTES)
            return _update_text(update_data) if update_data is not None else None
    except (OSError, ValueError, struct.error, OverflowError):
        return None


def suggest_source(information: str | None) -> str | None:
    """Recognize a repository from supported update-info shapes, never a homepage."""
    if (not isinstance(information, str) or len(information) > MAX_UPDATE_BYTES
            or any(ord(c) < 32 or ord(c) > 126 for c in information)):
        return None
    fields = information.split('|')
    url = None
    if len(fields) == 5 and fields[0] == 'gh-releases-zsync':
        _, owner, repo, tag, pattern = fields
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner)
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', repo) or repo in ('.', '..')
                or not tag.strip() or not pattern.lower().endswith('.zsync')
                or any(c in pattern for c in '/\\') or not pattern[:-6]):
            return None
        url = f'https://github.com/{owner}/{repo}'
    elif len(fields) == 2 and fields[0] == 'zsync':
        try:
            parsed = urlsplit(fields[1])
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment
                    or (parsed.port is not None and not 0 < parsed.port <= 65535)):
                return None
            if parsed.hostname in ('github.com', 'gitlab.com', 'codeberg.org') and parsed.port not in (None, 443):
                return None
            parts = [unquote(p) for p in parsed.path.split('/') if p]
            if not parts or not parts[-1].lower().endswith('.zsync'):
                return None
            # GitLab: /group/project/-/releases/tag/downloads/file.zsync.
            if '-' in parts:
                cut = parts.index('-')
                tail = parts[cut + 1:]
                if cut < 2 or len(tail) < 4 or tail[0] != 'releases' or tail[2] != 'downloads':
                    return None
                repo_parts = parts[:cut]
            # GitHub/Forgejo: /owner/repo/releases/download/tag/file.zsync
            # or /owner/repo/releases/latest/download/file.zsync.
            elif (len(parts) == 6 and parts[2] == 'releases'
                  and (parts[3] == 'download' or parts[3:5] == ['latest', 'download'])):
                repo_parts = parts[:2]
            else:
                return None
            if not all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) and p not in ('.', '..') for p in repo_parts):
                return None
            host = parsed.hostname
            if parsed.port not in (None, 443):
                host += f':{parsed.port}'
            url = f'https://{host}/' + '/'.join(repo_parts)
        except ValueError:
            return None
    source = parse_source(url) if url else None
    return source.url if source else None


def metadata_source(metadata) -> str | None:
    """Validate a reader's suggestion again at the UI boundary."""
    if metadata.format_id != 'appimage':
        return None
    value = metadata.extra.get(SUGGESTED_SOURCE_KEY)
    if not isinstance(value, str) or not value.startswith('https://') or any(c.isspace() for c in value):
        return None
    try:
        source = parse_source(value)
    except ValueError:
        return None
    return source.url if source and source.url == value else None


def repository_metadata_url(value: str, *, explicit_vcs: bool = False) -> str | None:
    """Accept repository roots, not arbitrary homepages, issue trackers or URLs in text."""
    if len(value) > MAX_UPDATE_BYTES or any(ord(c) < 33 or ord(c) > 126 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            return None
        known = parsed.hostname in ('github.com', 'gitlab.com', 'codeberg.org')
        if not explicit_vcs and not known:
            return None
        if known and parsed.port not in (None, 443):
            return None
        host = parsed.hostname
        if parsed.port not in (None, 443):
            host += f':{parsed.port}'
        path = parsed.path.rstrip('/').removesuffix('.git')
        canonical = f'https://{host}{path}'
        source = parse_source(canonical)
        return source.url if source and source.url == canonical else None
    except ValueError:
        return None


def source_detection_message(metadata) -> str:
    if metadata_source(metadata):
        origin = metadata.extra.get(SOURCE_ORIGIN_KEY)
        where = ("AppStream repository metadata" if origin == 'appstream_vcs' else
                 "AppStream repository homepage" if origin == 'appstream_homepage' else
                 "update information")
        return f"Suggested from this AppImage's embedded {where}. Review, change or clear the source before adding."
    return ("No automatic update source found in this AppImage's readable embedded metadata. "
            "Enter a repository URL manually to enable updates.")
