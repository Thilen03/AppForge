"""Pre-release opt-in through the card menu and the release asset picker."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from appforge.core.database import Database
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.update_policy import updates_paused
from appforge.core.updates.checker import check_for_update
from appforge.core.updates.github import Asset, Release
from appforge.core.updates.service import can_update
from appforge.ui.main_window import MainWindow
from appforge.ui.popups import RoundedMenu
from test_gui import qapp, wait_for  # noqa: F401


@pytest.fixture
def setup(qapp, service, tmp_path):
    path = tmp_path / 'App.AppImage'
    path.write_bytes(b'installed')
    path.chmod(0o755)
    entry = AppEntry(name='App', path=str(path), installed_version='nightly-144-aaaaaaa',
                     github_repo='https://github.com/o/r')
    service.db.add(entry)
    nightly = Release('nightly-145-bbbbbbb', prerelease=True,
                      assets=[Asset('App-nightly-145-bbbbbbb-x86_64.AppImage', 'https://x/nightly')])
    client = SimpleNamespace(releases=lambda *a: [nightly])
    win = MainWindow(service, github_client=client)
    outcome = check_for_update(repo_url=entry.github_repo, installed_version=entry.installed_version,
                               current_filename=path.name, app_name=entry.name, client=client)
    win.updates.apply_check(entry.id, outcome)
    win.reload()
    yield win, entry, nightly
    win.check_pool.waitForDone()
    win._quitting = True
    win.close()
    win.deleteLater()
    qapp.processEvents()


def menu_action(win, app_id, text):
    return next(a for a in win._card(app_id).findChild(RoundedMenu).actions() if a.text() == text)


def wait_checked(qapp, win, app_id):
    assert wait_for(qapp, lambda: app_id not in win._busy)


def test_menu_opt_in_persists_and_exposes_update_button(setup, qapp, service):
    win, entry, _ = setup
    assert win._card(entry.id)._status_chip()[0] == 'Pre-releases available'
    assert win._card(entry.id)._update_btn is None
    menu_action(win, entry.id, 'Enable pre-releases').trigger()
    wait_checked(qapp, win, entry.id)
    saved = service.get(entry.id)
    assert saved.metadata['include_prereleases']
    assert saved.update_status is UpdateStatus.UPDATE_AVAILABLE and can_update(saved)
    assert win._card(entry.id)._update_btn.text() == 'Update'
    assert menu_action(win, entry.id, 'Use stable releases only').isEnabled()
    other = Database(service.db.path)
    try:
        assert other.get(entry.id).metadata['include_prereleases']
    finally:
        other.close()


def test_asset_choice_offers_opt_in_and_selects_nightly(setup, qapp, service, monkeypatch):
    win, entry, nightly = setup
    questions = []
    monkeypatch.setattr(win, '_pick_asset', lambda *a: nightly.assets[0].name)
    def accept(*args):
        questions.append(args[2])
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, 'question', accept)
    win.choose_asset(entry.id)
    wait_checked(qapp, win, entry.id)
    saved = service.get(entry.id)
    assert questions and 'pre-release/nightly' in questions[0]
    assert saved.metadata['include_prereleases']
    assert saved.metadata['asset_pattern'] == 'App-*-x86_64.AppImage'
    assert saved.metadata['update']['asset']['url'] == 'https://x/nightly'
    assert can_update(saved) and win._card(entry.id)._update_btn is not None


@pytest.mark.parametrize('pick', [None, 'decline'])
def test_cancel_or_decline_changes_nothing(setup, service, monkeypatch, pick):
    win, entry, nightly = setup
    before = service.get(entry.id)
    monkeypatch.setattr(win, '_pick_asset', lambda *a: nightly.assets[0].name if pick else None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.No)
    win.choose_asset(entry.id)
    after = service.get(entry.id)
    assert after.metadata == before.metadata
    assert after.update_status is UpdateStatus.UNAVAILABLE
    assert entry.id not in win._busy


def test_return_to_stable_invalidates_cached_nightly(setup, qapp, service, monkeypatch):
    win, entry, _ = setup
    win.set_prereleases_enabled(entry.id, True)
    wait_checked(qapp, win, entry.id)
    assert can_update(service.get(entry.id))
    jobs = []
    monkeypatch.setattr(win.check_pool, 'start', jobs.append)
    menu_action(win, entry.id, 'Use stable releases only').trigger()
    assert not service.get(entry.id).metadata.get('include_prereleases')
    assert not can_update(service.get(entry.id))
    assert jobs[0].kwargs['include_prereleases'] is False
    # Run the queued worker synchronously so teardown has no abandoned busy job.
    jobs[0].run()
    assert service.get(entry.id).metadata['update']['prereleases_only']


@pytest.mark.parametrize('method', ['menu', 'picker'])
def test_busy_app_cannot_change_channel_or_asset(setup, service, monkeypatch, method):
    win, entry, _ = setup
    win._set_busy(entry.id, 'Checking for updates…', None)
    assert not menu_action(win, entry.id, 'Enable pre-releases').isEnabled()
    assert not menu_action(win, entry.id, 'Choose release asset…').isEnabled()
    monkeypatch.setattr(win, '_pick_asset', lambda *a: pytest.fail('busy picker'))
    if method == 'menu':
        win.set_prereleases_enabled(entry.id, True)
    else:
        win.choose_asset(entry.id)
    assert not service.get(entry.id).metadata.get('include_prereleases')
    win._set_busy(entry.id, None)


def test_channel_change_preserves_pause_and_other_apps(setup, service, tmp_path):
    win, entry, _ = setup
    other = AppEntry(name='Other', path=str(tmp_path / 'Other'), github_repo='https://github.com/x/y')
    service.db.add(other)
    win.updates.set_paused(entry.id, True)
    win.set_prereleases_enabled(entry.id, True)
    assert updates_paused(service.get(entry.id))
    assert service.get(entry.id).metadata['include_prereleases']
    assert not service.get(other.id).metadata.get('include_prereleases')
    assert entry.id not in win._busy
    assert 'Resume updates' in win.statusBar().currentMessage()


def test_already_opted_in_does_not_ask_again(setup, qapp, monkeypatch):
    win, entry, nightly = setup
    win.set_prereleases_enabled(entry.id, True)
    wait_checked(qapp, win, entry.id)
    monkeypatch.setattr(win, '_pick_asset', lambda *a: nightly.assets[0].name)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: pytest.fail('redundant opt-in'))
    win.choose_asset(entry.id)
    wait_checked(qapp, win, entry.id)


def test_stable_asset_choice_does_not_enable_prereleases(setup, service, qapp, monkeypatch):
    win, entry, _ = setup
    stable = Release('v999', assets=[Asset('App-999-x86_64.AppImage', 'https://x/stable')])
    win._client = SimpleNamespace(releases=lambda *a: [stable])
    win.check_updates([entry.id])
    wait_checked(qapp, win, entry.id)
    monkeypatch.setattr(win, '_pick_asset', lambda *a: stable.assets[0].name)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: pytest.fail('stable opt-in'))
    win.choose_asset(entry.id)
    wait_checked(qapp, win, entry.id)
    assert not service.get(entry.id).metadata.get('include_prereleases')
    assert can_update(service.get(entry.id))
