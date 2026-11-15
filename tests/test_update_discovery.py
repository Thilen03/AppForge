"""Offline regressions for unusual releases and checksum-based discovery."""
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from appforge.core.formats.appimage import version_from_filename
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.updates import checker, installer
from appforge.core.updates.assets import choose_asset
from appforge.core.updates.github import Asset, Release
from appforge.core.updates.service import UpdateService, pattern_from_asset
from appforge.core.updates.version import compare
from appforge.ui.main_window import MainWindow
from test_gui import qapp, wait_for  # noqa: F401


@pytest.mark.parametrize('filename,version', [
    ('App2-1.2.3-x86_64.AppImage', '1.2.3'),
    ('App-2026-11-15-amd64.AppImage', '2026-11-15'),
    ('App_1_2_3_x86_64.AppImage', '1_2_3'),
    ('App-2.0.0-rc.2-x86_64.AppImage', '2.0.0-rc.2'),
    ('App-5.0-1234-x86_64.AppImage', '5.0-1234'),
    ('App-v42-x64.AppImage', '42'),
    ('App-nightly-145-1234567-x86_64.AppImage', 'nightly-145-1234567'),
    ('App2-x86_64.AppImage', None),
])
def test_filename_versions(filename, version):
    assert version_from_filename(filename) == version


@pytest.mark.parametrize('new,old,result', [
    ('App2-v1.3.0', '1.2.9', 1), ('release_2_1_0', '2.0', 1),
    ('2026-11-15', '2026-11-14', 1), ('v2.0-rc.2', '2.0-rc.1', 1),
    ('v2.0', '2.0-beta2', 1), ('5.0-1235', '5.0-1234', 1),
    ('nightly', 'nightly', None), ('abcdef1234567', '1.0', None),
])
def test_unusual_tag_comparison(new, old, result):
    assert compare(new, old) == result


def run_check(releases, *, installed='1.0', filename='App.AppImage', **kwargs):
    return checker.check_for_update(repo_url='o/r', installed_version=installed,
                                    current_filename=filename, app_name='App',
                                    client=SimpleNamespace(releases=lambda *a: releases), **kwargs)


@pytest.mark.parametrize('title,filename', [
    ('App2 version 2.4.0', 'App.AppImage'), ('Latest', 'App-2.4.0-x86_64.AppImage')])
def test_rolling_tag_uses_title_or_asset_version(title, filename):
    result = run_check([Release('continuous', name=title, assets=[Asset(filename, 'https://x/a')])])
    assert result.status is UpdateStatus.UPDATE_AVAILABLE
    assert result.latest_version == '2.4.0'
    assert result.tag == 'continuous'


@pytest.mark.parametrize('arch,filename', [
    ('aarch64', 'App-x86_64.AppImage'), ('arm64', 'App-x86-64.AppImage'),
    ('x86_64', 'App-armv7.AppImage'), ('x86_64', 'App-riscv64.AppImage')])
def test_pattern_cannot_override_wrong_architecture(arch, filename):
    assert choose_asset(Release('2', assets=[Asset(filename, 'https://x/a')]),
                        current_filename='App.AppImage', app_name='App', arch=arch,
                        pattern=filename) is None


def test_pattern_is_strict_and_metadata_cannot_be_an_appimage():
    release = Release('2', assets=[Asset('App-qt.AppImage', 'https://x/a'),
                                  Asset('App.AppImage.tar.gz', 'https://x/b')])
    assert choose_asset(release, current_filename='App.AppImage', app_name='App',
                        pattern='App-gtk.AppImage') is None
    choice = choose_asset(release, current_filename='App.AppImage', app_name='App')
    assert [a.name for a in choice.candidates] == ['App-qt.AppImage']


