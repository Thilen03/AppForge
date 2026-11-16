"""Persistent update policy and its card, tray, check and installation entry points."""
import pytest

from test_gui import qapp  # noqa: F401
from test_tray import add, available, window  # noqa: F401
from tuxshelf.core.database import Database
from tuxshelf.core.models import UpdateStatus
from tuxshelf.core.organize import Filter, UPDATES, matches
from tuxshelf.core.update_policy import updates_paused, version_skipped
from tuxshelf.core.updates.checker import CheckOutcome
from tuxshelf.core.updates.service import UpdateService, can_update
from tuxshelf.ui.popups import RoundedMenu


def action(window, app_id, text):
    return next(a for a in window._card(app_id).findChild(RoundedMenu).actions() if a.text() == text)


def outcome(tag='v2', version='2'):
    return CheckOutcome(UpdateStatus.UPDATE_AVAILABLE, latest_version=version, tag=tag,
                        asset={'name': 'tool', 'url': 'https://example.org/tool'})


def test_pause_persists_and_blocks_results_notifications_and_installs(service, tmp_path):
    entry = add(service, tmp_path)
    available(service, entry)
    updates = UpdateService(service)
    paused = updates.set_paused(entry.id, True)
    assert updates_paused(paused) and not can_update(paused)
    assert not matches(paused, Filter(status=UPDATES))
    assert not updates.pending_notifications()
    updates.apply_check(entry.id, outcome('v3', '3'))
    assert service.get(entry.id).latest_version == '2'
    other = Database(service.db.path)
    try:
        assert updates_paused(other.get(entry.id))
    finally:
        other.close()
    assert can_update(updates.set_paused(entry.id, False))


def test_skip_exact_release_survives_checks_and_newer_release_is_offered(service, tmp_path):
    entry = add(service, tmp_path)
    available(service, entry)
    updates = UpdateService(service)
    skipped = updates.skip_version(entry.id)
    assert version_skipped(skipped) and not can_update(skipped)
    assert not updates.pending_notifications()
    reopened = Database(service.db.path)
    try:
        assert version_skipped(reopened.get(entry.id))
    finally:
        reopened.close()
    updates.apply_check(entry.id, outcome())
    assert version_skipped(service.get(entry.id))
    updates.apply_check(entry.id, CheckOutcome(UpdateStatus.FAILED, message='offline'))
    assert version_skipped(service.get(entry.id))
    updates.apply_check(entry.id, outcome('v3', '3'))
    current = service.get(entry.id)
    assert not version_skipped(current) and can_update(current)
    assert updates.should_notify(current)
    # A different repository reusing the same tag must not inherit the skip.
    current.github_repo = 'https://github.com/other/repo'
    current.metadata['update']['tag'] = 'v2'
    service.db.update(current)
    assert not version_skipped(service.get(entry.id))


def test_skip_clear_and_pause_resume_are_independent(service, tmp_path):
    entry = add(service, tmp_path)
    available(service, entry)
    updates = UpdateService(service)
    updates.skip_version(entry.id)
    updates.set_paused(entry.id, True)
    current = updates.set_paused(entry.id, False)
    assert version_skipped(current) and not can_update(current)
    assert can_update(updates.clear_skipped_version(entry.id))
    assert updates.skip_version('missing') is None
    assert updates.set_paused('missing', True) is None
    assert updates.clear_skipped_version('missing') is None


def test_card_pause_resume_and_skip_menu_sync(window, service, tmp_path, monkeypatch):
    entry = add(service, tmp_path)
    available(service, entry)
    window.reload()
    action(window, entry.id, 'Pause updates').trigger()
    card = window._card(entry.id)
    assert card._status_chip()[:2] == ('Update paused', 'paused')
    assert card._update_btn is None
    assert not action(window, entry.id, 'Check for updates').isEnabled()
    assert not window.update_all_btn.isEnabled()
    assert not window.tray.update_action.isEnabled()
    assert '0 application updates' in window.tray.status_action.text()
    checks = []
    monkeypatch.setattr(window, 'check_updates', lambda ids: checks.extend(ids))
    action(window, entry.id, 'Resume updates').trigger()
    assert checks == [entry.id]
    assert window._card(entry.id)._status_chip()[0] == 'Update available'
    action(window, entry.id, 'Skip this version').trigger()
    assert window._card(entry.id)._status_chip()[0] == 'Version skipped'
    assert action(window, entry.id, 'Check for updates').isEnabled()
    assert not window.update_all_btn.isEnabled()
    action(window, entry.id, 'Clear skipped version').trigger()
    assert window._card(entry.id)._update_btn is not None
    assert window.update_all_btn.isEnabled()


