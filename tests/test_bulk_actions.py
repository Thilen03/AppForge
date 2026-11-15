"""Multi-selection and real bulk commands, using isolated files and desktop entries."""
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox, QPushButton

from appforge.core.bulk import BulkActions, UpdatePreferences
from appforge.core.database import Database
from appforge.core.desktop import DesktopError, MENU_CATEGORY_KEY
from appforge.core.library import LibraryError
from appforge.core.models import UpdateStatus
from appforge.core.organize import category_of
from appforge.core.update_policy import PAUSED_KEY, SKIPPED_KEY
from appforge.ui.bulk_dialog import BulkUpdateDialog
from appforge.ui.main_window import MainWindow
from appforge.ui.popups import RoundedComboBox
from test_gui import qapp, wait_for  # noqa: F401
from test_tray import add


@pytest.fixture
def setup(qapp, service, tmp_path):
    entries = [add(service, tmp_path, name) for name in ("Alpha", "Beta", "Gamma")]
    win = MainWindow(service)
    win.show()
    qapp.processEvents()
    yield win, entries
    if win._bulk_run:
        win._bulk_run['progress'].cancel()
        assert wait_for(qapp, lambda: win._bulk_run is None)
    win._quitting = True
    win.close()
    win.check_pool.waitForDone()
    win.install_pool.waitForDone()
    win.deleteLater()
    qapp.processEvents()


def select(win, entries):
    win.select_btn.setChecked(True)
    for entry in entries:
        win._card(entry.id).selection_box.click()


def test_selection_click_refresh_sort_filter_and_done(setup, qapp):
    win, entries = setup
    assert all(c.selection_box.isHidden() for c in win._cards)
    select(win, entries[:2])
    assert win.selection_count.text() == '2 selected'
    assert win.bulk_actions_btn.isEnabled()
    assert win._card(entries[0].id).property('selected')
    win._refresh_card(entries[0].id)
    win.sort_cb.setCurrentIndex(1)
    assert win._selected == {e.id for e in entries[:2]}
    assert win._card(entries[0].id).selection_box.isChecked()
    win.search.setText('Beta')
    assert win._selected == {entries[1].id}
    win.search.clear()
    assert win._selected == {entries[1].id}
    win.select_visible_btn.click()
    assert win._selected == {e.id for e in entries}
    win.clear_selection_btn.click()
    assert not win._selected and not win.bulk_actions_btn.isEnabled()
    win.select_visible_btn.click()
    win.select_btn.click()
    assert not win._selected and win.selection_bar.isHidden()
    assert all(c.selection_box.isHidden() for c in win._cards)


def test_double_click_in_selection_mode_never_launches(setup):
    win, entries = setup
    win.select_btn.click()
    card = win._card(entries[0].id)
    launches = []
    card.launchRequested.connect(launches.append)
    QTest.mouseClick(card, Qt.LeftButton)
    QTest.mouseDClick(card, Qt.LeftButton)
    QTest.mouseRelease(card, Qt.LeftButton)
    assert not launches and entries[0].id in win._selected


@pytest.mark.parametrize('target', ['background', 'cardName', 'cardMeta', 'iconTile', 'cardPath', 'chip', 'busy'])
def test_click_card_contents_toggles_selection(setup, target):
    win, entries = setup
    win.select_btn.click()
    card = win._card(entries[0].id)
    if target == 'background':
        widget, position = card, QPoint(card.width() - 8, card.height() - 8)
    elif target == 'busy':
        card.set_busy('Downloading…', .5)
        widget = card._busy_bar
        position = widget.rect().center()
    else:
        widget = card.findChild(QLabel, target)
        position = widget.rect().center()
    QTest.mouseClick(widget, Qt.LeftButton, pos=position)
    assert entries[0].id in win._selected
    assert card.selection_box.isChecked() and card.property('selected')
    QTest.mouseClick(widget, Qt.LeftButton, pos=position)
    assert entries[0].id not in win._selected
    assert not card.selection_box.isChecked()