@pytest.mark.parametrize('algo', ['sha256', 'sha512'])
@pytest.mark.parametrize('same', [True, False])
@pytest.mark.parametrize('installed', [None, 'nightly'])
def test_unknown_versions_compare_published_hash(tmp_path, algo, same, installed):
    target = tmp_path / 'App.AppImage'
    target.write_bytes(b'installed bytes')
    published = target.read_bytes() if same else b'new release bytes'
    asset = Asset('App.AppImage', 'https://x/a', digest=f'{algo}:' + hashlib.new(algo, published).hexdigest())
    result = run_check([Release('continuous', assets=[asset])], installed=installed, installed_path=str(target))
    assert result.status is (UpdateStatus.UP_TO_DATE if same else UpdateStatus.UPDATE_AVAILABLE)
    assert 'checksum' in result.message
    if not same:
        assert 'ordering is unknown' in result.message
    assert target.read_bytes() == b'installed bytes'


def test_rolling_equal_tag_does_not_claim_up_to_date_without_evidence():
    result = run_check([Release('continuous', assets=[Asset('App.AppImage', 'https://x/a')])],
                       installed='continuous')
    assert result.status is UpdateStatus.UNAVAILABLE


def test_numeric_downgrade_never_uses_hash(tmp_path, monkeypatch):
    def unexpected(*args):
        pytest.fail('Comparable versions must not use checksum mismatch as a downgrade')
    monkeypatch.setattr(checker, 'find_expected_checksum', unexpected)
    assert run_check([Release('v1.0', assets=[Asset('App.AppImage', 'https://x/a')])],
                     installed='2.0', installed_path=str(tmp_path / 'missing')).status is UpdateStatus.UP_TO_DATE


def test_ambiguous_asset_requires_choice_before_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(checker, 'find_expected_checksum', lambda *a: pytest.fail('ambiguous checksum'))
    result = run_check([Release('continuous', assets=[Asset('App-a.AppImage', 'https://x/a'),
                                                    Asset('App-b.AppImage', 'https://x/b')])],
                       installed=None, installed_path=str(tmp_path / 'App.AppImage'))
    assert result.status is UpdateStatus.UNAVAILABLE
    assert 'Choose' in result.message


def test_checksum_sidecar_is_used_without_downloading_application(tmp_path, monkeypatch):
    target = tmp_path / 'App.AppImage'
    target.write_bytes(b'installed')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    seen = []
    def fetch(url, **kwargs):
        seen.append(url)
        return f'{digest}  App.AppImage\n'
    monkeypatch.setattr(installer, '_fetch_text', fetch)
    release = Release('continuous', assets=[Asset('App.AppImage', 'https://x/app'),
                                           Asset('SHA256SUMS', 'https://x/sums')])
    assert run_check([release], installed=None, installed_path=str(target)).status is UpdateStatus.UP_TO_DATE
    assert seen == ['https://x/sums']


def test_missing_and_changing_installed_file_are_not_updates(tmp_path, monkeypatch):
    asset = Asset('App.AppImage', 'https://x/a', digest='sha256:' + 'a' * 64)
    target = tmp_path / 'App.AppImage'
    result = run_check([Release('continuous', assets=[asset])], installed=None, installed_path=str(target))
    assert result.status is UpdateStatus.UNAVAILABLE and 'read' in result.message
    target.write_bytes(b'old')
    def changing(path, algo):
        path.write_bytes(b'changed')
        return 'b' * 64
    monkeypatch.setattr(checker, '_hash_file', changing)
    result = run_check([Release('continuous', assets=[asset])], installed=None, installed_path=str(target))
    assert result.status is UpdateStatus.UNAVAILABLE and 'changed' in result.message


def test_invalid_digest_is_not_trusted():
    with pytest.raises(installer.InstallError, match='invalid asset checksum'):
        installer.find_expected_checksum({'name': 'App.AppImage', 'digest': 'sha256:abc'}, [])


def test_manual_choice_rechecks_with_installed_path(qapp, service, tmp_path, monkeypatch):
    path = tmp_path / 'App.AppImage'
    path.write_bytes(b'installed bytes')
    entry = AppEntry(name='App', path=str(path), github_repo='https://github.com/o/r')
    service.db.add(entry)
    asset = Asset('App-gtk.AppImage', 'https://x/a', digest='sha256:' + hashlib.sha256(b'new').hexdigest())
    release = Release('continuous', assets=[asset, Asset('App-qt.AppImage', 'https://x/b')])
    client = SimpleNamespace(releases=lambda *a: [release])
    us = UpdateService(service)
    us.apply_check(entry.id, run_check([release], installed=None))
    win = MainWindow(service, github_client=client)
    monkeypatch.setattr(win, '_pick_asset', lambda *a: asset.name)
    win.choose_asset(entry.id)
    assert wait_for(qapp, lambda: entry.id not in win._busy)
    saved = service.get(entry.id)
    assert saved.update_status is UpdateStatus.UPDATE_AVAILABLE
    assert saved.metadata['update']['asset']['name'] == asset.name
    win._quitting = True
    win.close()


