"""Offline repository discovery, safe initial downloads, and the Add workflow."""
import hashlib
import io
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QFileDialog

from appforge.core import downloads
from appforge.core.database import Database
from appforge.core.discovery import ROOTS_KEY, load_paths, save_paths
from appforge.core.downloads import download_application, download_choices, fetch_releases, validate_downloaded
from appforge.core.library import LibraryError
from appforge.core.updates import installer
from appforge.core.updates.github import Asset, GitHubError, Release
from appforge.ui.dialogs import AddApplicationDialog
from appforge.ui.download_dialog import AddSourceDialog, DownloadApplicationDialog
from appforge.ui.main_window import MainWindow
from test_gui import qapp, wait_for  # noqa: F401

SOURCE = 'https://github.com/o/r'
BODY = b'#!/bin/sh\necho never executed\n'


def release(*names, tag='v2.0', pre=False, draft=False):
    return Release(tag, prerelease=pre, draft=draft,
                   assets=[Asset(n, f'https://x/{n}', len(BODY),
                                 'sha256:' + hashlib.sha256(BODY).hexdigest()) for n in names])


def choice(rel=None):
    return download_choices(SOURCE, [rel or release('tool-linux-x86_64')], include_prereleases=True)[0]


def mock_download(monkeypatch, body=BODY, claimed=None):
    class Response(io.BytesIO):
        headers = {'Content-Length': str(len(body) if claimed is None else claimed)}
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: Response(body))


def test_discovery_filters_archives_platforms_metadata_and_wrong_arch():
    rel = release('App-x86_64.AppImage', 'tool-linux-amd64', 'tool-arm64', 'tool-windows-amd64.exe',
                  'tool-darwin-amd64', 'tool.tar.gz', 'SHA256SUMS', 'App.AppImage.zsync',
                  'icon.png', 'LICENSE', 'notes.md')
    assert [c.asset.name for c in download_choices(SOURCE, [rel], arch='x86_64')] == [
        'App-x86_64.AppImage', 'tool-linux-amd64']
    assert not download_choices(SOURCE, [release('tool', pre=True), release('tool', draft=True)])
    assert len(download_choices(SOURCE, [release('tool', pre=True)], include_prereleases=True)) == 1


@pytest.mark.parametrize('name', ['../bad.AppImage', '/bad.AppImage', 'a/b.AppImage', 'a\\b.AppImage',
                                  '.hidden', 'a\nAppImage', '.', '..', ''])
def test_reject_unsafe_asset_names(name):
    assert not download_choices(SOURCE, [release(name)])


@pytest.mark.parametrize('url', ['http://x/tool', 'file:///tmp/tool', 'https://user:secret@x/tool', 'https://[bad'])
def test_reject_bad_download_urls(url):
    rel = release('tool')
    rel.assets[0].url = url
    assert not download_choices(SOURCE, [rel])


@pytest.mark.parametrize('source,canonical', [('o/r', SOURCE), (SOURCE + '/releases/tag/v2', SOURCE),
                                             ('https://gitlab.com/a/b/-/releases/v2', 'https://gitlab.com/a/b'),
                                             ('https://codeberg.org/a/b', 'https://codeberg.org/a/b')])
def test_fetch_normalizes_supported_links(source, canonical):
    seen = []
    client = SimpleNamespace(releases=lambda *a: seen.append(a) or [release('tool')])
    assert fetch_releases(source, client=client)[0] == canonical
    assert len(seen) == 1


def test_invalid_source_and_cancel_before_provider_request():
    with pytest.raises(GitHubError):
        fetch_releases('ftp://x/repo')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(installer.InstallCancelled):
        fetch_releases(SOURCE, client=SimpleNamespace(releases=lambda *a: pytest.fail('cancelled')), cancel=cancel)


def test_verified_download_publishes_executable_without_backups_or_execution(tmp_path, monkeypatch):
    mock_download(monkeypatch)
    result = download_application(choice(), str(tmp_path))
    assert Path(result.path).read_bytes() == BODY
    assert os.access(result.path, os.X_OK)
    assert result.checksum == 'verified (sha256)'
    validate_downloaded(result)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['tool-linux-x86_64']