def test_card_buttons_checkbox_and_right_click_are_independent(setup, qapp):
    win, entries = setup
    win.select_btn.click()
    card = win._card(entries[0].id)
    launches, edits, favorites = [], [], []
    # Observe the buttons without launching/editing a real application.
    card.launchRequested.disconnect()
    card.editRequested.disconnect()
    card.favoriteRequested.disconnect()
    card.launchRequested.connect(launches.append)
    card.editRequested.connect(edits.append)
    card.favoriteRequested.connect(lambda *args: favorites.append(args))
    QTest.mouseClick(card._primary, Qt.LeftButton)
    card._reveal(True)
    QTest.mouseClick(next(b for b in card.findChildren(QPushButton) if b.text() == 'Edit'), Qt.LeftButton)
    QTest.mouseClick(card.favorite_star, Qt.LeftButton)
    assert launches == edits == [entries[0].id]
    assert favorites == [(entries[0].id, True)]
    assert not win._selected
    card._primary.setEnabled(False)
    QTest.mouseClick(card._primary, Qt.LeftButton)
    QTest.mouseClick(card, Qt.RightButton)
    assert not win._selected
    QTest.mouseClick(card.selection_box, Qt.LeftButton)
    assert win._selected == {entries[0].id}
    QTest.mouseClick(card.selection_box, Qt.LeftButton)
    assert not win._selected


def test_card_click_outside_selection_mode_keeps_normal_launch_behavior(setup):
    win, entries = setup
    card = win._card(entries[0].id)
    launches = []
    card.launchRequested.disconnect()
    card.launchRequested.connect(launches.append)
    QTest.mouseClick(card, Qt.LeftButton)
    assert not win._selected and not launches
    QTest.mouseDClick(card, Qt.LeftButton)
    assert launches == [entries[0].id]


def test_releasing_outside_card_does_not_select(setup):
    win, entries = setup
    win.select_btn.click()
    card = win._card(entries[0].id)
    QTest.mousePress(card, Qt.LeftButton)
    QTest.mouseRelease(card, Qt.LeftButton, pos=QPoint(-5, -5))
    assert not win._selected


def test_action_menu_dispatches_each_command(setup, monkeypatch):
    win, entries = setup
    select(win, entries[:2])
    actions = []
    monkeypatch.setattr(win, 'bulk_action', actions.append)
    for action in win.bulk_actions_btn.menu().actions():
        action.trigger()
    assert actions == ['category', 'updates', 'shortcuts', 'remove']


def test_removing_last_entries_exits_selection_mode(setup, service, qapp):
    win, entries = setup
    select(win, entries)
    win._start_bulk([e.id for e in entries], 'remove')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert not win.select_btn.isChecked() and win.selection_bar.isHidden()
    assert not service.list_applications()


def test_bulk_category_updates_library_menu_and_legacy(service, tmp_path):
    entry = add(service, tmp_path)
    service.update_application(entry.id, category='Old custom category')
    service.set_desktop_integration(entry.id, True)
    helper = BulkActions(service)
    helper.apply(entry.id, 'category', 'Game')
    saved = service.get(entry.id)
    assert saved.metadata[MENU_CATEGORY_KEY] == 'Game'
    assert 'category' not in saved.metadata and category_of(saved) == 'Games'
    assert 'Categories=Game;' in service.desktop.entry_path(entry.id).read_text()
    helper.apply(entry.id, 'category', None)
    saved = service.get(entry.id)
    assert MENU_CATEGORY_KEY not in saved.metadata and 'category' not in saved.metadata


def cached_entry(service, tmp_path):
    entry = add(service, tmp_path)
    entry.github_repo = 'https://github.com/example/app'
    entry.latest_version = '2'
    entry.update_status = UpdateStatus.UPDATE_AVAILABLE
    entry.metadata.update({'include_prereleases': True, 'asset_pattern': '*nightly*',
                           'update': {'tag': 'v2', 'asset': {'url': 'https://example.org/app'}},
                           PAUSED_KEY: True, SKIPPED_KEY: {'source': entry.github_repo, 'tag': 'v2'},
                           'launch_args': ['--test'], 'other': 'preserved'})
    service.db.update(entry)
    return entry


