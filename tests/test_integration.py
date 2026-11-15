"""Cross-feature regressions using real SQLite/files and an offline HTTP boundary."""
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import urllib.error

import pytest

from test_gui import qapp  # noqa: F401

from appforge.core.backups import BackupService
from appforge.core.database import Database, MIGRATIONS
from appforge.core.desktop.service import DesktopService
from appforge.core.details import inspect_details
from appforge.core.discovery import import_candidate, scan
from appforge.core.library import LibraryService
from appforge.core.library_transfer import export_library, read_export, preview_import, prepare_import
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.settings import AppSettings
from appforge.core.storage import scan_storage, cleanup_backups
from appforge.core.tray import TrayShortcuts
from appforge.core.updates import installer
from appforge.core.updates.checker import check_for_update
from appforge.core.updates.github import Asset, Release
from appforge.core.updates.notes import cached_notes
from appforge.core.updates.service import UpdateService


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}


def script(path, body=b'#!/bin/sh\necho original\n'):
    path.write_bytes(body)
    path.chmod(0o750)
    return path


def reopen(service):
    path, icons, desktop = service.db.path, service.icons_dir, service.desktop
    service.db.close()
    return LibraryService(Database(path), icons, desktop=desktop)


@pytest.mark.parametrize('version', range(len(MIGRATIONS) + 1))
def test_fresh_and_populated_schema_upgrades_preserve_every_field(tmp_path, version):
    path = tmp_path / 'library.db'
    entry = AppEntry(name='Existing App', path='/opt/Existing.AppImage', id='legacy-id',
                     installed_version='1.0', latest_version='2.0', github_repo='https://codeberg.org/o/r',
                     icon_path='/icons/existing.png', description='Keep this', last_update_check=12,
                     update_status=UpdateStatus.UPDATE_AVAILABLE, added_at=10, updated_at=11,
                     metadata={'category': 'Games', 'desktop_entry': True, 'menu_category': 'Game',
                               'env_vars': {'MODE': 'quiet'}, 'include_prereleases': True,
                               'update': {'tag': 'v2.0'}, 'last_install': {'tag': 'v1.0', 'time': 11}},
                     backup_info={'backups': [{'file': '/opt/.Existing.backups/old.AppImage',
                                               'version': '0.9', 'created': 9}]})
    with sqlite3.connect(path) as conn:
        for migration in MIGRATIONS[:version]:
            conn.executescript(migration)
        conn.execute(f'PRAGMA user_version={version}')
        if version:
            record = asdict(entry)
            record['metadata'] = json.dumps(entry.metadata)
            record['backup_info'] = json.dumps(entry.backup_info)
            conn.execute(f"INSERT INTO apps ({','.join(record)}) VALUES ({','.join('?' for _ in record)})",
                         list(record.values()))
        if version >= 2:
            conn.executemany('INSERT INTO settings VALUES (?, ?)',
                             [('run_in_background', '1'), ('backup_keep', '0'),
                              ('tray_favorites', '["legacy-id"]'), ('custom_future_setting', 'preserve')])
    for _ in range(2):  # migration and a normal subsequent restart
        db = Database(path)
        try:
            assert db._conn.execute('PRAGMA user_version').fetchone()[0] == len(MIGRATIONS)
            assert db.list_all() == ([entry] if version else [])
            if version >= 2:
                assert AppSettings(db).run_in_background
                assert TrayShortcuts(db).favorites == [entry.id]
                assert db.get_setting('backup_keep') == '0'
                assert db.get_setting('custom_future_setting') == 'preserve'
            else:
                assert AppSettings(db).auto_check
        finally:
            db.close()