@pytest.mark.parametrize('failure', ['checksum', 'truncated', 'metadata_size', 'invalid', 'cancelled', 'network'])
def test_failed_download_leaves_no_file_or_parts(tmp_path, monkeypatch, failure):
    picked = choice()
    body, claimed = BODY, len(BODY)
    cancel = threading.Event()
    if failure == 'checksum':
        picked.asset.digest = 'sha256:' + '0' * 64
    elif failure == 'truncated':
        body = BODY[:10]
    elif failure == 'metadata_size':
        picked.asset.size = 999
    elif failure == 'invalid':
        body = b'<html>not an executable</html>'
        claimed = len(body)
        picked.asset.size = 0
    elif failure == 'cancelled':
        cancel.set()
    mock_download(monkeypatch, body, claimed)
    if failure == 'network':
        def fail(*a, **kw):
            raise OSError('offline')
        monkeypatch.setattr(installer, '_open', fail)
    with pytest.raises(installer.InstallError):
        download_application(picked, str(tmp_path), cancel=cancel)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('kind', ['file', 'symlink', 'race'])
def test_existing_files_and_concurrent_collisions_are_never_overwritten(tmp_path, monkeypatch, kind):
    picked = choice()
    target = tmp_path / picked.asset.name
    other = tmp_path / 'important'
    other.write_bytes(b'keep')
    if kind == 'file':
        target.write_bytes(b'original')
    elif kind == 'symlink':
        target.symlink_to(other)
    else:
        original = downloads.download_verified
        def collide(*args, **kw):
            result = original(*args, **kw)
            target.write_bytes(b'original')
            return result
        monkeypatch.setattr(downloads, 'download_verified', collide)
    mock_download(monkeypatch)
    with pytest.raises(installer.InstallError):
        download_application(picked, str(tmp_path))
    assert target.read_bytes() == (b'keep' if kind == 'symlink' else b'original')
    assert other.read_bytes() == b'keep'
    assert not list(tmp_path.glob('.*.part'))


def test_symlink_folder_is_rejected(tmp_path):
    folder = tmp_path / 'real'
    folder.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(folder, target_is_directory=True)
    with pytest.raises(installer.InstallError, match='symlinks'):
        download_application(choice(), str(alias))


def test_download_identity_rejects_modified_file(tmp_path, monkeypatch):
    mock_download(monkeypatch)
    result = download_application(choice(), str(tmp_path))
    Path(result.path).write_bytes(b'changed')
    with pytest.raises(LibraryError, match='changed'):
        validate_downloaded(result)


def test_real_appimage_download_uses_shared_validation(fixtures, tmp_path, monkeypatch):
    body = fixtures['alpha'].read_bytes()
    picked = choice(release('App-2.0-x86_64.AppImage'))
    picked.asset.size = len(body)
    picked.asset.digest = 'sha256:' + hashlib.sha256(body).hexdigest()
    mock_download(monkeypatch, body)
    result = download_application(picked, str(tmp_path))
    assert Path(result.path).read_bytes() == body and result.checksum == 'verified (sha256)'
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: pytest.fail('AppImage downloaded again'))
    existing = download_application(picked, str(tmp_path))
    assert existing.signature == result.signature and existing.checksum == 'verified (sha256)'


@pytest.fixture
def dialog(qapp, service, tmp_path):
    folder = tmp_path / 'apps'
    folder.mkdir()
    save_paths(service.db, ROOTS_KEY, [str(folder)])
    client = SimpleNamespace(releases=lambda *a: [release('tool-linux-x86_64', tag='v2.0-rc1', pre=True)])
    dlg = DownloadApplicationDialog(service, client=client)
    yield dlg
    if dlg.job:
        dlg.reject()
        assert wait_for(qapp, lambda: dlg.job is None)
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()


def find(qapp, dlg):
    dlg.url_edit.setText(SOURCE)
    dlg.find_releases()
    assert wait_for(qapp, lambda: dlg.job is None)


def test_empty_destination_prompts_for_and_persists_discovery_folder(qapp, service, tmp_path, monkeypatch):
    save_paths(service.db, ROOTS_KEY, [])
    dlg = DownloadApplicationDialog(service)
    assert dlg.folder_combo.count() == 0
    assert 'Add a folder' in dlg.folder_hint.text()
    assert not dlg.download_btn.isEnabled()
    folder = tmp_path / 'apps'
    folder.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: str(folder))
    dlg.add_folder()
    assert dlg.folder_combo.currentData() == str(folder)
    assert load_paths(service.db, ROOTS_KEY) == [str(folder)]
    other = Database(service.db.path)
    try:
        assert load_paths(other, ROOTS_KEY) == [str(folder)]
    finally:
        other.close()
    dlg.close()