def test_rolling_asset_choice_pattern_tracks_future_versions():
    pattern = pattern_from_asset('App-2.4.0-x86_64.AppImage', 'continuous')
    assert pattern == 'App-*-x86_64.AppImage'
    assert choose_asset(Release('continuous', assets=[Asset('App-2.5.0-x86_64.AppImage', 'https://x/a')]),
                        current_filename='App.AppImage', app_name='App', pattern=pattern) is not None


@pytest.mark.parametrize('corrupt', [False, True])
def test_offline_install_checksums_preserve_original_on_failure(tmp_path, monkeypatch, corrupt):
    target = tmp_path / 'tool'
    target.write_bytes(b'#!/bin/sh\necho old version\n')
    target.chmod(0o755)
    before = target.read_bytes()
    body = b'#!/bin/sh\necho new version\n'
    class Response(io.BytesIO):
        headers = {'Content-Length': str(len(body))}
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: Response(body))
    asset = {'name': 'tool-linux-amd64', 'url': 'https://x/a',
             'digest': 'sha256:' + ('0' * 64 if corrupt else hashlib.sha256(body).hexdigest())}
    if corrupt:
        with pytest.raises(installer.InstallError, match='Checksum mismatch'):
            installer.install_update(target, asset, [], old_version='1', format_id='executable')
        assert target.read_bytes() == before
        assert not installer.backup_dir_for(target).exists()
    else:
        result = installer.install_update(target, asset, [], old_version='1', format_id='executable')
        assert result.checksum == 'verified (sha256)'
        assert Path(result.backup_path).read_bytes() == before
        assert target.read_bytes() == body
    assert not list(tmp_path.glob('.*.part'))


@pytest.mark.parametrize('name,tag,expected', [
    ('App-v2.4.0-x86_64.AppImage', 'v2.4.0', 'App-v*-x86_64.AppImage'),
    ('App2-2.4.0.AppImage', 'v2', 'App2-*.AppImage'),
    ('App-[gtk]-2.4.0.AppImage', 'continuous', 'App-[[]gtk]-*.AppImage'),
])
def test_asset_pattern_does_not_replace_product_digits_or_glob_flavors(name, tag, expected):
    import fnmatch
    pattern = pattern_from_asset(name, tag)
    assert pattern == expected
    assert fnmatch.fnmatchcase(name.replace('2.4.0', '2.5.0'), pattern)


def test_prerelease_preferences_apply_before_hash_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(checker, 'find_expected_checksum', lambda *a: pytest.fail('excluded prerelease'))
    result = run_check([Release('nightly', prerelease=True, assets=[Asset('App.AppImage', 'https://x/a')])],
                       installed=None, installed_path=str(tmp_path / 'app'))
    assert result.status is UpdateStatus.UNAVAILABLE
    assert result.prereleases_only and result.asset is None


def test_checksum_based_update_requires_explicit_install_choice(qapp, service, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    path = tmp_path / 'App.AppImage'
    path.write_bytes(b'installed')
    entry = AppEntry(name='App', path=str(path), github_repo='https://github.com/o/r')
    service.db.add(entry)
    asset = Asset('App.AppImage', 'https://x/a', digest='sha256:' + 'a' * 64)
    outcome = run_check([Release('continuous', assets=[asset])], installed=None, installed_path=str(path))
    UpdateService(service).apply_check(entry.id, outcome)
    win = MainWindow(service)
    seen = []
    def decline(*args):
        seen.append(args[2])
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, 'question', decline)
    win.start_update(entry.id)
    assert seen and 'ordering is unknown' in seen[0]
    assert entry.id not in win._busy
    assert path.read_bytes() == b'installed'
    win._quitting = True
    win.close()


