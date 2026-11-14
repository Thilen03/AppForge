"""Offline provider, cache and GUI release-note regressions."""
import io
import json
import threading
from copy import deepcopy

import pytest
from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QTextDocument

from appforge.core.models import UpdateStatus
from appforge.core.updates.checker import check_for_update, CheckOutcome
from appforge.core.updates.github import Asset, GitHubClient, GitHubError, Release
from appforge.core.updates.providers import ForgejoClient, GitLabClient, SelfHostedClient
from appforge.core.updates.notes import cached_notes, fetch_notes, release_notes
from appforge.core.updates.service import UpdateService
from appforge.ui.main_window import MainWindow
from appforge.ui.release_notes_dialog import NotesDocument, open_web_link
from test_details import add_script
from test_gui import qapp, wait_for  # noqa: F401


class Client:
    def __init__(self, releases):
        self.items = releases
        self.calls = []

    def releases(self, owner, name):
        self.calls.append((owner, name, threading.get_ident()))
        return self.items


def release(tag='v2.0', body='## Changes\n\n- A useful fix\n\n[Read more](https://example.org)'):
    return Release(tag, name='Example release', body=body, prerelease=True,
                   published_at='2026-11-01T12:00:00Z',
                   html_url='https://github.com/owner/repo/releases/tag/' + tag,
                   assets=[Asset('Example-2.0-linux-x86_64', 'https://example.org/Example-2.0-linux-x86_64')])


def prepare(service, tmp_path, rel=None):
    entry = add_script(service, tmp_path)
    rel = rel or release()
    outcome = check_for_update(repo_url=entry.github_repo, installed_version='1.0',
                               current_filename='Example-1.0.sh', app_name='Example',
                               format_id='executable', include_prereleases=True, client=Client([rel]))
    UpdateService(service).apply_check(entry.id, outcome)
    return service.get(entry.id)


@pytest.mark.parametrize('kind', ['github', 'gitlab', 'codeberg', 'forgejo', 'gitea', 'self-gitlab'])
@pytest.mark.parametrize('body', ['## Hello\n\nRelease description', None])
def test_provider_descriptions(kind, body):
    seen = []
    payload = dict(tag_name='v2.0', name='Release', body=body, description=body,
                   published_at='2026-11-01', released_at='2026-11-01', prerelease=True, assets=[])
    if 'gitlab' in kind:
        payload['assets'] = {'links': []}
    def opener(req, timeout=None):
        seen.append(req)
        if kind == 'self-gitlab' and '/api/v1/' in req.full_url:
            import urllib.error
            raise urllib.error.HTTPError(req.full_url, 404, '', {}, None)
        return io.BytesIO(json.dumps([payload]).encode())
    client = (GitHubClient(token='test', opener=opener) if kind == 'github' else
              GitLabClient(opener=opener) if kind == 'gitlab' else
              ForgejoClient(opener=opener) if kind == 'codeberg' else
              SelfHostedClient('git.example.org', opener=opener))
    rel = client.releases('owner', 'repo')[0]
    assert rel.body == (body or '')
    assert rel.tag == 'v2.0' and rel.name == 'Release' and rel.published_at
    assert all(not req.has_header('Authorization') for req in seen) if kind != 'github' else True


def test_cache_replace_failed_check_and_source_identity(service, tmp_path):
    entry = prepare(service, tmp_path)
    assert cached_notes(entry)['body'].startswith('## Changes')
    UpdateService(service).apply_check(entry.id, CheckOutcome(UpdateStatus.FAILED, 'offline'))
    assert cached_notes(service.get(entry.id)) == cached_notes(entry)
    newer = release('v3.0', '')
    new_outcome = CheckOutcome(UpdateStatus.UPDATE_AVAILABLE, tag=newer.tag,
                               latest_version='3.0', notes=release_notes('https://github.com/owner/repo', newer))
    UpdateService(service).apply_check(entry.id, new_outcome)
    current = service.get(entry.id)
    assert cached_notes(current)['tag'] == 'v3.0' and cached_notes(current)['body'] == ''
    current.github_repo = 'other/repo'
    assert cached_notes(current) is None
    current.github_repo = entry.github_repo
    current.metadata['update']['tag'] = 'v4.0'
    assert cached_notes(current) is None
    # Old databases without cached descriptions remain readable.
    current.metadata['update'].pop('notes')
    assert cached_notes(current) is None


def test_exact_tag_not_newest_draft_or_missing():
    client = Client([release('v3.0'), release('v2.0')])
    assert fetch_notes('owner/repo', 'v2.0', client=client)['tag'] == 'v2.0'
    client.items[1].draft = True
    with pytest.raises(GitHubError, match='no longer'):
        fetch_notes('owner/repo', 'v2.0', client=client)
    with pytest.raises(GitHubError, match='first'):
        fetch_notes('', '', client=client)


