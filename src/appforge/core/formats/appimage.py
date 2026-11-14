"""AppImage support: detection and *non-executing* metadata extraction.

An AppImage (type 2) is an ELF runtime followed by a SquashFS image. We locate the SquashFS
image from the ELF headers and read it with the pure-Python PySquashfsImage library, so
importing an AppImage never runs it and does not require the executable bit or FUSE.
"""
from __future__ import annotations

import configparser
import logging
import re
import struct
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

from .base import AppFormat, AppMetadata, FormatError

log = logging.getLogger(__name__)

MAX_ICON_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
_SCAN_LIMIT = 16 * 1024 * 1024

# --------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------


def appimage_type(path: Path) -> int | None:
    """Return 1 or 2 for AppImage types, 0 for an unmarked ELF named *.AppImage, else None."""
    try:
        if not path.is_file():
            return None
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head[:4] != b"\x7fELF":
        return None
    if head[8:10] == b"AI" and head[10] in (1, 2):
        return head[10]
    if path.name.lower().endswith(".appimage"):
        return 0
    return None


def _elf_end(f) -> int | None:
    """Offset just past the ELF section header table = start of the SquashFS image."""
    f.seek(0)
    h = f.read(64)
    if len(h) < 52 or h[:4] != b"\x7fELF":
        return None
    little = h[5] == 1
    e = "<" if little else ">"
    try:
        if h[4] == 2:  # 64-bit
            shoff = struct.unpack_from(e + "Q", h, 0x28)[0]
            shentsize, shnum = struct.unpack_from(e + "HH", h, 0x3A)
        else:
            shoff = struct.unpack_from(e + "I", h, 0x20)[0]
            shentsize, shnum = struct.unpack_from(e + "HH", h, 0x2E)
    except struct.error:
        return None
    return shoff + shentsize * shnum


def _looks_like_squashfs(f, off: int) -> bool:
    f.seek(off)
    sb = f.read(32)
    if len(sb) < 32 or sb[:4] != b"hsqs":
        return False
    major = struct.unpack_from("<H", sb, 28)[0]
    return major == 4


def find_squashfs_offset(path: Path) -> int | None:
    with open(path, "rb") as f:
        off = _elf_end(f)
        if off is not None and _looks_like_squashfs(f, off):
            return off
        # Fallback: scan the start of the file for a plausible SquashFS superblock.
        f.seek(0)
        data = f.read(_SCAN_LIMIT)
    pos = data.find(b"hsqs")
    with open(path, "rb") as f:
        while pos != -1:
            if _looks_like_squashfs(f, pos):
                return pos
            pos = data.find(b"hsqs", pos + 1)
    return None


# --------------------------------------------------------------------------------------
# SquashFS access
# --------------------------------------------------------------------------------------


class _Image:
    """Small convenience layer over PySquashfsImage (path lookup with symlink following)."""

    def __init__(self, path: Path, offset: int):
        from PySquashfsImage import SquashFsImage  # imported lazily: heavy and optional

        self.im = SquashFsImage.from_file(str(path), offset=offset)
        self.root = self.im.root

    def close(self) -> None:
        try:
            self.im.close()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _children(node):
        ch = node.children
        return list(ch.values()) if isinstance(ch, dict) else list(ch)

    def listdir(self, path: str):
        node = self.lookup(path)
        if node is None or not node.is_dir:
            return []
        return self._children(node)

    def lookup(self, path: str):
        parts = deque(p for p in path.split("/") if p)
        stack = [self.root]
        hops = 0
        while parts:
            name = parts.popleft()
            if name == ".":
                continue
            if name == "..":
                if len(stack) > 1:
                    stack.pop()
                continue
            if not stack[-1].is_dir:
                return None
            child = next((c for c in self._children(stack[-1]) if c.name == name), None)
            if child is None:
                return None
            if child.is_symlink:
                hops += 1
                if hops > 16:
                    return None
                target = child.readlink()
                if target.startswith("/"):
                    stack = [self.root]
                parts = deque([p for p in target.split("/") if p] + list(parts))
                continue
            if parts:
                if not child.is_dir:
                    return None
                stack.append(child)
            else:
                return child
        return stack[-1]

    def read(self, path: str, limit: int) -> bytes | None:
        node = self.lookup(path)
        if node is None or not node.is_file or node.size > limit:
            return None
        return self.im.read_file(node.inode)


