"""Rebranding must retain real library data and ownership boundaries."""
import hashlib
import json
from pathlib import Path

import pytest

from tuxshelf import APP_DISPLAY_NAME, APP_ID
from tuxshelf.core import autostart, paths
from tuxshelf.core.compat import LEGACY_ID, LEGACY_NAME
from tuxshelf.core.database import Database
from tuxshelf.core.desktop import selflauncher
from tuxshelf.core.desktop.service import DesktopService
from tuxshelf.core.instance import InstanceGuard, default_socket_path
from tuxshelf.core.library_transfer import export_library, read_export, TransferError
from tuxshelf.core.models import AppEntry
from tuxshelf.core.settings import AppSettings


@pytest.fixture
def clean_paths(tmp_path, monkeypatch):
    for prefix in (APP_ID.upper(), LEGACY_ID.upper()):
        for suffix in ('DATA_DIR', 'APPLICATIONS_DIR'):
            monkeypatch.delenv(f'{prefix}_{suffix}', raising=False)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'share'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    return tmp_path


def test_new_installation_identity_and_paths(clean_paths):
    assert APP_DISPLAY_NAME == 'TuxShelf' and APP_ID == 'tuxshelf'
    assert paths.data_dir() == clean_paths / 'share/tuxshelf'
    assert paths.applications_dir() == clean_paths / 'share/applications'
    assert selflauncher.launcher_path().name == 'tuxshelf.desktop'
    assert autostart.entry_path().name == 'tuxshelf.desktop'


def test_existing_library_settings_and_absolute_icon_paths_survive(clean_paths):
    old = clean_paths / 'share' / LEGACY_ID
    old.mkdir(parents=True)
    icon = old / 'icons/tool.png'
    icon.parent.mkdir()
    icon.write_bytes(b'unchanged-icon')
    db = Database(old / 'library.db')
    entry = db.add(AppEntry(name='Tool', path='/opt/tool', icon_path=str(icon)))
    AppSettings(db).theme_mode = 'dark'
    db.close()
    assert paths.data_dir() == old
    assert not (clean_paths / 'share/tuxshelf').exists()
    restored = Database(paths.database_path())
    try:
        assert AppSettings(restored).theme_mode == 'dark'
        assert restored.get(entry.id).icon_path == str(icon)
        assert icon.read_bytes() == b'unchanged-icon'
    finally:
        restored.close()


def test_current_directory_wins_without_merging_libraries(clean_paths):
    old = clean_paths / 'share' / LEGACY_ID
    old.mkdir(parents=True)
    (old / 'library.db').write_bytes(b'old-library')
    new = clean_paths / 'share/tuxshelf'
    new.mkdir()
    (new / 'library.db').write_bytes(b'new-library')
    assert paths.data_dir() == new
    assert (old / 'library.db').read_bytes() == b'old-library'
    assert (new / 'library.db').read_bytes() == b'new-library'


def test_empty_current_directory_does_not_hide_existing_library(clean_paths):
    old = clean_paths / 'share' / LEGACY_ID
    old.mkdir(parents=True)
    (old / 'library.db').write_bytes(b'existing-library')
    (clean_paths / 'share/tuxshelf').mkdir()
    assert paths.data_dir() == old


def test_portable_environment_aliases_and_precedence(clean_paths, monkeypatch):
    legacy_data = clean_paths / 'portable-old'
    monkeypatch.setenv(f'{LEGACY_ID.upper()}_DATA_DIR', str(legacy_data))
    assert paths.data_dir() == legacy_data
    assert paths.applications_dir() == legacy_data / 'applications'
    monkeypatch.setenv('TUXSHELF_DATA_DIR', str(clean_paths / 'portable-new'))
    assert paths.data_dir() == clean_paths / 'portable-new'
    monkeypatch.setenv(f'{LEGACY_ID.upper()}_APPLICATIONS_DIR', str(clean_paths / 'old-menu'))
    assert paths.applications_dir() == clean_paths / 'old-menu'
    monkeypatch.setenv('TUXSHELF_APPLICATIONS_DIR', str(clean_paths / 'new-menu'))
    assert paths.applications_dir() == clean_paths / 'new-menu'


@pytest.mark.parametrize('prefix', (APP_ID, LEGACY_ID))
def test_both_export_generations_import(clean_paths, prefix):
    export = clean_paths / 'library.json'
    export.write_text(json.dumps({'format': f'{prefix}-library', 'schema_version': 1,
                                 f'{prefix}_version': '0.6.5', 'applications': []}))
    assert read_export(export) == []
    export_library([], export)
    document = json.loads(export.read_text())
    assert document['format'] == 'tuxshelf-library'
    assert 'tuxshelf_version' in document and f'{LEGACY_ID}_version' not in document


def test_legacy_exports_keep_strict_field_validation(clean_paths):
    export = clean_paths / 'library.json'
    export.write_text(json.dumps({'format': f'{LEGACY_ID}-library', 'schema_version': 1,
                                 f'{LEGACY_ID}_version': '0.6.5', 'applications': [],
                                 'github_token': 'must-not-import'}))
    with pytest.raises(TransferError, match='Unsupported export fields'):
        read_export(export)


