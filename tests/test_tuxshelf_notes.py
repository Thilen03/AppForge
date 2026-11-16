"""Offline startup notes, preference transactions and visible update actions."""
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from test_gui import qapp  # noqa: F401
from test_tray import window, add, available  # noqa: F401
from tuxshelf import __version__
from tuxshelf.core.settings import AppSettings
from tuxshelf.ui import theme
from tuxshelf.ui.tuxshelf_notes_dialog import TuxShelfNotesDialog
from tuxshelf.ui.settings_dialog import SettingsDialog


def test_notes_match_public_release():
    root = Path(__file__).resolve().parents[1]
    public = root / f'releases/RELEASE_NOTES_v{__version__}.md'
    bundled = root / 'src/tuxshelf/resources/release_notes.md'
    assert bundled.read_text() == public.read_text()
    assert bundled.read_text().startswith(f'# TuxShelf {__version__}\n')


def test_preference_persistence(service):
    settings = AppSettings(service.db)
    assert not settings.hide_release_notes
    assert settings.last_release_notes_version == ''
    settings.last_release_notes_version = __version__
    settings.hide_release_notes = True
    restored = AppSettings(service.db)
    assert restored.hide_release_notes
    restored.hide_release_notes = False
    assert settings.last_release_notes_version == ''


def test_settings_cancel_and_reenable(qapp, service):
    settings = AppSettings(service.db)
    settings.hide_release_notes = True
    settings.last_release_notes_version = __version__
    dialog = SettingsDialog(settings, False)
    dialog.hide_notes_cb.setChecked(False)
    dialog.reject()
    assert settings.hide_release_notes
    dialog = SettingsDialog(settings, False)
    dialog.hide_notes_cb.setChecked(False)
    dialog._save()
    assert not settings.hide_release_notes
    assert settings.last_release_notes_version == ''


def test_once_per_version_and_hidden_startup(qapp, window, monkeypatch):
    # The real startup uses the same showEvent path; avoid starting network jobs.
    window.settings.self_launcher_prompted = True
    window._live = True
    window._show_tuxshelf_notes()
    assert window._tuxshelf_notes is None
    window.show()
    qapp.processEvents()
    first = window._tuxshelf_notes
    assert first.isVisible()
    assert __version__ in first.browser.toPlainText()
    first.close()
    window.hide()
    window.show()
    qapp.processEvents()
    assert window._tuxshelf_notes is first and not first.isVisible()
    monkeypatch.setattr('tuxshelf.ui.main_window.__version__', '99.0.0')
    window._show_tuxshelf_notes()
    assert window._tuxshelf_notes is not first
    assert window.settings.last_release_notes_version == '99.0.0'


def test_suppress_future_versions_and_replay(qapp, window, monkeypatch):
    window.show()
    window._show_tuxshelf_notes()
    dialog = window._tuxshelf_notes
    dialog.hide_notes_cb.click()
    assert window.settings.hide_release_notes
    dialog.close()
    monkeypatch.setattr('tuxshelf.ui.main_window.__version__', '99.0.0')
    window._show_tuxshelf_notes()
    assert window._tuxshelf_notes is dialog
    window.settings.hide_release_notes = False
    window._show_tuxshelf_notes()
    assert window._tuxshelf_notes is not dialog
    assert window._tuxshelf_notes.isVisible()


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_update_primary_and_notes_layout(qapp, service, tmp_path, mode):
    from tuxshelf.core.library import FileState
    from tuxshelf.ui.app_card import AppCard
    theme.apply_theme(qapp, mode)
    entry = add(service, tmp_path)
    available(service, entry)
    card = AppCard(service.get(entry.id), FileState.OK)
    card.show()
    dialog = TuxShelfNotesDialog(AppSettings(service.db))
    dialog.show()
    qapp.processEvents()
    assert card._update_btn.objectName() == card._primary.objectName() == 'primary'
    assert card._update_btn.geometry().right() < card._actions.x()
    assert dialog.browser.height() > 300
    # Compare interior pixels away from text, borders and the launch split edge.
    assert card._update_btn.grab().toImage().pixelColor(8, 8) == QColor(theme.tokens().accent)
    assert dialog.hide_notes_cb.geometry().bottom() < dialog.height()
    dialog.grab().save(f'/tmp/tuxshelf-notes-{mode}.png')
    card.grab().save(f'/tmp/tuxshelf-card-{mode}.png')
    card.close()
    dialog.close()