def test_cards_details_cached_view_read_only_and_empty(qapp, service, tmp_path):
    entry = prepare(service, tmp_path)
    original = deepcopy(entry)
    from pathlib import Path
    before = Path(entry.path).read_bytes()
    win = MainWindow(service)
    action = next(a for a in win._card(entry.id)._build_menu().actions() if a.text() == 'Release notes…')
    action.trigger()
    dialog = win._release_notes[entry.id]
    assert dialog._job is None  # cached notes require no request
    assert 'A useful fix' in dialog.browser.toPlainText()
    assert dialog.browser.verticalScrollBar().value() == 0
    assert 'Prerelease' in dialog.metadata.text() and 'v2.0' in dialog.metadata.text()
    win.show_details(entry.id)
    win._details[entry.id].buttons['notes'].click()
    assert win._release_notes[entry.id] is dialog
    assert service.get(entry.id) == original and Path(entry.path).read_bytes() == before
    dialog.render(release_notes('https://github.com/owner/repo', release(body='')))
    assert 'No release description' in dialog.browser.toPlainText()
    win._quitting = True
    win.close()


def test_async_refresh_cache_and_error(qapp, service, tmp_path):
    entry = prepare(service, tmp_path)
    client = Client([release(body='Refreshed notes')])
    win = MainWindow(service, github_client=client)
    win.show_release_notes(entry.id)
    dialog = win._release_notes[entry.id]
    dialog.refresh_btn.click()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert dialog.browser.toPlainText() == 'Refreshed notes'
    assert cached_notes(service.get(entry.id))['body'] == 'Refreshed notes'
    assert client.calls[0][2] != threading.get_ident()
    client.releases = lambda *args: (_ for _ in ()).throw(GitHubError('Offline', 'network'))
    dialog.refresh_btn.click()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert 'Offline' in dialog.notice.text() and 'cached' in dialog.notice.text()
    assert dialog.browser.toPlainText() == 'Refreshed notes'
    assert service.get(entry.id).update_status == entry.update_status
    win._quitting = True
    win.close()


@pytest.mark.parametrize('change', ['source', 'tag', 'remove', 'close'])
def test_stale_and_closed_requests(qapp, service, tmp_path, change):
    entry = prepare(service, tmp_path)
    entered, unblock = threading.Event(), threading.Event()
    class Blocked:
        def releases(self, *args):
            entered.set()
            unblock.wait(5)
            return [release(body='Stale content')]
    win = MainWindow(service, github_client=Blocked())
    win.show_release_notes(entry.id)
    dialog = win._release_notes[entry.id]
    dialog.load()
    assert wait_for(qapp, entered.is_set)
    if change == 'close':
        win._quitting = True
        win.close()
        qapp.processEvents()
        service.db.close()
    elif change == 'remove':
        service.remove_application(entry.id)
    else:
        current = service.get(entry.id)
        if change == 'source':
            current.github_repo = None  # no replacement request necessary
        else:
            current.metadata['update']['tag'] = None
        service.db.update(current)
        win.reload()
    unblock.set()
    assert QThreadPool.globalInstance().waitForDone(2000)
    qapp.processEvents()
    if change not in ('close', 'remove'):
        assert 'Stale content' not in dialog.browser.toPlainText()
        assert cached_notes(service.get(entry.id)) is None
    if change != 'close':
        win._quitting = True
        win.close()


def test_untrusted_resources_and_links(qapp, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    seen = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: seen.append(url.toString()))
    for url in ['file:///etc/passwd', 'javascript:alert(1)', 'data:text/html,hello',
                'https://user:password@example.org', 'relative/path', 'https://example.org/release']:
        open_web_link(QUrl(url))
    assert seen == ['https://example.org/release']
    doc = NotesDocument()
    for url in ['file:///etc/passwd', 'https://example.org/tracker.png', 'data:image/png,test']:
        assert doc.loadResource(QTextDocument.ImageResource, QUrl(url)) is None


def test_batch_notes_never_approve_install(qapp, service, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    entry = prepare(service, tmp_path)
    win = MainWindow(service)
    choices = iter(['Release notes…', 'Cancel'])
    clicked = {}
    def execute(box):
        wanted = next(choices)
        clicked['button'] = next(b for b in box.buttons() if b.text() == wanted)
    monkeypatch.setattr(QMessageBox, 'exec', execute)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda _: clicked['button'])
    seen = []
    monkeypatch.setattr(win, '_show_batch_notes', lambda entries: seen.extend(e.id for e in entries))
    monkeypatch.setattr(win, 'start_update', lambda *args, **kwargs: pytest.fail('Notes approved an update'))
    win.update_all()
    assert seen == [entry.id] and win._batch is None and not win._jobs
    win._quitting = True
    win.close()


def test_legacy_cache_fetch_failure_requires_explicit_retry(qapp, service, tmp_path):
    entry = prepare(service, tmp_path)
    entry.metadata['update'].pop('notes')
    service.db.update(entry)
    client = Client([])
    win = MainWindow(service, github_client=client)
    win.show_release_notes(entry.id)
    dialog = win._release_notes[entry.id]
    assert wait_for(qapp, lambda: dialog._job is None)
    assert 'no longer' in dialog.notice.text()
    for _ in range(3):
        dialog.sync()
    assert len(client.calls) == 1
    client.items = [release(body='')]
    dialog.load()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert 'No release description' in dialog.browser.toPlainText()
    assert len(client.calls) == 2
    win._quitting = True
    win.close()