def test_existing_app_shortcut_is_refreshed_without_duplicate_or_lost_pin(clean_paths):
    desktop = DesktopService(clean_paths / 'menu')
    desktop.directory.mkdir()
    entry = AppEntry(name='Tool', path='/opt/tool')
    legacy = desktop.directory / f'{LEGACY_ID}-{entry.id}.desktop'
    legacy.write_text(f'[Desktop Entry]\nX-{LEGACY_NAME}-Id={entry.id}\nTryExec=/opt/tool\n')
    assert desktop.exists(entry.id)
    assert desktop.write_entry(entry)
    assert desktop.entry_path(entry.id) == legacy
    assert '# Managed by TuxShelf.' in legacy.read_text()
    assert f'X-TuxShelf-Id={entry.id}' in legacy.read_text()
    assert len(list(desktop.directory.glob('*.desktop'))) == 1
    assert desktop.list_managed()[0].app_id == entry.id
    assert desktop.remove(entry.id) and not legacy.exists()


@pytest.mark.parametrize('kind', ('foreign', 'symlink'))
def test_foreign_and_symlink_legacy_app_shortcuts_are_not_adopted(clean_paths, kind):
    desktop = DesktopService(clean_paths / 'menu')
    desktop.directory.mkdir()
    entry = AppEntry(name='Tool', path='/opt/tool')
    legacy = desktop.directory / f'{LEGACY_ID}-{entry.id}.desktop'
    target = clean_paths / 'foreign.desktop'
    target.write_text(f'X-{LEGACY_NAME}-Id={entry.id}\n')
    if kind == 'symlink':
        legacy.symlink_to(target)
    else:
        legacy.write_text('Name=Foreign\n')
    before = legacy.read_bytes()
    assert desktop.entry_path(entry.id).name.startswith('tuxshelf-')
    desktop.write_entry(entry)
    assert legacy.read_bytes() == before and target.exists()


def test_existing_self_launcher_keeps_pin_and_move_consent(clean_paths, monkeypatch):
    parent = paths.applications_dir()
    parent.mkdir(parents=True)
    image = clean_paths / 'TuxShelf.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    legacy = parent / f'{LEGACY_ID}.desktop'
    legacy.write_text(f'[Desktop Entry]\nName={LEGACY_NAME}\nX-{LEGACY_NAME}-Self=true\n'
                      'TryExec=/previous/location.AppImage\n')
    before = legacy.read_bytes()
    assert selflauncher.launcher_installed()
    assert selflauncher.moved_appimage() == ('/previous/location.AppImage', str(image))
    assert legacy.read_bytes() == before
    selflauncher.set_enabled(True)  # the operation invoked after the user's repair choice
    assert 'Name=TuxShelf\n' in legacy.read_text()
    assert 'StartupWMClass=tuxshelf\n' in legacy.read_text()
    assert selflauncher.moved_appimage() is None
    assert selflauncher.launcher_path() == legacy
    assert not (parent / 'tuxshelf.desktop').exists()
    selflauncher.set_enabled(False)
    assert not legacy.exists()


def test_legacy_autostart_refresh_and_removal(clean_paths, monkeypatch):
    legacy = clean_paths / 'config/autostart' / f'{LEGACY_ID}.desktop'
    legacy.parent.mkdir(parents=True)
    legacy.write_text(f'Name={LEGACY_NAME}\nX-{LEGACY_NAME}-Autostart=true\n')
    monkeypatch.setattr(autostart, 'startup_command', lambda: ['/opt/TuxShelf.AppImage'])
    assert autostart.entry_path() == legacy
    autostart.set_enabled(True)
    assert 'Name=TuxShelf\n' in legacy.read_text()
    assert 'X-TuxShelf-Autostart=true\n' in legacy.read_text()
    assert len(list(legacy.parent.glob('*.desktop'))) == 1
    autostart.set_enabled(False)
    assert not legacy.exists()


def test_existing_instance_guard_namespace_is_retained(clean_paths, monkeypatch):
    old = clean_paths / 'share' / LEGACY_ID
    old.mkdir(parents=True)
    (old / 'library.db').touch()
    monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
    key = hashlib.sha1(str(old.resolve()).encode()).hexdigest()[:10]
    guard = InstanceGuard()
    assert guard.lock_path == old / f'{LEGACY_ID}.lock'
    assert Path(default_socket_path()).name.endswith(f'-{key}.sock')
    assert Path(default_socket_path()).name.startswith(LEGACY_ID + '-')


@pytest.mark.parametrize('existing', (False, True))
def test_window_geometry_is_carried_forward_without_overwriting(existing, monkeypatch):
    from PySide6 import QtCore
    from tuxshelf.app import _migrate_window_settings
    current = {'geometry': b'current-position'} if existing else {}
    legacy = {'geometry': b'previous-position'}

    class Settings:
        def __init__(self, *identity):
            self.values = legacy if identity == (LEGACY_ID, LEGACY_ID) else current

        def contains(self, key):
            return key in self.values

        def value(self, key):
            return self.values.get(key)

        def setValue(self, key, value):
            self.values[key] = value

    monkeypatch.setattr(QtCore, 'QSettings', Settings)
    _migrate_window_settings()
    assert current['geometry'] == (b'current-position' if existing else b'previous-position')
    assert legacy['geometry'] == b'previous-position'