# --------------------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------------------

_ARCH_TOKENS = {
    "x86_64", "x86", "x64", "amd64", "aarch64", "arm64", "armhf", "i386", "i686", "linux",
    "linux64", "appimage", "64bit", "64-bit",
}
_VERSION_TOKEN = re.compile(r"^v?\d+([._+\-~]?[0-9A-Za-z]+)*$")
_NUMBERED_NIGHTLY_IN_NAME = re.compile(
    r"(?<![A-Za-z0-9])((?:nightly|snapshot)[-_]\d+(?:[-_][0-9a-f]{7,40})?)(?=$|[-_ .])",
    re.IGNORECASE,
)
_VERSION_IN_NAME = re.compile(r"(?<![A-Za-z0-9.])v?(\d+(?:\.\d+){1,3}(?:[-+~][0-9A-Za-z.]+)?)")


def suggest_name_from_filename(filename: str) -> str:
    """'Dolphin-Emu-5.0-x86_64.AppImage' -> 'Dolphin Emu'."""
    stem = re.sub(r"\.appimage(\.zs-old)?$", "", filename, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"[-_ ]+", stem) if t]
    kept: list[str] = []
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if low in _ARCH_TOKENS:
            continue
        if i > 0 and _VERSION_TOKEN.match(tok) and any(ch.isdigit() for ch in tok):
            break
        kept.append(tok)
    name = " ".join(kept).strip()
    return name or stem or filename


def version_from_filename(filename: str) -> str | None:
    stem = re.sub(r"\.appimage$", "", filename, flags=re.IGNORECASE)
    stem = "".join(t for t in re.split(r"([-_ ]+)", stem) if t.lower() not in _ARCH_TOKENS)
    m = _NUMBERED_NIGHTLY_IN_NAME.search(stem) or _VERSION_IN_NAME.search(stem)
    return m.group(1) if m else None


def _parse_desktop(text: str) -> dict[str, str]:
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # keep key case
    try:
        cp.read_string(text)
    except configparser.Error:
        # Tolerate files with junk before the first section header.
        try:
            cp.read_string(text[text.index("[Desktop Entry]"):])
        except (ValueError, configparser.Error):
            return {}
    if not cp.has_section("Desktop Entry"):
        return {}
    return dict(cp.items("Desktop Entry"))


def _localised(entries: dict[str, str], key: str) -> str | None:
    val = entries.get(key)
    return val.strip() if val and val.strip() else None