def test_full_download_then_review_registers_source_version_channel_and_variant(dialog, qapp, service, monkeypatch):
    mock_download(monkeypatch)
    find(qapp, dialog)
    assert not dialog.choices and 'nightly' in dialog.status.text()
    dialog.pre_cb.setChecked(True)
    assert len(dialog.choices) == 1 and dialog.download_btn.isEnabled()
    dialog.start_download()
    assert wait_for(qapp, lambda: dialog.downloaded is not None)
    assert not service.list_applications()  # final review is required
    review = AddApplicationDialog(service, initial_path=dialog.downloaded.path, downloaded=dialog.downloaded)
    review.menu_cb.setChecked(False)
    assert wait_for(qapp, lambda: review.metadata is not None)
    assert review.repo_edit.text() == SOURCE
    assert review.metadata.version == '2.0-rc1'
    review._accept()
    entry = service.get(review.added.id)
    assert entry.github_repo == SOURCE and entry.installed_version == '2.0-rc1'
    assert entry.metadata['include_prereleases']
    assert entry.metadata['asset_pattern'] == 'tool-linux-x86_64'
    assert service.refresh_metadata(entry.id).installed_version == '2.0-rc1'
    review.close()


def test_cancel_final_review_keeps_file_and_does_not_register(dialog, qapp, service, monkeypatch):
    mock_download(monkeypatch)
    find(qapp, dialog)
    dialog.pre_cb.setChecked(True)
    dialog.start_download()
    assert wait_for(qapp, lambda: dialog.downloaded is not None)
    review = AddApplicationDialog(service, initial_path=dialog.downloaded.path, downloaded=dialog.downloaded)
    assert wait_for(qapp, lambda: review.metadata is not None)
    review.reject()
    assert Path(dialog.downloaded.path).read_bytes() == BODY
    assert not service.list_applications()
    review.close()


def test_changing_source_clears_old_choices(dialog, qapp):
    dialog.pre_cb.setChecked(True)
    find(qapp, dialog)
    assert dialog.choices
    dialog.url_edit.setText('https://github.com/other/repo')
    assert not dialog.choices and not dialog.download_btn.isEnabled()


def test_closing_search_waits_for_worker_and_discards_result(dialog, qapp):
    entered, release_worker = threading.Event(), threading.Event()
    def slow(*a):
        entered.set()
        release_worker.wait(5)
        return [release('tool')]
    dialog.client = SimpleNamespace(releases=slow)
    dialog.url_edit.setText(SOURCE)
    dialog.find_releases()
    assert entered.wait(2)
    dialog.reject()
    assert dialog.job and dialog._closing
    release_worker.set()
    assert wait_for(qapp, lambda: dialog.job is None)
    assert dialog.result() == QDialog.Rejected and not dialog.choices


@pytest.mark.parametrize('mode', ['local', 'link'])
def test_add_source_chooser_routes_selection(qapp, mode):
    dlg = AddSourceDialog()
    dlg._choose(mode)
    assert dlg.mode == mode and dlg.result() == QDialog.Accepted


def test_main_window_local_and_drag_drop_preserve_existing_add_form(qapp, service, tmp_path, monkeypatch):
    from appforge.ui import download_dialog, main_window
    calls = []
    monkeypatch.setattr(download_dialog.AddSourceDialog, 'exec', lambda self: self._choose('local') or QDialog.Accepted)
    monkeypatch.setattr(main_window.AddApplicationDialog, 'exec', lambda self: calls.append(self.path_edit.text()) or QDialog.Rejected)
    win = MainWindow(service)
    win.add_application()
    path = tmp_path / 'local-tool'
    path.write_bytes(BODY)
    monkeypatch.setattr(download_dialog.AddSourceDialog, 'exec', lambda self: pytest.fail('drop must bypass chooser'))
    win.add_application(str(path))
    assert calls == ['', str(path)]
    assert wait_for(qapp, lambda: all(not child._jobs for child in win.findChildren(AddApplicationDialog)))
    win._quitting = True
    win.close()


