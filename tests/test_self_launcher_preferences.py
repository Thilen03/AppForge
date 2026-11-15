"""Opt-in launcher creation, safe removal and first-visible-start choice."""
import pytest
from PySide6.QtWidgets import QMessageBox

from test_gui import qapp  # noqa: F401
from test_tray import window  # noqa: F401
from appforge.core.desktop import selflauncher
from appforge.core.paths import applications_dir
from appforge.core.settings import AppSettings
from appforge.ui.settings_dialog import SettingsDialog


def entry():
    return applications_dir() / selflauncher.SELF_FILENAME


def test_create_refresh_remove_and_source_command(service, monkeypatch):
    monkeypatch.delenv('APPIMAGE', raising=False)
    selflauncher.set_enabled(True)
    dest = entry()
    text = dest.read_text()
    assert 'StartupWMClass=appforge' in text
    assert '-m appforge' in text and 'PYTHONPATH=' in text
    assert selflauncher.launcher_installed()
    before = dest.stat().st_mtime_ns
    selflauncher.set_enabled(True)
    assert dest.stat().st_mtime_ns == before
    selflauncher.set_enabled(False)
    assert not dest.exists()
    selflauncher.set_enabled(False)


def test_appimage_command_and_refresh_after_move(service, tmp_path, monkeypatch):
    appimage = tmp_path / 'AppForge one.AppImage'
    appimage.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(appimage))
    selflauncher.set_enabled(True)
    assert f'Exec="{appimage}" %F' in entry().read_text()
    moved = appimage.rename(tmp_path / 'AppForge two.AppImage')
    monkeypatch.setenv('APPIMAGE', str(moved))
    selflauncher.set_enabled(True)
    assert str(moved) in entry().read_text()
    assert str(appimage) not in entry().read_text()


@pytest.mark.parametrize('kind', ['foreign', 'directory', 'symlink', 'broken_symlink'])
def test_protect_unmanaged_paths(service, tmp_path, kind):
    dest = entry()
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / 'target'
    if kind == 'foreign':
        dest.write_text('[Desktop Entry]\nName=Personal\n')
    elif kind == 'directory':
        dest.mkdir()
    else:
        if kind == 'symlink':
            target.write_text('X-AppForge-Self=true\n')
        dest.symlink_to(target)
    with pytest.raises(selflauncher.SelfLauncherError):
        selflauncher.set_enabled(True)
    if kind == 'foreign':
        selflauncher.set_enabled(False)
        assert 'Personal' in dest.read_text()
    else:
        with pytest.raises(selflauncher.SelfLauncherError):
            selflauncher.set_enabled(False)
    if target.exists():
        assert target.read_text() == 'X-AppForge-Self=true\n'
    assert dest.exists() or dest.is_symlink()


def test_atomic_write_error_preserves_existing(service, monkeypatch):
    selflauncher.set_enabled(True)
    original = entry().read_bytes()
    monkeypatch.setattr(selflauncher, 'render_self_entry', lambda *a, **kw: 'changed')
    monkeypatch.setattr(selflauncher.os, 'replace', lambda *a: (_ for _ in ()).throw(PermissionError('read only')))
    with pytest.raises(selflauncher.SelfLauncherError, match='read only'):
        selflauncher.set_enabled(True)
    assert entry().read_bytes() == original
    assert list(entry().parent.glob('.appforge-*.tmp')) == []


@pytest.mark.parametrize('yes', [True, False])
def test_first_start_choice_once_and_before_notes(qapp, window, yes):
    window._live = True
    window._show_startup_dialogs()
    assert window._launcher_prompt is None  # hidden startup waits
    window.show()
    qapp.processEvents()
    box = window._launcher_prompt
    assert box is not None and box.isVisible()
    assert window._appforge_notes is None
    window._show_startup_dialogs()
    assert window._launcher_prompt is box
    box.button(QMessageBox.Yes if yes else QMessageBox.No).click()
    qapp.processEvents()
    assert window.settings.self_launcher_prompted
    assert window.settings.self_launcher_enabled == yes
    assert selflauncher.launcher_installed() == yes
    assert window._appforge_notes.isVisible()
    window.hide()
    window.show()
    qapp.processEvents()
    assert window._launcher_prompt is None
    assert AppSettings(window.service.db).self_launcher_enabled == yes