def _parse_metainfo(xml_bytes: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for tag in ("name", "summary", "id"):
        el = root.find(tag)  # un-localised element only (no xml:lang attribute)
        for cand in root.findall(tag):
            if not any(k.endswith("lang") for k in cand.attrib):
                el = cand
                break
        if el is not None and el.text and el.text.strip():
            out[tag] = el.text.strip()
    releases = root.findall("./releases/release")
    best = None
    for rel in releases:
        ver = rel.get("version")
        if not ver:
            continue
        stamp = rel.get("date") or rel.get("timestamp") or ""
        if best is None or stamp > best[0]:
            best = (stamp, ver)
    if best:
        out["version"] = best[1]
    return out


def _sniff_icon(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    head = data[:2048].lstrip()
    if head.startswith(b"\x1f\x8b"):
        return None  # svgz – not supported
    if b"<svg" in data[:4096]:
        return "svg"
    if head.startswith(b"/* XPM"):
        return "xpm"
    return None


def _icon_score(data: bytes, kind: str) -> int:
    if kind == "svg":
        return 10_000
    if kind == "png" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return min(w, h)
    return 1


# --------------------------------------------------------------------------------------
# Format implementation
# --------------------------------------------------------------------------------------


class AppImageFormat(AppFormat):
    id = "appimage"
    display_name = "AppImage"

    def detect(self, path: Path) -> bool:
        return appimage_type(path) is not None

    def extract_metadata(self, path: Path) -> AppMetadata:
        kind = appimage_type(path)
        if kind is None:
            raise FormatError("This file is not an AppImage.")

        fname = path.name
        md = AppMetadata(
            format_id=self.id,
            name_suggestion=suggest_name_from_filename(fname),
            version=version_from_filename(fname),
            extra={"appimage_type": kind, "version_source": "filename" if version_from_filename(fname) else None},
        )
        if kind == 1:
            md.warnings.append("Type 1 AppImage: embedded metadata cannot be read, using the file name.")
            return md

        offset = find_squashfs_offset(path)
        if offset is None:
            md.warnings.append("Could not locate the embedded file system; using the file name only.")
            return md

        image = None
        try:
            image = _Image(path, offset)
            self._fill_from_image(image, md)
        except Exception as exc:  # noqa: BLE001 - any parse/decompress failure degrades gracefully
            log.warning("AppImage metadata extraction failed for %s: %s", path, exc, exc_info=True)
            md.warnings.append(f"Could not read embedded metadata ({type(exc).__name__}); using the file name.")
        finally:
            if image:
                image.close()
        return md

    # -- internals ----------------------------------------------------------------------
    def _fill_from_image(self, image: _Image, md: AppMetadata) -> None:
        desktop = self._read_desktop(image)
        meta = self._read_metainfo(image)

        name = _localised(desktop, "Name") or meta.get("name")
        if name:
            md.name_suggestion = name
        md.description = _localised(desktop, "Comment") or meta.get("summary")

        version = _localised(desktop, "X-AppImage-Version")
        source = "desktop"
        if not version:
            version, source = meta.get("version"), "metainfo"
        if version:
            md.version, md.extra["version_source"] = version, source

        for key, out in (("Exec", "desktop_exec"), ("Categories", "categories"),
                         ("GenericName", "generic_name"), ("StartupWMClass", "startup_wm_class")):
            val = _localised(desktop, key)
            if val:
                md.extra[out] = val
        if "id" in meta:
            md.extra["appstream_id"] = meta["id"]

        icon_name = _localised(desktop, "Icon")
        icon = self._find_icon(image, icon_name)
        if icon:
            md.icon_data, md.icon_ext = icon
        else:
            md.warnings.append("No embedded icon found.")

    def _read_desktop(self, image: _Image) -> dict[str, str]:
        candidates = [c for c in image.listdir("/") if c.name.endswith(".desktop")]
        candidates.sort(key=lambda c: c.name)
        if not candidates:
            candidates = [c for c in image.listdir("/usr/share/applications") if c.name.endswith(".desktop")]
            candidates.sort(key=lambda c: c.name)
        for node in candidates:
            data = image.read(node.path, MAX_TEXT_BYTES)
            if data:
                parsed = _parse_desktop(data.decode("utf-8", "replace"))
                if parsed:
                    return parsed
        return {}

    def _read_metainfo(self, image: _Image) -> dict[str, str]:
        for d in ("/usr/share/metainfo", "/usr/share/appdata"):
            files = [c for c in image.listdir(d) if c.name.endswith((".xml"))]
            files.sort(key=lambda c: c.name)
            for node in files:
                data = image.read(node.path, MAX_TEXT_BYTES)
                if data:
                    parsed = _parse_metainfo(data)
                    if parsed:
                        return parsed
        return {}

    def _find_icon(self, image: _Image, icon_name: str | None) -> tuple[bytes, str] | None:
        paths: list[str] = []
        if icon_name:
            if "/" in icon_name:
                paths.append(icon_name)  # absolute icon path inside the AppDir
            else:
                paths += [f"/{icon_name}{ext}" for ext in (".png", ".svg", ".xpm")]
                paths.append(f"/{icon_name}")
        paths.append("/.DirIcon")
        if icon_name and "/" not in icon_name:
            for size_dir in image.listdir("/usr/share/icons/hicolor"):
                if size_dir.is_dir:
                    for ext in (".png", ".svg"):
                        paths.append(f"/usr/share/icons/hicolor/{size_dir.name}/apps/{icon_name}{ext}")
            paths += [f"/usr/share/pixmaps/{icon_name}{ext}" for ext in (".png", ".svg", ".xpm")]

        best: tuple[int, bytes, str] | None = None
        for p in dict.fromkeys(paths):
            data = image.read(p, MAX_ICON_BYTES)
            if not data:
                continue
            kind = _sniff_icon(data)
            if not kind:
                continue
            score = _icon_score(data, kind)
            if best is None or score > best[0]:
                best = (score, data, kind)
        return (best[1], best[2]) if best else None
