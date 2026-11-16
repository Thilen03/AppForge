"""Header appearance switching, persistence and system-theme precedence."""
import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from test_gui import qapp  # noqa: F401
from test_tray import add, window  # noqa: F401
from tuxshelf.core.database import Database
from tuxshelf.core.settings import AppSettings
from tuxshelf.ui import theme
from tuxshelf.ui.main_window import MainWindow


def test_setting_default_validation_and_reopen(service):
    settings = AppSettings(service.db)
    assert settings.theme_mode == 'system'
    service.db.set_setting('theme_mode', 'broken')
    assert settings.theme_mode == 'system'
    with pytest.raises(ValueError):
        settings.theme_mode = 'unknown'
    settings.theme_mode = 'dark'
    other = Database(service.db.path)
    try:
        assert AppSettings(other).theme_mode == 'dark'
    finally:
        other.close()


def test_toggle_position_icons_and_live_state(window, service, tmp_path, qapp):
    entry = add(service, tmp_path)
    window.reload()
    window.search.setText('Tool')
    window._set_busy(entry.id, 'Downloading… 50%', .5)
    window.show()
    qapp.processEvents()
    btn = window.theme_btn
    assert btn.x() > window.settings_btn.x()
    assert btn.size() == window.settings_btn.size()
    card = window._card(entry.id)
    before = theme.tokens().dark
    icon = btn.icon().pixmap(24, 24).toImage()
    QTest.mouseClick(btn, Qt.LeftButton)
    qapp.processEvents()
    assert theme.tokens().dark != before
    mode = 'dark' if theme.tokens().dark else 'light'
    assert window.settings.theme_mode == mode
    assert btn.toolTip() == ('Switch to light mode' if theme.tokens().dark else 'Switch to dark mode')
    assert btn.accessibleName() == btn.toolTip()
    assert icon != btn.icon().pixmap(24, 24).toImage()
    assert window._card(entry.id) is card
    assert window.search.text() == 'Tool'
    assert card._busy_bar.value() == 500
    QTest.mouseClick(btn, Qt.LeftButton)
    assert theme.tokens().dark == before
    window._set_busy(entry.id, None)


def test_saved_mode_restored_and_open_dialog_recolored(qapp, service, monkeypatch):
    settings = AppSettings(service.db)
    settings.theme_mode = 'dark'
    monkeypatch.setattr(theme, 'is_dark', lambda app: False)
    win = MainWindow(service)
    dialog = QDialog(win)
    dialog.show()
    qapp.processEvents()
    assert theme.tokens().dark
    assert dialog.palette().color(QPalette.Window) == QColor(theme.DARK.bg)
    win.theme_btn.click()
    qapp.processEvents()
    assert not theme.tokens().dark
    assert dialog.palette().color(QPalette.Window) == QColor(theme.LIGHT.bg)
    dialog.close()
    win.close()
    restored = MainWindow(service)
    assert restored.settings.theme_mode == 'light'
    assert not theme.tokens().dark
    assert restored.theme_btn.toolTip() == 'Switch to dark mode'
    restored.close()
    restored.deleteLater()
    win.deleteLater()
    qapp.processEvents()


def test_explicit_appearance_survives_desktop_changes(qapp, service, monkeypatch):
    settings = AppSettings(service.db)
    for desktop_dark in (False, True):
        monkeypatch.setattr(theme, 'is_dark', lambda app: desktop_dark)
        assert theme.apply_theme(qapp, settings.theme_mode).dark == desktop_dark
        for mode in ('light', 'dark'):
            settings.theme_mode = mode
            assert theme.apply_theme(qapp, settings.theme_mode).dark == (mode == 'dark')
        settings.theme_mode = 'system'
    theme.apply_theme(qapp)
