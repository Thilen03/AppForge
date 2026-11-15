"""Per-badge preferences, dialog transactions and live card appearance."""
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel

from test_gui import qapp  # noqa: F401
from test_tray import add, window  # noqa: F401
from appforge.core.database import Database
from appforge.core.library import FileState
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.settings import CARD_BADGES, AppSettings
from appforge.ui import theme
from appforge.ui.app_card import AppCard
from appforge.ui.settings_dialog import SettingsDialog
from appforge.ui.main_window import MainWindow


def test_settings_validation_and_reopen(service):
    settings = AppSettings(service.db)
    assert settings.card_badge_colors == {}
    for raw in ('garbage', '[]', 'null', '42', '{"failed": null}'):
        service.db.set_setting('card_badge_colors', raw)
        assert settings.card_badge_colors == {}
    service.db.set_setting('card_badge_colors', json.dumps(
        {'failed': '#aa00bb', 'no_source': 'red', 'unknown': '#FFFFFF'}))
    assert settings.card_badge_colors == {'failed': '#AA00BB'}
    with pytest.raises(ValueError):
        settings.card_badge_colors = {'failed': '#fff; color: red'}
    with pytest.raises(ValueError):
        settings.card_badge_colors = {'unknown': '#FFFFFF'}
    settings.card_badge_colors = {'failed': '#aabbcc', 'no_source': '#123456'}
    other = Database(service.db.path)
    try:
        assert AppSettings(other).card_badge_colors == {'failed': '#AABBCC', 'no_source': '#123456'}
    finally:
        other.close()


def test_dialog_picker_cancel_save_and_resets(qapp, service, monkeypatch):
    settings = AppSettings(service.db)
    dialog = SettingsDialog(settings, False)
    assert set(dialog.badge_buttons) == set(CARD_BADGES)
    monkeypatch.setattr('appforge.ui.settings_dialog.QColorDialog.getColor', lambda *args: QColor())
    dialog.badge_buttons['failed'].click()
    assert dialog.badge_colors == {}
    monkeypatch.setattr('appforge.ui.settings_dialog.QColorDialog.getColor', lambda *args: QColor('#FF00AA'))
    dialog.badge_buttons['failed'].click()
    assert dialog.badge_colors == {'failed': '#FF00AA'}
    assert settings.card_badge_colors == {}
    dialog.reject()
    assert settings.card_badge_colors == {}
    dialog = SettingsDialog(settings, False)
    dialog.badge_buttons['no_source'].click()
    dialog._save()
    assert dialog.result() == SettingsDialog.DialogCode.Accepted
    assert settings.card_badge_colors == {'no_source': '#FF00AA'}
    dialog = SettingsDialog(settings, False)
    dialog.badge_resets['no_source'].click()
    assert dialog.badge_colors == {}
    dialog.reject()
    assert settings.card_badge_colors == {'no_source': '#FF00AA'}
    dialog = SettingsDialog(settings, False)
    dialog._reset_badge_colors()
    dialog._save()
    assert settings.card_badge_colors == {}


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_all_badges_independent_and_defaults_unchanged(qapp, mode):
    t = theme.LIGHT if mode == 'light' else theme.DARK
    for key, (_, kind) in CARD_BADGES.items():
        defaults = theme.badge_colors(t, key, {})
        assert theme.badge_colors(t, key, {'failed': '#112233'}) == (
            (f'rgba(17, 34, 51, {40 if t.dark else 30})', '#112233', '#112233')
            if key == 'failed' else defaults)
        # Compare rendered default to the existing shared-kind CSS.
        old = QLabel('Default', objectName='chip')
        old.setProperty('kind', kind)
        new = QLabel('New', objectName='chip')
        new.setProperty('badgeKey', key)
        theme.apply_theme(qapp, mode)
        old.ensurePolished()
        new.ensurePolished()
        for role in (QPalette.Window, QPalette.WindowText):
            assert new.palette().color(role) == old.palette().color(role)
        old.deleteLater()
        new.deleteLater()
    assert theme.badge_colors(t, 'failed', {'failed': '#FFFFFF'})[1:] == ('#FFFFFF', '#FFFFFF')
    theme.apply_theme(qapp)


