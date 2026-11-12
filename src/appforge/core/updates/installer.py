"""Safe in-place AppImage replacement. Pure filesystem/network code, no database.

Guarantees (see tests/test_installer.py):
* The new file is downloaded to a hidden temp file *in the same directory*; the active AppImage is
  untouched until the download is complete, size-checked, validated and checksum-verified.
* The previous version is preserved in ``.<Name>.backups/`` (hard-linked, so nothing is copied or
  lost) before the active file is atomically swapped with ``os.replace``.
* Any failure or cancellation removes the temp file and leaves the original and backups intact.
* Filename and executable permissions of the original are preserved.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..formats.appimage import appimage_type, find_squashfs_offset
from .github import user_agent
from .net import urlopen

Progress = Callable[[int, int], None]   # (bytes_done, bytes_total or 0)
MIN_APPIMAGE_BYTES = 64 * 1024
_STALE_PART_SECONDS = 3600


class InstallError(Exception):
    """User-presentable failure; the original application is untouched."""


class InstallCancelled(InstallError):
    pass


@dataclass
class InstallResult:
    path: str
    backup_path: str | None
    checksum: str            # "verified (sha256)" | "not available"
    size: int


# -- helpers ------------------------------------------------------------------------------
def backup_dir_for(path: Path) -> Path:
    stem = re.sub(r"\.appimage$", "", path.name, flags=re.IGNORECASE)
    return path.parent / f".{stem}.backups"


def _safe_label(text: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", (text or "").strip()) or "previous"


def _open(url: str, timeout: float = 30):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    return urlopen(req, timeout=timeout)


def _download(url: str, fd: int, expected: int, progress: Progress | None,
              cancel: threading.Event | None) -> tuple[int, str]:
    sha = hashlib.sha256()
    done = 0
    try:
        with _open(url) as resp, os.fdopen(fd, "wb") as out:
            total = int(resp.headers.get("Content-Length") or expected or 0)
            last = 0.0
            while True:
                if cancel and cancel.is_set():
                    raise InstallCancelled("Update cancelled.")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                now = time.monotonic()
                if progress and now - last > 0.1:
                    progress(done, total)
                    last = now
            out.flush()
            os.fsync(out.fileno())
            if progress:
                progress(done, total)
            if total and done != total:
                raise InstallError(f"The download was incomplete ({done} of {total} bytes).")
    except urllib.error.HTTPError as exc:
        raise InstallError(f"The download failed (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise InstallError(f"The download failed: {getattr(exc, 'reason', exc)}") from exc
    return done, sha.hexdigest()


def _fetch_text(url: str, limit: int = 1024 * 1024) -> str | None:
    try:
        with _open(url, timeout=20) as resp:
            return resp.read(limit).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _parse_checksum_text(text: str, filename: str) -> str | None:
    """Return the hex digest listed for exactly ``filename`` (GNU, BSD or bare-hash formats)."""
    hexp = r"[0-9a-fA-F]{64}(?:[0-9a-fA-F]{64})?"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1 and re.fullmatch(hexp, lines[0]):
        return lines[0].lower()                      # a sidecar file containing only the hash
    for ln in lines:
        m = re.fullmatch(rf"({hexp})\s+\*?(.+)", ln) or None
        if m and os.path.basename(m.group(2).strip()) == filename:
            return m.group(1).lower()
        b = re.fullmatch(rf"SHA\d+ \((.+)\) = ({hexp})", ln)
        if b and os.path.basename(b.group(1)) == filename:
            return b.group(2).lower()
    return None


def find_expected_checksum(asset: dict, assets: list[dict]) -> tuple[str, str] | None:
    """Return (algorithm, hex digest) published for ``asset`` or None when nothing is available."""
    digest = asset.get("digest")
    if digest and ":" in digest:
        algo, _, value = digest.partition(":")
        if algo.lower() in ("sha256", "sha512") and re.fullmatch(r"[0-9a-fA-F]+", value):
            return algo.lower(), value.lower()
    name = asset["name"]
    sidecars = [a for a in assets if a["name"] in (f"{name}.sha256", f"{name}.sha256sum", f"{name}.sha512")]
    sums = [a for a in assets if re.search(r"(sha256sums?|sha512sums?|checksums?)", a["name"], re.I)
            and a["name"] != name]
    for a in sidecars + sums:
        text = _fetch_text(a["url"])
        if not text:
            continue
        hexval = _parse_checksum_text(text, name)
        if hexval:
            return ("sha512" if len(hexval) == 128 else "sha256"), hexval
    return None


def validate_appimage_file(path: Path) -> None:
    if path.stat().st_size < MIN_APPIMAGE_BYTES:
        raise InstallError("The downloaded file is too small to be an AppImage.")
    kind = appimage_type(path)
    if kind is None:
        raise InstallError("The downloaded file is not a valid AppImage (wrong file type).")
    if kind == 2 and find_squashfs_offset(path) is None:
        raise InstallError("The downloaded AppImage is damaged (no embedded file system found).")


def _hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_stale_parts(path: Path) -> None:
    for p in path.parent.glob(f".{path.name}.*.part"):
        try:
            if time.time() - p.stat().st_mtime > _STALE_PART_SECONDS:
                p.unlink()
        except OSError:
            pass


# -- main entry point ---------------------------------------------------------------------
def install_update(path: str | os.PathLike, asset: dict, assets: list[dict], *,
                   old_version: str | None, progress: Progress | None = None,
                   cancel: threading.Event | None = None) -> InstallResult:
    target = Path(path)
    if not target.is_file():
        raise InstallError("The installed AppImage was not found, so it can't be updated.")
    if not os.access(target.parent, os.W_OK):
        raise InstallError(f"AppForge can't write to {target.parent}.")
    size_hint = int(asset.get("size") or 0)
    if size_hint and shutil.disk_usage(target.parent).free < size_hint * 1.1:
        raise InstallError("There isn't enough free disk space to download this update.")

    clean_stale_parts(target)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
    tmp = Path(tmp_name)
    backup: Path | None = None
    try:
        size, sha256_hex = _download(asset["url"], fd, size_hint, progress, cancel)
        validate_appimage_file(tmp)

        expected = find_expected_checksum(asset, assets)
        if expected:
            algo, want = expected
            got = sha256_hex if algo == "sha256" else _hash_file(tmp, algo)
            if got != want:
                raise InstallError(f"Checksum mismatch ({algo}): the download doesn't match what the "
                                   "publisher listed. The update was discarded.")
            checksum = f"verified ({algo})"
        else:
            checksum = "not available"

        # permissions: keep the user's mode, make sure it's executable
        try:
            mode = stat.S_IMODE(target.stat().st_mode) | 0o111
        except OSError:
            mode = 0o755
        os.chmod(tmp, mode)

        if cancel and cancel.is_set():
            raise InstallCancelled("Update cancelled.")

        # preserve the current version, then atomically swap
        bdir = backup_dir_for(target)
        bdir.mkdir(exist_ok=True)
        stem = re.sub(r"\.appimage$", "", target.name, flags=re.IGNORECASE)
        label = _safe_label(old_version)
        backup = bdir / f"{stem}-{label}.AppImage"
        n = 2
        while backup.exists():
            backup = bdir / f"{stem}-{label}-{n}.AppImage"
            n += 1
        try:
            os.link(target, backup)
        except OSError:
            shutil.copy2(target, backup)
        try:
            os.replace(tmp, target)
        except OSError as exc:
            backup.unlink(missing_ok=True)      # nothing changed, drop the just-made backup
            raise InstallError(f"Couldn't replace the AppImage: {exc.strerror or exc}") from exc
        return InstallResult(str(target), str(backup), checksum, size)
    finally:
        tmp.unlink(missing_ok=True)