def test_update_preferences_preserve_unspecified_and_invalidate_targets(service, tmp_path):
    entry = cached_entry(service, tmp_path)
    helper = BulkActions(service)
    helper.apply(entry.id, 'updates', UpdatePreferences())
    assert service.get(entry.id).metadata == entry.metadata
    helper.apply(entry.id, 'updates', UpdatePreferences(include_prereleases=False))
    saved = service.get(entry.id)
    assert 'include_prereleases' not in saved.metadata
    assert saved.metadata['asset_pattern'] == '*nightly*'
    assert saved.metadata[PAUSED_KEY] and saved.metadata[SKIPPED_KEY]
    assert saved.update_status is UpdateStatus.UNAVAILABLE
    assert saved.latest_version is None and 'update' not in saved.metadata
    assert saved.metadata['launch_args'] == ['--test'] and saved.github_repo == entry.github_repo
    helper.apply(entry.id, 'updates', UpdatePreferences(paused=False, asset_pattern='', clear_skipped=True))
    saved = service.get(entry.id)
    assert PAUSED_KEY not in saved.metadata and SKIPPED_KEY not in saved.metadata
    assert 'asset_pattern' not in saved.metadata
    reopened = Database(service.db.path)
    try:
        assert reopened.get(entry.id).metadata == saved.metadata
    finally:
        reopened.close()


def test_pause_alone_retains_cached_result(service, tmp_path):
    entry = cached_entry(service, tmp_path)
    BulkActions(service).apply(entry.id, 'updates', UpdatePreferences(paused=False))
    saved = service.get(entry.id)
    assert 'updates_paused' not in saved.metadata
    assert saved.metadata['update'] == entry.metadata['update']
    assert saved.update_status is UpdateStatus.UPDATE_AVAILABLE


def test_shortcut_validation_failures_and_library_only_removal(service, tmp_path, monkeypatch):
    entry = add(service, tmp_path)
    helper = BulkActions(service)
    original = Path(entry.path).read_bytes()
    backup = tmp_path / 'backup'
    backup.write_bytes(b'backup')
    icon = service.icons_dir / f'{entry.id}.png'
    icon.write_bytes(b'icon')
    entry.icon_path = str(icon)
    entry.backup_info = {'backups': [{'path': str(backup)}]}
    service.db.update(entry)
    helper.apply(entry.id, 'shortcuts')
    assert service.desktop.exists(entry.id)
    helper.apply(entry.id, 'shortcuts')  # repeat creation is safe
    Path(entry.path).chmod(0o644)
    with pytest.raises(LibraryError, match='executable'):
        helper.apply(entry.id, 'shortcuts')
    Path(entry.path).chmod(0o755)
    def fail(*args):
        raise DesktopError('Permission denied')
    with monkeypatch.context() as patch:
        patch.setattr(service.desktop, 'write_entry', fail)
        with pytest.raises(LibraryError, match='Permission denied'):
            helper.apply(entry.id, 'shortcuts')
    helper.apply(entry.id, 'remove')
    assert service.get(entry.id) is None and not service.desktop.exists(entry.id)
    assert not icon.exists() and backup.read_bytes() == b'backup'
    assert Path(entry.path).read_bytes() == original
    with pytest.raises(LibraryError, match='no longer'):
        helper.apply(entry.id, 'remove')


def test_update_dialog_defaults_explicit_false_and_cancel(qapp):
    dialog = BulkUpdateDialog(3)
    assert dialog.preferences() == UpdatePreferences()
    assert not dialog.buttons.button(QDialogButtonBox.Apply).isEnabled()
    dialog.paused.setCurrentIndex(2)
    dialog.prereleases.setCurrentIndex(1)
    dialog.change_pattern.click()
    dialog.clear_skipped.click()
    assert dialog.preferences() == UpdatePreferences(False, False, '', True)
    assert dialog.buttons.button(QDialogButtonBox.Apply).isEnabled()
    dialog.buttons.button(QDialogButtonBox.Cancel).click()
    assert dialog.result() == QDialog.Rejected
    dialog.deleteLater()
    qapp.processEvents()