@pytest.mark.parametrize('status', list(UpdateStatus))
def test_card_status_keys(qapp, status):
    entry = AppEntry('Tool', '/tmp/tool', github_repo='a/b', update_status=status)
    card = AppCard(entry, FileState.OK)
    chips = card.findChildren(QLabel, 'chip')
    assert [c.property('badgeKey') for c in chips] == ['appimage', status.value]
    card.deleteLater()


@pytest.mark.parametrize('key,state,metadata,repo', [
    ('no_source', FileState.OK, {}, None),
    ('prereleases', FileState.OK, {'update': {'prereleases_only': True}}, 'a/b'),
    ('paused', FileState.OK, {'updates_paused': True}, None),
    ('skipped', FileState.OK, {'skipped_update': {'source': 'a/b', 'tag': 'v2'},
                             'update': {'tag': 'v2'}}, 'a/b'),
    ('missing', FileState.MISSING, {}, 'a/b'),
    ('missing', FileState.NOT_A_FILE, {}, 'a/b'),
    ('not_executable', FileState.NOT_EXECUTABLE, {}, 'a/b'),
])
def test_special_card_keys(qapp, key, state, metadata, repo):
    entry = AppEntry('Tool', '/tmp/tool', format='executable', github_repo=repo, metadata=metadata)
    card = AppCard(entry, state)
    assert [c.property('badgeKey') for c in card.findChildren(QLabel, 'chip')] == ['executable', key]
    card.deleteLater()


def test_save_applies_without_recreating_card_and_survives_theme(window, qapp, service, tmp_path, monkeypatch):
    entry = add(service, tmp_path)
    window.reload()
    card = window._card(entry.id)
    def save(dialog):
        dialog.badge_colors = {'no_source': '#102030'}
        dialog._save()
        return SettingsDialog.DialogCode.Accepted
    monkeypatch.setattr(SettingsDialog, 'exec', save)
    window.open_settings()
    qapp.processEvents()
    assert window._card(entry.id) is card
    chip = next(c for c in card.findChildren(QLabel, 'chip') if c.property('badgeKey') == 'no_source')
    for _ in range(2):
        background = QColor('#102030')
        background.setAlpha(40 if theme.tokens().dark else 30)
        assert chip.palette().color(QPalette.Window) == background
        assert chip.palette().color(QPalette.WindowText) == QColor('#102030')
        window.toggle_theme()
        qapp.processEvents()


def test_custom_colors_restored_on_window_startup(qapp, service):
    settings = AppSettings(service.db)
    settings.card_badge_colors = {'up_to_date': '#AB1290'}
    win = MainWindow(service)
    assert '#AB1290' in qapp.styleSheet()
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_color_section_is_last_collapsed_and_keyboard_expandable(qapp, service):
    dialog = SettingsDialog(AppSettings(service.db), False)
    dialog.show()
    qapp.processEvents()
    layout = dialog.badge_toggle.parentWidget().layout()
    assert layout.indexOf(dialog.badge_section) == layout.count() - 2
    assert layout.indexOf(dialog.badge_toggle) > layout.indexOf(dialog.token_edit)
    assert dialog.badge_section.isHidden()
    assert not dialog.badge_toggle.isChecked()
    assert dialog.badge_toggle.arrowType() == Qt.RightArrow
    dialog.badge_toggle.setFocus()
    QTest.keyClick(dialog.badge_toggle, Qt.Key_Space)
    qapp.processEvents()
    assert dialog.badge_section.isVisible()
    assert dialog.badge_toggle.arrowType() == Qt.DownArrow
    dialog.badge_colors['failed'] = '#112233'
    dialog.badge_toggle.click()
    assert dialog.badge_section.isHidden()
    dialog.badge_toggle.click()
    assert dialog.badge_colors['failed'] == '#112233'
    dialog.reject()
    reopened = SettingsDialog(AppSettings(service.db), False)
    assert reopened.badge_section.isHidden()
    assert not reopened.badge_toggle.isChecked()
    reopened.reject()
