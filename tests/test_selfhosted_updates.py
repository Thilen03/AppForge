"""Self-hosted source persistence and numbered-nightly update regressions."""
import io
import json

import pytest

from appforge.core.formats.appimage import version_from_filename
from appforge.core.formats.base import AppMetadata
from appforge.core.models import UpdateStatus
from appforge.core.updates import checker
from appforge.core.updates.providers import SelfHostedClient
from appforge.core.updates.version import compare
from appforge.ui.dialogs import EditApplicationDialog
from appforge.ui.main_window import MainWindow
from test_gui import qapp, wait_for  # noqa: F401

ROOT = 'https://git.magicbean.dev/MagicBeanDev/Longshot'
TAG = 'nightly-145-543846eb'
ASSET = f'Longshot-{TAG}-x86_64.AppImage'


def provider(seen, *, prerelease=True):
    # Representative Forgejo API response; the live API is unavailable in this environment.
    payload = [{'tag_name': TAG, 'name': f'Longshot {TAG}', 'prerelease': prerelease,
                'html_url': f'{ROOT}/releases/tag/{TAG}', 'assets': [
                    {'name': ASSET, 'browser_download_url': f'{ROOT}/releases/download/{TAG}/{ASSET}', 'size': 1024},
                    {'name': 'SHA256SUMS', 'browser_download_url': f'{ROOT}/releases/download/{TAG}/SHA256SUMS'}]}]
    def opener(req, timeout=None):
        seen.append(req)
        return io.BytesIO(json.dumps(payload).encode())
    return SelfHostedClient('git.magicbean.dev', opener=opener)


@pytest.mark.parametrize('suffix', ['', '/releases', f'/releases/tag/{TAG}'])
def test_edit_saves_selfhosted_source_and_checks_nightly(qapp, service, tmp_path, monkeypatch, suffix):
    path = tmp_path / 'Longshot.AppImage'
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    entry = service.add_application(str(path), name='Longshot',
                                    metadata=AppMetadata(format_id='appimage', name_suggestion='Longshot'))
    edit = EditApplicationDialog(service, entry)
    edit.repo_edit.setText(ROOT + suffix)
    edit.version_edit.setText('nightly-144-a636846b')
    edit.pre_cb.setChecked(True)
    assert edit.save_btn.isEnabled()
    edit._save()
    saved = service.get(entry.id)
    assert saved.github_repo == ROOT
    assert saved.metadata['include_prereleases']
    seen = []
    monkeypatch.setattr(checker, 'client_for', lambda ref, token: provider(seen))
    win = MainWindow(service)
    assert win._card(entry.id)._status_chip()[0] != 'No update source'
    win.check_updates([entry.id])
    assert wait_for(qapp, lambda: entry.id not in win._busy)
    saved = service.get(entry.id)
    assert saved.update_status is UpdateStatus.UPDATE_AVAILABLE
    assert saved.metadata['update']['asset']['name'] == ASSET
    assert seen[0].full_url == 'https://git.magicbean.dev/api/v1/repos/MagicBeanDev/Longshot/releases?limit=30'
    assert not seen[0].has_header('Authorization')
    win._quitting = True
    win.close()
    edit.close()


def check(*, installed='nightly-144-a636846b', include=False, data=None, filename='Longshot.AppImage'):
    return checker.check_for_update(
        repo_url=ROOT + '/releases', installed_version=installed, current_filename=filename,
        app_name='Longshot', include_prereleases=include, client=data or provider([]))


def test_only_prereleases_has_actionable_message_and_release_link():
    result = check()
    assert result.status is UpdateStatus.UNAVAILABLE
    assert 'pre-releases' in result.message and 'Edit' in result.message
    assert result.release_url == f'{ROOT}/releases/tag/{TAG}'
    assert result.prereleases_only
    assert result.asset is None  # never bypass the user's stable-only preference


def test_unknown_installed_version_can_use_numbered_nightly_filename():
    result = check(installed=None, include=True, filename='Longshot-nightly-144-a636846b-x86_64.AppImage')
    assert result.status is UpdateStatus.UPDATE_AVAILABLE


def test_numbered_nightly_filename_and_comparison_ignore_commit_hash():
    assert version_from_filename('Longshot-nightly-144-a636846b-x86_64.AppImage') == 'nightly-144-a636846b'
    assert compare('nightly-145-543846eb', 'nightly-145-fffffff') == 0
    assert compare('nightly-145-543846eb', 'nightly-144-a636846b') == 1
    assert compare('nightly-145-543846eb', 'nightly-146-00000000') == -1
    # Previously stored display versions have no nightly prefix.
    assert compare('145-543846eb', '145-fffffff') == 0
    assert version_from_filename('nightly.AppImage') is None


def test_prerelease_status_keeps_source_and_explains_opt_in(qapp, service, tmp_path):
    from appforge.core.models import AppEntry
    entry = AppEntry(name='Longshot', path=str(tmp_path / 'Longshot.AppImage'), github_repo=ROOT,
                     installed_version='nightly-144-a636846b')
    service.db.add(entry)
    win = MainWindow(service)
    win.updates.apply_check(entry.id, check())
    win.reload()
    assert win._card(entry.id)._status_chip()[0] == 'Pre-releases available'
    assert 'Edit' in win._card(entry.id)._status_chip()[2]
    assert service.get(entry.id).github_repo == ROOT
    win.updates.apply_check(entry.id, check(include=True))
    win.reload()
    assert win._card(entry.id)._status_chip()[0] == 'Update available'
    assert not service.get(entry.id).metadata['update']['prereleases_only']
    win._quitting = True
    win.close()