@pytest.mark.parametrize('user_initiated', [False, True])
def test_checks_exclude_paused_but_include_skipped(window, service, tmp_path, monkeypatch, user_initiated):
    paused, skipped = [add(service, tmp_path, name) for name in ['Paused', 'Skipped']]
    for e in (paused, skipped):
        available(service, e)
    window.updates.set_paused(paused.id, True)
    window.updates.skip_version(skipped.id)
    window.reload()
    jobs = []
    monkeypatch.setattr(window.check_pool, 'start', jobs.append)
    window.check_updates(user_initiated=user_initiated)
    assert len(jobs) == 1 and jobs[0].app_id == skipped.id
    window._on_check_done(skipped.id, outcome())
    assert version_skipped(service.get(skipped.id))


@pytest.mark.parametrize('control', ['pause', 'skip'])
def test_direct_install_and_update_all_cannot_bypass_controls(window, service, tmp_path, monkeypatch, control):
    entry = add(service, tmp_path)
    available(service, entry)
    if control == 'pause':
        window.updates.set_paused(entry.id, True)
    else:
        window.updates.skip_version(entry.id)
    window.reload()
    jobs = []
    monkeypatch.setattr(window.install_pool, 'start', jobs.append)
    window.start_update(entry.id)
    window.update_all()
    assert jobs == [] and window._batch is None


def test_controls_disabled_while_busy(window, service, tmp_path):
    entry = add(service, tmp_path)
    available(service, entry)
    window.reload()
    window._set_busy(entry.id, 'Waiting…', None)
    assert not action(window, entry.id, 'Pause updates').isEnabled()
    assert not action(window, entry.id, 'Skip this version').isEnabled()
    window.set_updates_paused(entry.id, True)
    window.skip_update_version(entry.id)
    assert not updates_paused(service.get(entry.id))
    assert not version_skipped(service.get(entry.id))
    window._set_busy(entry.id, None)


def test_pause_without_source_and_missing_file_still_allows_repair(qapp):
    from tuxshelf.core.library import FileState
    from tuxshelf.core.models import AppEntry
    from tuxshelf.ui.app_card import AppCard
    entry = AppEntry(name='Missing', path='/missing', metadata={'updates_paused': True})
    card = AppCard(entry, FileState.MISSING)
    assert card._status_chip()[:2] == ('Update paused', 'paused')
    assert card._primary.text() == 'Locate file…'
    assert any(a.text() == 'Resume updates' for a in card.findChild(RoundedMenu).actions())
    card.close()


def test_details_reflect_pause_and_skip_without_blocking_launch(window, service, tmp_path, qapp):
    from test_gui import wait_for
    entry = add(service, tmp_path)
    available(service, entry)
    window.reload()
    window.show_details(entry.id)
    details = window._details[entry.id]
    assert wait_for(qapp, lambda: details.fields['File status'].text() == 'Ready')
    window.set_updates_paused(entry.id, True)
    assert details.fields['Update status'].text() == 'Update paused'
    assert not details.buttons['check'].isEnabled()
    assert not details.buttons['update'].isEnabled()
    assert wait_for(qapp, lambda: details.buttons['launch'].isEnabled())
    window.updates.set_paused(entry.id, False)
    window.skip_update_version(entry.id)
    assert details.fields['Update status'].text() == 'Version skipped'
    assert details.buttons['check'].isEnabled()
    assert not details.buttons['update'].isEnabled()
    window.clear_skipped_version(entry.id)
    assert wait_for(qapp, lambda: details.buttons['update'].isEnabled())