def test_settings_add_cancel_remove_and_no_recreation(qapp, window):
    settings = window.settings
    dialog = SettingsDialog(settings, False)
    dialog.launcher_cb.setChecked(True)
    dialog.reject()
    assert not entry().exists()
    assert not settings.self_launcher_prompted
    dialog = SettingsDialog(settings, False)
    dialog.launcher_cb.setChecked(True)
    dialog._save()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert entry().is_file() and settings.self_launcher_enabled
    dialog = SettingsDialog(settings, False)
    dialog.launcher_cb.setChecked(False)
    dialog._save()
    assert not entry().exists() and not settings.self_launcher_enabled
    window._refresh_self_launcher()
    assert not entry().exists()
    assert settings.self_launcher_prompted


def test_settings_reports_error_and_keeps_preferences(qapp, service, monkeypatch):
    settings = AppSettings(service.db)
    dialog = SettingsDialog(settings, False)
    dialog.launcher_cb.setChecked(True)
    def fail(enabled):
        raise selflauncher.SelfLauncherError('Permission denied')
    monkeypatch.setattr(selflauncher, 'set_enabled', fail)
    dialog._save()
    assert 'Permission denied' in dialog.error_lbl.text()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert not settings.self_launcher_enabled
    assert not settings.self_launcher_prompted


def test_existing_launcher_adopted_and_removed_choice_preserved(qapp, window):
    selflauncher.set_enabled(True)
    window._refresh_self_launcher()
    assert window.settings.self_launcher_enabled
    assert window.settings.self_launcher_prompted
    entry().unlink()
    window._refresh_self_launcher()
    assert entry().is_file()  # opted-in repair
    window.settings.self_launcher_enabled = False
    selflauncher.set_enabled(False)
    window._refresh_self_launcher()
    assert not entry().exists()


def test_unreadable_launcher_does_not_break_preferences(service):
    dest = entry()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xfe")
    assert not AppSettings(service.db).self_launcher_enabled
    with pytest.raises(selflauncher.SelfLauncherError):
        selflauncher.set_enabled(True)
    assert dest.read_bytes() == b"\xff\xfe"