@pytest.mark.parametrize('mode', ['download', 'cancel_retry', 'previous_session'])
def test_main_window_link_route_downloads_reviews_and_adds(qapp, service, tmp_path, monkeypatch, mode):
    cancel_first = mode == 'cancel_retry'
    mock_download(monkeypatch)
    transfers = []
    open_asset = installer._open
    def count_transfer(*args, **kwargs):
        transfers.append(True)
        return open_asset(*args, **kwargs)
    monkeypatch.setattr(installer, '_open', count_transfer)
    folder = tmp_path / 'apps'
    folder.mkdir()
    save_paths(service.db, ROOTS_KEY, [str(folder)])
    monkeypatch.setattr(AddSourceDialog, 'exec', lambda self: self._choose('link') or QDialog.Accepted)
    if mode == 'previous_session':
        saved = folder / 'tool-linux-x86_64'
        saved.write_bytes(BODY)
        saved.chmod(0o755)
    original_download_exec = DownloadApplicationDialog.exec
    original_review_exec = AddApplicationDialog.exec
    timers = []
    def download_exec(dlg):
        dlg.url_edit.setText(SOURCE)
        timer = QTimer(dlg)
        def advance():
            if dlg.job is None and dlg.choices:
                timer.stop()
                dlg.start_download()
        timer.timeout.connect(advance)
        timer.start(10)
        timers.append(timer)
        QTimer.singleShot(0, dlg.find_releases)
        return original_download_exec(dlg)
    reviews = []
    def review_exec(dlg):
        reviews.append(dlg)
        dlg.menu_cb.setChecked(False)
        timer = QTimer(dlg)
        def advance():
            if dlg.metadata:
                timer.stop()
                if cancel_first and len(reviews) == 1:
                    dlg.reject()
                else:
                    dlg._accept()
        timer.timeout.connect(advance)
        timer.start(10)
        timers.append(timer)
        return original_review_exec(dlg)
    monkeypatch.setattr(DownloadApplicationDialog, 'exec', download_exec)
    monkeypatch.setattr(AddApplicationDialog, 'exec', review_exec)
    win = MainWindow(service, github_client=SimpleNamespace(releases=lambda *a: [release('tool-linux-x86_64')]))
    # Fail safely instead of leaving a modal test hung if a regression blocks the flow.
    watchdog = QTimer(win)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: [d.reject() for d in win.findChildren(QDialog)])
    watchdog.start(5000)
    win.add_application()
    if cancel_first:
        assert not service.list_applications()
        assert (folder / 'tool-linux-x86_64').read_bytes() == BODY
        win.add_application()
    watchdog.stop()
    assert len(transfers) == (0 if mode == 'previous_session' else 1)
    assert len(reviews) == (2 if cancel_first else 1)
    assert wait_for(qapp, lambda: not win._busy)
    entries = service.list_applications()
    assert len(entries) == 1 and entries[0].path == str(folder / 'tool-linux-x86_64')
    assert entries[0].github_repo == SOURCE and entries[0].installed_version == '2.0'
    assert Path(entries[0].path).read_bytes() == BODY
    win._quitting = True
    win.close()


def test_changed_download_cannot_be_registered(dialog, qapp, service, monkeypatch):
    mock_download(monkeypatch)
    find(qapp, dialog)
    dialog.pre_cb.setChecked(True)
    dialog.start_download()
    assert wait_for(qapp, lambda: dialog.downloaded is not None)
    review = AddApplicationDialog(service, initial_path=dialog.downloaded.path, downloaded=dialog.downloaded)
    assert wait_for(qapp, lambda: review.metadata is not None)
    Path(dialog.downloaded.path).write_bytes(b'changed since inspection')
    review._accept()
    assert review.added is None and not service.list_applications()
    assert 'changed' in review.file_msg.text()
    review.close()


def test_publish_fallback_remains_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads.ctypes, 'CDLL', lambda *a, **kw: SimpleNamespace())
    mock_download(monkeypatch)
    result = download_application(choice(), str(tmp_path))
    assert Path(result.path).read_bytes() == BODY
    assert download_application(choice(), str(tmp_path)).signature == result.signature


def test_cancellation_during_transfer_removes_temporary_file(tmp_path, monkeypatch):
    cancel = threading.Event()
    class Response(io.BytesIO):
        headers = {'Content-Length': str(len(BODY))}
        def read(self, *a):
            cancel.set()
            return super().read(*a)
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: Response(BODY))
    with pytest.raises(installer.InstallCancelled):
        download_application(choice(), str(tmp_path), cancel=cancel)
    assert not list(tmp_path.iterdir())


def test_replaced_download_is_not_reported_as_verified(tmp_path, monkeypatch):
    mock_download(monkeypatch)
    publish = downloads._publish_exclusive
    def replace_file(root_fd, temporary, name):
        publish(root_fd, temporary, name)
        target = tmp_path / name
        target.unlink()
        target.write_bytes(b'different file')
    monkeypatch.setattr(downloads, '_publish_exclusive', replace_file)
    with pytest.raises(installer.InstallError, match='changed'):
        download_application(choice(), str(tmp_path))
    assert (tmp_path / 'tool-linux-x86_64').read_bytes() == b'different file'
    assert not list(tmp_path.glob('.*.part'))


