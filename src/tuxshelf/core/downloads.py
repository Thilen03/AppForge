"""Discover and safely download a new portable app. No database writes or execution."""
from __future__ import annotations

import os
import hashlib
import stat
import ctypes
import errno
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .discovery import _safe_path
from .library import LibraryError, normalize_path
from .updates.assets import compatible_arch, host_arch, is_appimage_name, is_executable_name
from .updates.github import Asset, GitHubError, Release
from .updates.installer import (
    InstallCancelled, InstallError, download_verified, find_expected_checksum, validate_for_format,
)
from .updates.providers import client_for, parse_source
from .updates.version import display_version, parse_version
from .formats.appimage import version_from_filename


@dataclass
class DownloadChoice:
    source: str
    release: Release
    asset: Asset
    format_id: str

    @property
    def version(self) -> str:
        if parse_version(self.release.tag) is not None:
            return display_version(self.release.tag)
        return (version_from_filename(self.release.name) or version_from_filename(self.asset.name)
                or self.release.tag)


@dataclass
class DownloadResult:
    path: str
    choice: DownloadChoice
    checksum: str
    signature: tuple


def file_signature(path) -> tuple:
    st = Path(path).stat()
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def validate_downloaded(result: DownloadResult) -> None:
    path = Path(result.path)
    try:
        if not _safe_path(path) or file_signature(path) != result.signature:
            raise LibraryError("The downloaded file changed or moved. Choose it again as a local file.")
    except OSError as exc:
        raise LibraryError(f"The downloaded file is no longer available: {exc}") from exc