def test_prompt_creation_failure_is_reported_and_retryable(qapp, window, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    def fail(enabled):
        raise selflauncher.SelfLauncherError('Permission denied')
    monkeypatch.setattr(selflauncher, 'set_enabled', fail)
    window.show()
    window._show_startup_dialogs()
    window._launcher_prompt.button(QMessageBox.Yes).click()
    qapp.processEvents()
    assert messages == ['Permission denied']
    assert not window.settings.self_launcher_prompted
    assert not window.settings.self_launcher_enabled
    assert window._appforge_notes is None


def test_utility_category_for_all_appforge_entries(service):
    from pathlib import Path
    from appforge.core import selfintegration
    selflauncher.set_enabled(True)
    assert 'Categories=Utility;' in entry().read_text().splitlines()
    assert 'Categories=Utility;' in selfintegration.render_self_entry(['/test'], 'icon').splitlines()
    packaged = Path(__file__).resolve().parents[1] / 'packaging/appforge.desktop'
    assert [line for line in packaged.read_text().splitlines() if line.startswith('Categories=')] == ['Categories=Utility;']


def test_unchanged_appimage_does_not_write_or_prompt(qapp, window, tmp_path, monkeypatch):
    image = tmp_path / 'AppForge.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    selflauncher.set_enabled(True)
    before = entry().stat()
    icon = entry().parent.parent / 'appforge.png'
    icon_before = icon.stat().st_mtime_ns
    window._refresh_self_launcher()
    assert selflauncher.moved_appimage() is None
    assert entry().stat().st_mtime_ns == before.st_mtime_ns
    assert entry().stat().st_ino == before.st_ino
    assert icon.stat().st_mtime_ns == icon_before
    window.show()
    window._show_startup_dialogs()
    assert window._launcher_prompt is None


@pytest.mark.parametrize('yes', [True, False])
@pytest.mark.parametrize('move', ['folder', 'rename'])
def test_moved_appimage_requires_consent(qapp, window, tmp_path, monkeypatch, yes, move):
    image = tmp_path / 'AppForge old.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    selflauncher.set_enabled(True)
    original = entry().read_bytes()
    old_stat = entry().stat()
    directory = tmp_path / 'New folder' if move == 'folder' else tmp_path
    directory.mkdir(exist_ok=True)
    moved = image.rename(directory / ('AppForge old.AppImage' if move == 'folder' else 'Renamed.AppImage'))
    monkeypatch.setenv('APPIMAGE', str(moved))
    window._refresh_self_launcher()
    assert entry().read_bytes() == original
    assert entry().stat().st_mtime_ns == old_stat.st_mtime_ns
    window._show_startup_dialogs()
    assert window._launcher_prompt is None  # hidden login startup defers the question
    window.show()
    window._show_startup_dialogs()
    prompt = window._launcher_prompt
    assert 'moved' in prompt.windowTitle()
    assert str(image) in prompt.informativeText()
    assert str(moved) in prompt.informativeText()
    assert window._appforge_notes is None
    prompt.button(QMessageBox.Yes if yes else QMessageBox.No).click()
    qapp.processEvents()
    assert window._launcher_prompt is None
    if yes:
        assert str(moved) in entry().read_text()
        assert str(image) not in entry().read_text()
        assert selflauncher.moved_appimage() is None
    else:
        assert entry().read_bytes() == original
        # Saving unrelated settings must not silently repair the declined shortcut.
        dialog = SettingsDialog(window.settings, False)
        dialog._save()
        assert dialog.result() == dialog.DialogCode.Accepted
        assert entry().read_bytes() == original
        window._show_startup_dialogs()
        assert window._launcher_prompt is None  # once per session
        window._launcher_move_offered = False  # simulate the next launch
        window._refresh_self_launcher()
        window._show_startup_dialogs()
        assert window._launcher_prompt is not None
        window._launcher_prompt.button(QMessageBox.No).click()


def test_move_repair_failure_preserves_shortcut(qapp, window, tmp_path, monkeypatch):
    image = tmp_path / 'old.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    selflauncher.set_enabled(True)
    original = entry().read_bytes()
    moved = image.rename(tmp_path / 'new.AppImage')
    monkeypatch.setenv('APPIMAGE', str(moved))
    window._refresh_self_launcher()
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    def fail(enabled):
        raise selflauncher.SelfLauncherError('Read only')
    monkeypatch.setattr(selflauncher, 'set_enabled', fail)
    window.show()
    window._show_startup_dialogs()
    window._launcher_prompt.button(QMessageBox.Yes).click()
    assert messages == ['Read only']
    assert entry().read_bytes() == original
    assert window._pending_launcher_move is not None


def test_disabled_shortcut_does_not_offer_move_repair(qapp, window, tmp_path, monkeypatch):
    image = tmp_path / 'old.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    selflauncher.set_enabled(True)
    moved = image.rename(tmp_path / 'new.AppImage')
    monkeypatch.setenv('APPIMAGE', str(moved))
    window.settings.self_launcher_enabled = False
    window.settings.self_launcher_prompted = True
    original = entry().read_bytes()
    window._refresh_self_launcher()
    window.show()
    window._show_startup_dialogs()
    assert window._launcher_prompt is None
    assert entry().read_bytes() == original


def test_existing_same_location_shortcut_migrates_to_utility_without_prompt(qapp, window, tmp_path, monkeypatch):
    image = tmp_path / 'AppForge.AppImage'
    image.write_bytes(b'appimage')
    monkeypatch.setenv('APPIMAGE', str(image))
    selflauncher.set_enabled(True)
    entry().write_text(entry().read_text().replace('Categories=Utility;', 'Categories=System;Utility;'))
    window._refresh_self_launcher()
    assert 'Categories=Utility;' in entry().read_text().splitlines()
    window.show()
    window._show_startup_dialogs()
    assert window._launcher_prompt is None
