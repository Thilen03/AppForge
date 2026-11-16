"""Login startup and minimize-to-tray without touching the user's desktop config."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from test_gui import qapp, wait_for  # noqa: F401
from test_tray import window  # noqa: F401
from tuxshelf.core import autostart
from tuxshelf.core.settings import AppSettings
from tuxshelf.ui.main_window import MainWindow
from tuxshelf.ui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.delenv('APPIMAGE', raising=False)
    monkeypatch.delenv('APPDIR', raising=False)
    return tmp_path / 'config'


def test_defaults_and_roundtrip(service):
    settings = AppSettings(service.db)
    assert not settings.start_at_login and not settings.start_minimized
    settings.start_at_login = settings.start_minimized = True
    restored = AppSettings(service.db)
    assert restored.start_at_login and restored.start_minimized


def test_create_refresh_disable_and_unrelated_files(config, monkeypatch):
    command = ['/opt/My App $stuff%/TuxShelf.AppImage']
    monkeypatch.setattr(autostart, 'startup_command', lambda: command)
    autostart.set_enabled(True)
    dest = autostart.entry_path()
    text = dest.read_text()
    assert '--autostart' in text and autostart.MARKER in text
    assert '%%' in text and '\\$' in text
    stamp = dest.stat().st_mtime_ns
    autostart.set_enabled(True)
    assert dest.stat().st_mtime_ns == stamp
    command[0] = '/opt/Relocated.AppImage'
    autostart.set_enabled(True)
    assert 'Relocated.AppImage' in dest.read_text()
    other = dest.with_name('other.desktop')
    other.write_text('Keep me')
    autostart.set_enabled(False)
    assert not dest.exists() and other.read_text() == 'Keep me'
    autostart.set_enabled(False)


@pytest.mark.parametrize('kind', ['foreign', 'symlink', 'directory'])
def test_preserves_unowned_or_invalid_entry(config, tmp_path, kind):
    dest = autostart.entry_path()
    dest.parent.mkdir(parents=True)
    if kind == 'foreign':
        dest.write_text('[Desktop Entry]\nName=User entry\n')
    elif kind == 'directory':
        dest.mkdir()
    else:
        target = tmp_path / 'target'
        target.write_text(autostart.MARKER)
        dest.symlink_to(target)
    with pytest.raises(autostart.AutostartError):
        autostart.set_enabled(True)
    if kind == 'foreign':
        autostart.set_enabled(False)
        assert 'User entry' in dest.read_text()
    else:
        with pytest.raises(autostart.AutostartError):
            autostart.set_enabled(False)
        assert dest.is_symlink() if kind == 'symlink' else dest.is_dir()


def test_failed_atomic_write_keeps_old_entry(config, monkeypatch):
    monkeypatch.setattr(autostart, 'startup_command', lambda: ['/opt/Old.AppImage'])
    autostart.set_enabled(True)
    dest = autostart.entry_path()
    original = dest.read_bytes()
    monkeypatch.setattr(autostart, 'startup_command', lambda: ['/opt/New.AppImage'])
    monkeypatch.setattr(autostart.os, 'replace', lambda *args: (_ for _ in ()).throw(PermissionError('Read only')))
    with pytest.raises(autostart.AutostartError, match='Read only'):
        autostart.set_enabled(True)
    assert dest.read_bytes() == original
    assert list(dest.parent.iterdir()) == [dest]


def test_stable_appimage_and_source_commands(tmp_path, monkeypatch):
    exe = tmp_path / 'Tux Shelf.AppImage'
    exe.write_text('fixture')
    monkeypatch.setenv('APPIMAGE', str(exe))
    assert autostart.startup_command() == [str(exe.resolve())]
    monkeypatch.delenv('APPIMAGE')
    command = autostart.startup_command()
    assert command[0] == 'env' and command[-2:] == ['-m', 'tuxshelf']
    assert command[1].startswith('PYTHONPATH=')
    monkeypatch.setattr(autostart.sys, 'frozen', True, raising=False)
    monkeypatch.setenv('APPDIR', '/tmp/transient')
    with pytest.raises(autostart.AutostartError, match='permanent'):
        autostart.startup_command()


def test_invalid_command_and_relative_config(monkeypatch, tmp_path):
    with pytest.raises(autostart.AutostartError):
        autostart.render_entry(['/tmp/bad\nExec=anything'])
    monkeypatch.setenv('XDG_CONFIG_HOME', 'relative')
    monkeypatch.setenv('HOME', str(tmp_path))
    assert autostart.entry_path() == Path.home() / '.config/autostart/tuxshelf.desktop'


def test_settings_enable_minimized_implies_background_and_cancel_is_noop(qapp, service):
    settings = AppSettings(service.db)
    dlg = SettingsDialog(settings, True)
    assert not dlg.start_minimized_cb.isEnabled()
    dlg.startup_cb.setChecked(True)
    assert dlg.start_minimized_cb.isEnabled()
    dlg.start_minimized_cb.setChecked(True)
    assert dlg.bg_cb.isChecked()
    dlg.reject()
    assert not autostart.entry_path().exists() and not settings.start_at_login
    dlg = SettingsDialog(settings, True)
    dlg.startup_cb.setChecked(True)
    dlg.start_minimized_cb.setChecked(True)
    dlg._save()
    assert dlg.result() == QDialog.Accepted
    assert settings.start_at_login and settings.start_minimized and settings.run_in_background
    assert autostart.entry_path().exists()
    restored = SettingsDialog(AppSettings(service.db), True)
    assert restored.startup_cb.isChecked() and restored.start_minimized_cb.isChecked()
    restored.bg_cb.setChecked(False)
    assert not restored.start_minimized_cb.isChecked()
    restored.startup_cb.setChecked(False)
    restored._save()
    assert not autostart.entry_path().exists()
    assert not settings.start_at_login


def test_settings_show_autostart_write_errors(qapp, service, monkeypatch):
    dlg = SettingsDialog(AppSettings(service.db), True)
    dlg.startup_cb.setChecked(True)
    dlg.token_edit.setText('new-token')
    monkeypatch.setattr(autostart, 'set_enabled', lambda *a: (_ for _ in ()).throw(autostart.AutostartError('Permission denied')))
    dlg._save()
    assert dlg.result() != QDialog.Accepted
    assert 'Permission denied' in dlg.error_lbl.text()
    assert not dlg.settings.start_at_login
    assert dlg.settings.github_token == ''


def test_no_tray_disables_only_hidden_startup_option(qapp, service):
    dlg = SettingsDialog(AppSettings(service.db), False)
    dlg.startup_cb.setChecked(True)
    assert dlg.startup_cb.isEnabled() and not dlg.start_minimized_cb.isEnabled()
    dlg._save()
    assert dlg.settings.start_at_login and not dlg.settings.start_minimized


def test_minimize_hides_to_tray_and_restores(window, qapp):
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    window.showMinimized()
    assert wait_for(qapp, lambda: not window.isVisible())
    assert window.tray.visible
    window.bring_to_front()
    assert window.isVisible() and not window.isMinimized()
    window.showMinimized()
    assert wait_for(qapp, lambda: not window.isVisible())


def test_normal_minimize_without_background(window, qapp):
    window.show()
    window.showMinimized()
    qapp.processEvents()
    assert window.isVisible() and window.isMinimized()
    window.bring_to_front()
    window.settings.run_in_background = True
    window.tray = None
    window.showMinimized()
    qapp.processEvents()
    assert window.isVisible() and window.isMinimized()


def test_restore_before_deferred_hide_is_not_hidden(window, qapp):
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    window.showMinimized()
    window.bring_to_front()
    qapp.processEvents()
    assert window.isVisible() and not window.isMinimized()


@pytest.mark.parametrize('login,hidden,background,expected', [
    (True, True, True, False), (False, True, True, True),
    (True, False, True, True), (True, True, False, True),
])
def test_initial_visibility(window, login, hidden, background, expected):
    window.settings.start_at_login = True
    window.settings.start_minimized = hidden
    window.settings.run_in_background = background
    window.apply_settings()
    window.show_initial(login)
    assert window.isVisible() is expected


def test_hidden_startup_falls_back_without_tray(qapp, service):
    w = MainWindow(service)
    w.settings.start_at_login = w.settings.start_minimized = w.settings.run_in_background = True
    w.show_initial(True)
    assert w.isVisible()
    w._quitting = True
    w.close()


def test_login_duplicate_does_not_raise_existing_window():
    from tuxshelf.app import activate_window
    from types import SimpleNamespace
    opened = []
    w = SimpleNamespace(bring_to_front=lambda: opened.append(True))
    activate_window(w, ['--autostart'])
    assert not opened
    activate_window(w, [])
    assert opened == [True]


def test_self_update_prompt_deferred_until_opening(window, qapp, monkeypatch):
    window.settings.run_in_background = True
    window.apply_settings()
    found = object()
    window._offer_self_update(found)
    assert window._pending_self_update is found
    seen = []
    monkeypatch.setattr(window, '_offer_self_update', seen.append)
    window.bring_to_front()
    qapp.processEvents()
    assert seen == [found] and window._pending_self_update is None


def test_native_minimize_without_widget_change_callback(window, qapp, monkeypatch):
    from PySide6.QtWidgets import QMainWindow
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    handle = window.windowHandle()
    # Exercise the platform QWindow path even if the QWidget callback is missed.
    monkeypatch.setattr(window, 'changeEvent', lambda event: QMainWindow.changeEvent(window, event))
    handle.showMinimized()
    assert wait_for(qapp, lambda: not window.isVisible(), timeout=1)
    assert not handle.isVisible()
    window.bring_to_front()
    assert window.isVisible() and not window.isMinimized()


def test_native_minimize_when_widget_state_is_delayed(window, qapp, monkeypatch):
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    handle = window.windowHandle()
    monkeypatch.setattr(window, 'isMinimized', lambda: False)
    handle.showMinimized()
    assert wait_for(qapp, lambda: not handle.isVisible(), timeout=1)
    assert not window.isVisible()


def test_repeated_native_minimize_restore_clears_minimized_state(window, qapp):
    from PySide6.QtGui import QWindow
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    for _ in range(4):
        handle = window.windowHandle()
        handle.showMinimized()
        assert wait_for(qapp, lambda: not window.isVisible())
        assert not handle.isVisible() and handle.visibility() == QWindow.Hidden
        assert not (window.windowState() & Qt.WindowMinimized)
        window.bring_to_front()
        qapp.processEvents()
        assert window.isVisible() and handle.isVisible()
        assert not window.isMinimized()


def test_native_restore_cancels_pending_hide(window, qapp):
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    handle = window.windowHandle()
    handle.showMinimized()
    handle.showNormal()
    qapp.processEvents()
    assert window.isVisible() and handle.isVisible()
    assert not window._tray_minimize_timer.isActive()


def test_native_minimize_respects_disabled_background(window, qapp):
    window.settings.run_in_background = False
    window.apply_settings()
    window.show()
    qapp.processEvents()
    handle = window.windowHandle()
    handle.showMinimized()
    qapp.processEvents()
    assert window.isVisible() and handle.isVisible()