def safe_filename(name: str) -> bool:
    return (bool(name) and name not in (".", "..") and not name.startswith(".")
            and not any(c in name for c in '/\\') and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def download_choices(source: str, releases: list[Release], *, include_prereleases=False,
                     arch: str | None = None) -> list[DownloadChoice]:
    arch = arch or host_arch()
    choices = []
    for release in releases:
        if release.draft or (release.prerelease and not include_prereleases):
            continue
        for asset in release.assets:
            try:
                url = urlsplit(asset.url)
                usable_url = url.scheme == 'https' and url.hostname and not url.username and not url.password
            except ValueError:
                usable_url = False
            if (not usable_url or not safe_filename(asset.name) or not compatible_arch(asset.name, arch)):
                continue
            fmt = ('appimage' if is_appimage_name(asset.name) else
                   'executable' if is_executable_name(asset.name) else None)
            if fmt:
                choices.append(DownloadChoice(source, release, asset, fmt))
    return choices


def fetch_releases(source: str, *, client=None, token=None, cancel=None) -> tuple[str, list[Release]]:
    ref = parse_source(source)
    if ref is None:
        raise GitHubError("Enter a supported repository or release URL.", "invalid")
    if cancel and cancel.is_set():
        raise InstallCancelled("Search cancelled.")
    releases = (client or client_for(ref, token)).releases(ref.owner, ref.name)
    if cancel and cancel.is_set():
        raise InstallCancelled("Search cancelled.")
    return ref.url, releases


def _publish_exclusive(root_fd: int, temporary: str, name: str) -> None:
    """Atomic no-replace rename on Linux, including filesystems without hard links."""
    rename = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if rename is not None:
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(root_fd, os.fsencode(temporary), root_fd, os.fsencode(name), 1) == 0:
            return
        code = ctypes.get_errno()
        if code not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise OSError(code, os.strerror(code), name)
    # Older kernels/filesystems: a hard link is also atomic and never overwrites.
    os.link(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
    os.unlink(temporary, dir_fd=root_fd)


def _use_existing(choice: DownloadChoice, root: Path, root_fd: int, *,
                  cancel=None, progress=None) -> DownloadResult:
    target = root / choice.asset.name
    if not _safe_path(target):
        raise InstallError("The existing application must be a regular file without symlinks.")
    fd = os.open(choice.asset.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise InstallError("The existing application must be a regular file.")
        signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if choice.asset.size and info.st_size != choice.asset.size:
            raise InstallError("The existing file's size does not match the selected release. Nothing was overwritten.")
        opened = Path(f'/proc/self/fd/{fd}')
        validate_for_format(opened, choice.format_id)
        expected = find_expected_checksum(choice.asset.to_dict(), [a.to_dict() for a in choice.release.assets])
        checksum = "not available"
        if expected:
            algo, want = expected
            digest = hashlib.new(algo)
            count = 0
            while count < info.st_size:
                if cancel and cancel.is_set():
                    raise InstallCancelled("File verification cancelled.")
                chunk = os.read(fd, min(1 << 20, info.st_size - count))
                if not chunk:
                    break
                digest.update(chunk)
                count += len(chunk)
                if progress:
                    progress(count, info.st_size)
            if digest.hexdigest() != want:
                raise InstallError(f"Checksum mismatch ({algo}): the existing file does not match the selected release. "
                                   "Nothing was overwritten.")
            checksum = f"verified ({algo})"
        result = DownloadResult(str(target), choice, checksum, signature)
        validate_downloaded(result)
        if cancel and cancel.is_set():
            raise InstallCancelled("File verification cancelled.")
        return result
    finally:
        os.close(fd)


def download_application(choice: DownloadChoice, folder: str, *, progress=None,
                         cancel: threading.Event | None = None) -> DownloadResult:
    # Revalidate input even when invoked outside the UI.
    if choice not in download_choices(choice.source, [choice.release], include_prereleases=True):
        raise InstallError("This release file is not a compatible application download.")
    root = Path(normalize_path(folder))
    if not _safe_path(root) or not root.is_dir():
        raise InstallError("Choose an existing folder without symlinks or backup directories.")
    if not os.access(root, os.W_OK):
        raise InstallError("This folder is not writable. Choose another download folder.")
    if cancel and cancel.is_set():
        raise InstallCancelled("Download cancelled.")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise InstallError(f"Couldn't open the download folder: {exc}") from exc
    temp_name = f'.tuxshelf-{uuid.uuid4().hex}.part'
    try:
        if os.path.lexists(root / choice.asset.name):
            return _use_existing(choice, root, root_fd, cancel=cancel, progress=progress)
        if choice.asset.size and shutil.disk_usage(root).free < choice.asset.size * 1.1:
            raise InstallError("There isn't enough free disk space for this download.")
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root_fd)
        # A stable directory handle keeps downloads/cleanup inside the chosen directory
        # if another process renames it. Linux is the supported platform.
        temporary = Path(f'/proc/self/fd/{root_fd}/{temp_name}')
        _, checksum = download_verified(temporary, fd, choice.asset.to_dict(),
                                        [a.to_dict() for a in choice.release.assets],
                                        format_id=choice.format_id, progress=progress, cancel=cancel)
        os.chmod(temporary, 0o755)
        verified_signature = file_signature(temporary)
        current = root.stat()
        original = os.fstat(root_fd)
        if not _safe_path(root) or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise InstallError("The download folder changed. Choose it again.")
        if cancel and cancel.is_set():
            raise InstallCancelled("Download cancelled.")
        try:
            _publish_exclusive(root_fd, temp_name, choice.asset.name)
        except FileExistsError:
            return _use_existing(choice, root, root_fd, cancel=cancel, progress=progress)
        target = root / choice.asset.name
        signature = file_signature(target)
        # Renaming/linking can change ctime, but never this verified file identity.
        if signature[:4] != verified_signature[:4]:
            raise InstallError("The downloaded file changed before it could be reviewed. Choose it again as a local file.")
        return DownloadResult(str(target), choice, checksum, signature)
    except OSError as exc:
        raise InstallError(f"Couldn't save the application: {exc}") from exc
    finally:
        try:
            os.unlink(temp_name, dir_fd=root_fd)
        except FileNotFoundError:
            pass
        os.close(root_fd)