def test_rolling_rebuild_with_same_filename_version_uses_hash(tmp_path):
    target = tmp_path / 'App.AppImage'
    target.write_bytes(b'previous build')
    asset = Asset('App-2.0.AppImage', 'https://x/a', digest='sha256:' + hashlib.sha256(b'rebuilt').hexdigest())
    result = run_check([Release('continuous', assets=[asset])], installed='2.0', installed_path=str(target))
    assert result.status is UpdateStatus.UPDATE_AVAILABLE and result.comparison == 'checksum'


def test_unnamed_hash_in_global_sums_cannot_identify_asset(monkeypatch):
    monkeypatch.setattr(installer, '_fetch_text', lambda *a: 'a' * 64)
    assert installer.find_expected_checksum({'name': 'App.AppImage'},
                                           [{'name': 'SHA256SUMS', 'url': 'https://x/sums'}]) is None
    assert installer.find_expected_checksum({'name': 'App.AppImage'},
                                           [{'name': 'App.AppImage.sha256', 'url': 'https://x/sum'}]) == ('sha256', 'a' * 64)


def test_check_worker_always_reports_unexpected_failure(qapp, monkeypatch):
    from appforge.ui import workers
    def broken(**kwargs):
        raise ValueError('malformed release response')
    monkeypatch.setattr(workers, 'check_for_update', broken)
    job = workers.CheckJob('app')
    seen = []
    job.signals.done.connect(lambda app_id, outcome: seen.append((app_id, outcome)))
    job.run()
    assert seen[0][0] == 'app'
    assert seen[0][1].status is UpdateStatus.FAILED
    assert 'malformed release response' in seen[0][1].message


@pytest.mark.parametrize('name,expected', [
    ('App-1.2.3+abcdef-x86_64.AppImage', '1.2.3+abcdef'),
    ('App-1.2.3-rc1+build.42.AppImage', '1.2.3-rc1+build.42'),
    ('App-1.2.3~beta2.AppImage', '1.2.3~beta2'),
])
def test_filename_build_and_prerelease_metadata(name, expected):
    assert version_from_filename(name) == expected


def test_build_metadata_is_not_prerelease_or_ordered():
    assert compare('1.2.3+rc1', '1.2.3') == 0
    assert compare('1.2.3+build.5', '1.2.3+build.4') == 0
    assert compare('1.2.3~rc1', '1.2.3') == -1


@pytest.mark.parametrize('failure', [None, 'checksum', 'truncated', 'invalid', 'cancelled'])
def test_real_appimage_install_offline(fixtures, tmp_path, monkeypatch, failure):
    import shutil
    import threading
    target = tmp_path / 'MyApp.AppImage'
    shutil.copy2(fixtures['alpha'], target)
    original = target.read_bytes()
    body = fixtures['gamma'].read_bytes()
    expected = len(body)
    checksum = hashlib.sha512(body).hexdigest()
    if failure == 'checksum':
        checksum = '0' * 128
    elif failure == 'truncated':
        body = body[:len(body) // 2]
    elif failure == 'invalid':
        body = b'<html>error response</html>' * 10000
        expected = len(body)
    class Response(io.BytesIO):
        headers = {'Content-Length': str(expected)}
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: Response(body))
    asset = {'name': 'App.AppImage', 'url': 'https://x/a', 'size': expected,
             'digest': 'sha512:' + checksum}
    cancel = threading.Event()
    if failure == 'cancelled':
        cancel.set()
    if failure:
        with pytest.raises(installer.InstallError):
            installer.install_update(target, asset, [], old_version='2.3.1', cancel=cancel)
        assert target.read_bytes() == original
        assert not installer.backup_dir_for(target).exists()
    else:
        result = installer.install_update(target, asset, [], old_version='2.3.1')
        assert result.checksum == 'verified (sha512)'
        assert target.read_bytes() == body
        assert Path(result.backup_path).read_bytes() == original
    assert not list(tmp_path.glob('.*.part'))