def test_discovery_update_restart_rollback_storage_and_transfer(service, tmp_path, monkeypatch):
    root = tmp_path / 'applications'
    root.mkdir()
    target = script(root / 'Example-1.0.sh')
    old = target.read_bytes()
    found = scan([str(root)])
    assert not found.errors and len(found.candidates) == 1
    service.desktop = DesktopService(tmp_path / 'menus')
    entry = import_candidate(service, found.candidates[0], integrate_desktop=True)
    entry = service.update_application(entry.id, github_repo='https://codeberg.org/o/r',
                                       category='Work', menu_category='Development', env_vars={'MODE': 'quiet'})
    shortcuts = TrayShortcuts(service.db)
    shortcuts.set_favorite(entry.id, True)
    shortcuts.launched(entry.id)
    settings = AppSettings(service.db)
    settings.run_in_background = True
    BackupService(service).set_retention(0)
    new = b'#!/bin/sh\necho upgraded\n'
    asset = Asset('Example-2.0-linux-x86_64', 'https://codeberg.org/o/r/releases/download/v2.0/tool', len(new),
                  'sha256:' + hashlib.sha256(new).hexdigest())
    release = Release('v2.0', name='Version two', body='Useful release notes', assets=[asset])

    class Client:
        def releases(self, owner, name):
            assert (owner, name) == ('o', 'r')
            return [release]

    outcome = check_for_update(repo_url=entry.github_repo, installed_version=entry.installed_version,
                               current_filename=target.name, app_name=entry.name,
                               format_id=entry.format, client=Client())
    assert outcome.status is UpdateStatus.UPDATE_AVAILABLE
    updates = UpdateService(service)
    updates.apply_check(entry.id, outcome)
    updates.mark_notified(entry.id)
    monkeypatch.setattr(installer, '_open', lambda url, timeout=30: Response(new))
    result = installer.install_update(target, outcome.asset, outcome.release_assets,
                                      old_version=entry.installed_version, format_id=entry.format)
    updates.apply_install(entry.id, result, outcome.tag)
    restored = reopen(service)
    try:
        saved = restored.get(entry.id)
        assert saved.installed_version == '2.0' and saved.update_status is UpdateStatus.UP_TO_DATE
        assert saved.metadata['last_install']['checksum'] == 'verified (sha256)'
        assert cached_notes(saved)['body'] == release.body
        assert not UpdateService.should_notify(saved)
        assert TrayShortcuts(restored.db).favorites == [entry.id]
        assert TrayShortcuts(restored.db).recent == [entry.id]
        assert AppSettings(restored.db).run_in_background
        details = inspect_details(saved)
        storage = scan_storage([saved], threading.Event())
        assert details.size == storage.application_size == len(new)
        assert details.backup_size == storage.backup_size == len(old)
        assert details.backup_count == storage.backup_count == 1
        assert len(scan([str(root)], registered=[saved.path]).candidates) == 1
        assert scan([str(root)], registered=[saved.path]).candidates[0].registered
        menu = restored.desktop.entry_path(entry.id)
        menu.unlink()
        assert restored.sync_desktop_entries().repaired
        assert 'MODE=quiet' in menu.read_text()
        backup = BackupService(restored).list_backups(entry.id)[0]
        rolled = BackupService(restored).rollback(entry.id, backup.path)
        assert rolled.restored_version == '1.0' and target.read_bytes() == old
        assert rolled.entry.metadata['last_rollback']['from'] == '2.0'
        restored = reopen(restored)
        saved = restored.get(entry.id)
        assert saved.installed_version == '1.0' and saved.metadata['last_rollback']['to'] == '1.0'
        assert saved.github_repo == entry.github_repo and saved.metadata['category'] == 'Work'
        storage = scan_storage([saved], threading.Event())
        assert storage.backup_size == len(new)
        unrelated = root / 'unrelated.txt'
        unrelated.write_text('Keep me')
        cleanup = cleanup_backups([(saved, storage.apps[0].backups[0])], [saved.path], threading.Event())
        assert len(cleanup.removed) == 1 and not cleanup.errors
        assert unrelated.read_text() == 'Keep me' and target.read_bytes() == old
        destination = tmp_path / 'export.json'
        export_library([saved], destination, include_environment=True)
        target.rename(root / 'moved.sh')
        imported_db = Database(tmp_path / 'imported.db')
        try:
            imported = LibraryService(imported_db, restored.icons_dir,
                                      desktop=DesktopService(tmp_path / 'imported-menus'))
            candidate = preview_import(read_export(destination), [])[0]
            prepared = prepare_import(candidate, [], imported.icons_dir, environment=True)
            copied = imported.import_configuration(prepared)
            assert copied.github_repo == saved.github_repo
            assert copied.metadata['env_vars'] == {'MODE': 'quiet'}
            assert copied.metadata['category'] == 'Work'
            assert inspect_details(copied).state == 'File missing'
            linked = imported.update_application(copied.id, path=str(root / 'moved.sh'))
            assert inspect_details(linked).state == 'Ready'
            assert str(root / 'moved.sh') in imported.desktop.entry_path(linked.id).read_text()
        finally:
            imported_db.close()
    finally:
        restored.db.close()


