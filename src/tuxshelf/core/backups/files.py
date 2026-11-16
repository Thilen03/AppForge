"""Descriptor-based backup boundaries shared by storage and backup management."""
from contextlib import contextmanager
from pathlib import Path
import os
import stat

from ..updates.installer import backup_dir_for


@contextmanager
def backup_directory(entry):
    """Pin the expected directory, refusing symlinks in every path component."""
    folder = Path(os.path.abspath(backup_dir_for(Path(entry.path))))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in folder.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def backup_name(entry, path):
    path = Path(os.path.abspath(path))
    expected = Path(os.path.abspath(backup_dir_for(Path(entry.path))))
    if path.parent != expected or path.suffix.lower() not in ('.appimage', '.bak'):
        raise ValueError('Backup is outside this application’s managed backup folder.')
    return path.name


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def delete_managed_backup(entry, path, current_paths, expected=None):
    """Remove one checked regular backup; never follow a directory or file symlink."""
    name = backup_name(entry, path)
    with backup_directory(entry) as fd:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Backup is not a regular file.')
        if expected is not None and identity(info) != expected:
            raise ValueError('Backup changed since the preview. Refresh and try again.')
        for current in current_paths:
            if os.path.abspath(current) == os.path.abspath(path):
                raise ValueError('Cannot delete an installed application.')
            try:
                active = os.stat(current)
            except FileNotFoundError:
                continue
            if (active.st_dev, active.st_ino) == (info.st_dev, info.st_ino):
                raise ValueError('Backup is linked to an installed application.')
        if identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != identity(info):
            raise ValueError('Backup changed during cleanup.')
        os.unlink(name, dir_fd=fd)