def test_real_bulk_category_prompt_and_cancel(setup, service, qapp):
    win, entries = setup
    select(win, entries[:2])
    def choose():
        dialog = QApplication.activeModalWidget()
        assert dialog.windowTitle() == 'Change category'
        combo = dialog.findChild(RoundedComboBox)
        combo.setCurrentIndex(combo.findData('Game'))
        dialog.accept()
    QTimer.singleShot(0, choose)
    win.bulk_action('category')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert [category_of(service.get(e.id)) for e in entries] == ['Games', 'Games', 'Other']
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    win.bulk_action('category')
    assert win._bulk_run is None


def test_real_update_prompt_changes_only_selected_and_cancel(setup, service, qapp):
    win, entries = setup
    select(win, entries[:2])
    def choose():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, BulkUpdateDialog)
        dialog.paused.setCurrentIndex(1)
        dialog.prereleases.setCurrentIndex(2)
        dialog.buttons.button(QDialogButtonBox.Apply).click()
    QTimer.singleShot(0, choose)
    win.bulk_action('updates')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    for entry in entries[:2]:
        saved = service.get(entry.id)
        assert saved.metadata[PAUSED_KEY] and saved.metadata['include_prereleases']
    assert not service.get(entries[2].id).metadata.get(PAUSED_KEY)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    win.bulk_action('updates')
    assert win._bulk_run is None


def test_remove_confirmation_snapshot_and_cancel(setup, service, qapp):
    win, entries = setup
    select(win, entries[:2])
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    win.bulk_action('remove')
    assert len(service.list_applications()) == 3
    def confirm():
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        assert box.defaultButton().text() == 'Cancel'
        assert 'Alpha' in box.detailedText() and 'Beta' in box.detailedText()
        # A background refresh/selection change must not retarget confirmation.
        win._clear_selection()
        win._select_app(entries[2].id, True)
        next(b for b in box.buttons() if b.text() == 'Remove').click()
    QTimer.singleShot(0, confirm)
    win.bulk_action('remove')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert [e.id for e in service.list_applications()] == [entries[2].id]
    assert all(Path(e.path).exists() for e in entries)


def test_busy_missing_and_permission_failure_report_continue(setup, service, qapp, monkeypatch):
    win, entries = setup
    reports = []
    def report(box):
        reports.append((box.text(), box.detailedText()))
        return 0
    monkeypatch.setattr(QMessageBox, 'exec', report)
    original = service.set_desktop_integration
    def create(app_id, enabled):
        if app_id == entries[1].id:
            raise LibraryError('Permission denied')
        return original(app_id, enabled)
    monkeypatch.setattr(service, 'set_desktop_integration', create)
    select(win, entries)
    win._start_bulk([e.id for e in entries], 'shortcuts')
    # Became busy after the operation was requested, before processing.
    win._busy[entries[0].id] = ('Checking for updates…', None)
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert not service.desktop.exists(entries[0].id)
    assert not service.desktop.exists(entries[1].id)
    assert service.desktop.exists(entries[2].id)
    assert '1 of 3' in reports[0][0]
    assert 'Busy' in reports[0][1] and 'Permission denied' in reports[0][1]
    win._busy.clear()
    service.remove_application(entries[0].id)
    win._start_bulk([entries[0].id, entries[2].id], 'category', 'Game')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert 'no longer' in reports[1][1]
    assert category_of(service.get(entries[2].id)) == 'Games'


def test_cancel_between_entries_retains_completed_changes(setup, service, qapp, monkeypatch):
    win, entries = setup
    original = BulkActions.apply
    def apply(helper, app_id, action, value):
        original(helper, app_id, action, value)
        win._bulk_run['progress'].cancel()
    monkeypatch.setattr(BulkActions, 'apply', apply)
    win._start_bulk([e.id for e in entries], 'category', 'Game')
    assert wait_for(qapp, lambda: win._bulk_run is None)
    assert [category_of(service.get(e.id)) for e in entries] == ['Games', 'Other', 'Other']
    assert '2 not processed' in win.statusBar().currentMessage()