@pytest.mark.parametrize('failure', ['network', 'truncated', 'checksum', 'invalid', 'cancel', 'replace'])
def test_failed_install_preserves_app_backups_and_closes_temp(tmp_path, monkeypatch, failure):
    target = script(tmp_path / 'tool')
    old = target.read_bytes()
    body = b'#!/bin/sh\necho new version\n'
    cancel = threading.Event()
    asset = dict(name='tool', url='https://example.org/tool', size=len(body),
                 digest='sha256:' + hashlib.sha256(body).hexdigest())
    if failure == 'checksum':
        asset['digest'] = 'sha256:' + '0' * 64
    if failure == 'invalid':
        body = b'<html>this is not an executable</html>'
    if failure == 'cancel':
        cancel.set()
    response = Response(body, len(body) + 10 if failure == 'truncated' else None)

    def open_response(url, timeout=30):
        if failure == 'network':
            raise urllib.error.URLError('offline')
        return response

    monkeypatch.setattr(installer, '_open', open_response)
    opened = []
    original_mkstemp = installer.tempfile.mkstemp

    def record_fd(*args, **kwargs):
        fd, name = original_mkstemp(*args, **kwargs)
        opened.append(fd)
        return fd, name

    monkeypatch.setattr(installer.tempfile, 'mkstemp', record_fd)
    if failure == 'replace':
        def fail_replace(*args):
            raise PermissionError('cannot replace')
        monkeypatch.setattr(installer.os, 'replace', fail_replace)
    with pytest.raises(installer.InstallError):
        installer.install_update(target, asset, [], old_version='1.0',
                                 cancel=cancel, format_id='executable')
    assert target.read_bytes() == old and target.stat().st_mode & 0o777 == 0o750
    assert not list(tmp_path.glob('.*.part'))
    assert not list(installer.backup_dir_for(target).glob('*'))
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_hidden_window_checks_and_updates_batch_through_workers(service, tmp_path, monkeypatch, qapp):
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QMessageBox
    import appforge.core.updates.checker as checker
    import appforge.ui.main_window as main_window
    from test_gui import wait_for

    monkeypatch.setattr(main_window, 'tray_available', lambda: True)
    entries = [service.add_application(str(script(tmp_path / f'Tool{i}-1.0.sh')),
                                        github_repo=f'owner/tool{i}') for i in range(2)]
    body = b'#!/bin/sh\necho updated from background worker\n'

    class Client:
        def releases(self, owner, name):
            return [Release('v2.0', body='## Updated', assets=[
                Asset(f'{name}-2.0-linux-x86_64', f'https://example.org/{name}', len(body),
                      'sha256:' + hashlib.sha256(body).hexdigest())])]

    monkeypatch.setattr(checker, 'client_for', lambda ref, token: Client())
    monkeypatch.setattr(installer, '_open', lambda url, timeout=30: Response(body))
    window = main_window.MainWindow(service, tray_icon=QIcon())
    window.settings.run_in_background = True
    window.apply_settings()
    notices = []
    monkeypatch.setattr(window, '_notify', lambda *args: notices.append(args))

    def approve(box):
        box._test_clicked = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.AcceptRole)

    monkeypatch.setattr(QMessageBox, 'exec', approve)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda box: box._test_clicked)
    try:
        assert not window.isVisible()
        window.tray.checkRequested.emit()
        assert wait_for(qapp, lambda: not window._busy)
        assert all(service.get(e.id).update_status is UpdateStatus.UPDATE_AVAILABLE for e in entries)
        assert '2 application updates' in window.tray.status_action.text()
        notices.clear()
        window.tray.updateAllRequested.emit()
        # Tray opens the existing confirmation. Closing then leaves the batch
        # running in the background through the same workers.
        assert window.isVisible()
        assert window._hide_to_tray()
        assert wait_for(qapp, lambda: not window._busy and window._batch is None)
        for entry in entries:
            saved = service.get(entry.id)
            assert saved.installed_version == '2.0'
            assert Path(saved.path).read_bytes() == body
            assert inspect_details(saved).backup_count == 1
            assert cached_notes(saved)['body'] == '## Updated'
        assert '0 application updates' in window.tray.status_action.text()
        assert len(notices) == 1 and notices[0][0] == 'AppForge updates finished'
        assert not window.isVisible()
    finally:
        window._quitting = True
        window.close()
        window.check_pool.waitForDone()
        window.install_pool.waitForDone()
        window.deleteLater()
        qapp.processEvents()


def test_drag_drop_routes_only_local_file_to_existing_add_flow(service, tmp_path, monkeypatch, qapp):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from appforge.ui.main_window import MainWindow
    from test_gui import wait_for

    window = MainWindow(service)
    added = []
    monkeypatch.setattr(window, 'add_application', added.append)
    data = QMimeData()
    local = tmp_path / 'Example.AppImage'
    data.setUrls([QUrl('https://example.org/remote.AppImage'), QUrl.fromLocalFile(str(local))])
    try:
        drag = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(drag)
        assert drag.isAccepted()
        drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
        window.dropEvent(drop)
        assert drop.isAccepted()
        assert wait_for(qapp, lambda: added == [str(local)])
        assert not service.list_applications()  # registration still requires the add dialog
    finally:
        window._quitting = True
        window.close()
        window.deleteLater()
        qapp.processEvents()