def test_sha512_lists_are_not_executable_candidates():
    assert not download_choices(SOURCE, [release('SHA512SUMS', 'sha512sum.txt')])


@pytest.mark.parametrize('digest_kind', ['sha256', 'sha512', 'missing', 'sidecar'])
def test_existing_file_continues_without_session_record_or_asset_transfer(tmp_path, monkeypatch, digest_kind):
    picked = choice()
    target = tmp_path / picked.asset.name
    target.write_bytes(BODY)
    target.chmod(0o644)
    before = (target.read_bytes(), target.stat())
    if digest_kind == 'missing':
        picked.asset.digest = None
    elif digest_kind == 'sha512':
        picked.asset.digest = 'sha512:' + hashlib.sha512(BODY).hexdigest()
    elif digest_kind == 'sidecar':
        picked.asset.digest = None
        picked.release.assets.append(Asset(picked.asset.name + '.sha256', 'https://x/checksum'))
    def open_file(url, **kwargs):
        assert digest_kind == 'sidecar' and url == 'https://x/checksum', 'Asset downloaded again'
        return io.BytesIO(hashlib.sha256(BODY).hexdigest().encode())
    monkeypatch.setattr(installer, '_open', open_file)
    result = download_application(picked, str(tmp_path))
    validate_downloaded(result)
    assert result.choice == picked and result.path == str(target)
    assert result.checksum == ('not available' if digest_kind == 'missing' else
                               'verified (sha512)' if digest_kind == 'sha512' else 'verified (sha256)')
    assert target.read_bytes() == before[0]
    after = target.stat()
    assert (after.st_ino, after.st_mode, after.st_mtime_ns, after.st_ctime_ns) == (
        before[1].st_ino, before[1].st_mode, before[1].st_mtime_ns, before[1].st_ctime_ns)
    assert not list(tmp_path.glob('.*.part'))


@pytest.mark.parametrize('kind', ['size', 'checksum', 'format', 'directory', 'symlink', 'fifo'])
def test_invalid_existing_file_is_preserved(tmp_path, monkeypatch, kind):
    picked = choice()
    target = tmp_path / picked.asset.name
    if kind == 'directory':
        target.mkdir()
    elif kind == 'symlink':
        other = tmp_path / 'other'
        other.write_bytes(BODY)
        target.symlink_to(other)
    elif kind == 'fifo':
        os.mkfifo(target)
    else:
        body = BODY[:-1] if kind == 'size' else b'x' * len(BODY) if kind == 'format' else BODY
        target.write_bytes(body)
        if kind == 'checksum':
            picked.asset.digest = 'sha256:' + '0' * 64
    before = target.lstat()
    monkeypatch.setattr(installer, '_open', lambda *a, **kw: pytest.fail('Unexpected network request'))
    with pytest.raises(installer.InstallError):
        download_application(picked, str(tmp_path))
    after = target.lstat()
    assert (before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns) == (
        after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns)


def test_existing_file_verification_cancels_and_rejects_changes(tmp_path, monkeypatch):
    picked = choice()
    target = tmp_path / picked.asset.name
    target.write_bytes(BODY)
    cancel = threading.Event()
    with pytest.raises(installer.InstallCancelled):
        download_application(picked, str(tmp_path), cancel=cancel, progress=lambda *_: cancel.set())
    assert target.read_bytes() == BODY
    def change(*_):
        target.write_bytes(BODY + b'changed')
    with pytest.raises(LibraryError, match='changed'):
        download_application(picked, str(tmp_path), progress=change)
    assert target.read_bytes() == BODY + b'changed'


def test_valid_file_appearing_during_download_is_used_without_overwrite(tmp_path, monkeypatch):
    mock_download(monkeypatch)
    picked = choice()
    target = tmp_path / picked.asset.name
    download = downloads.download_verified
    def collide(*args, **kwargs):
        result = download(*args, **kwargs)
        target.write_bytes(BODY)
        target.chmod(0o644)
        return result
    monkeypatch.setattr(downloads, 'download_verified', collide)
    result = download_application(picked, str(tmp_path))
    validate_downloaded(result)
    assert result.signature == downloads.file_signature(target)
    assert target.read_bytes() == BODY and target.stat().st_mode & 0o777 == 0o644
    assert not list(tmp_path.glob('.*.part'))
