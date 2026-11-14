"""Storage arithmetic, destructive boundaries and asynchronous UI integration."""
from copy import deepcopy
from pathlib import Path
from threading import Event, get_ident
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from test_gui import qapp, wait_for  # noqa: F401
from appforge.core.backups import BackupService
from appforge.core.backups.files import delete_managed_backup
from appforge.core.backups.service import scan_backup_records
from appforge.core.models import AppEntry
from appforge.core.storage import cleanup_backups, scan_storage
from appforge.core.updates.installer import backup_dir_for
from appforge.ui.storage_dialog import StorageDialog


def make_app(service, tmp_path, name='Editor', size=100):
    path = tmp_path / name
    path.write_bytes(b'x' * size)
    entry = AppEntry(name=name, path=str(path), format='executable')
    service.db.add(entry)
    return entry


def add_backup(entry, version, size=30):
    folder = backup_dir_for(Path(entry.path))
    folder.mkdir(exist_ok=True)
    path = folder / f'{Path(entry.path).name}-{version}.bak'
    path.write_bytes(b'b' * size)
    os.utime(path, (version * 100, version * 100))
    return path


def scan(entries, cancel=None):
    return scan_storage(deepcopy(entries), cancel or Event())


def test_totals_order_missing_and_read_only(service, tmp_path):
    a = make_app(service, tmp_path)
    b = make_app(service, tmp_path, 'Other', 200)
    add_backup(a, 1, 20)
    add_backup(a, 2, 40)
    before = deepcopy(service.list_applications())
    progress = []
    result = scan_storage(before, Event(), lambda *args: progress.append(args))
    assert result.application_size == 300 and result.backup_size == 60
    assert result.backup_count == 2 and result.apps[0].total == 160
    assert [r.version for r in result.apps[0].backups] == ['2', '1']
    assert progress == [(1, 2), (2, 2)]
    assert service.list_applications() == before
    Path(b.path).unlink()
    result = scan([a, b])
    assert result.application_size == 100 and result.apps[1].notices


def test_cancel_and_empty(service, tmp_path):
    a = make_app(service, tmp_path)
    b = make_app(service, tmp_path, 'Other')
    stop = Event()
    result = scan_storage([a, b], stop, lambda *_: stop.set())
    assert result.cancelled and len(result.apps) == 1
    assert scan([]).application_size == 0


@pytest.mark.parametrize('kind', ['file_link', 'folder_link', 'ancestor_link', 'outside', 'other_app'])
def test_reject_unmanaged_paths_and_symlinks(service, tmp_path, kind):
    a = make_app(service, tmp_path)
    victim = tmp_path / 'important.bak'
    victim.write_bytes(b'valuable')
    folder = backup_dir_for(Path(a.path))
    folder.mkdir()
    path = folder / 'old.bak'
    if kind == 'file_link':
        path.symlink_to(victim)
    elif kind == 'folder_link':
        folder.rmdir()
        folder.symlink_to(tmp_path, target_is_directory=True)
        path = folder / victim.name
    elif kind == 'ancestor_link':
        alias = tmp_path / 'alias'
        alias.symlink_to(tmp_path, target_is_directory=True)
        a.path = str(alias / 'Editor')
        path = backup_dir_for(Path(a.path)) / 'old.bak'
        (folder / 'old.bak').write_bytes(b'valuable')
    elif kind == 'other_app':
        other = make_app(service, tmp_path, 'Other')
        path = add_backup(other, 1)
    else:
        path = victim
    a.backup_info = {'backups': [{'file': str(path), 'version': '1', 'created': 1}]}
    with pytest.raises((OSError, ValueError)):
        delete_managed_backup(a, str(path), [a.path])
    assert victim.read_bytes() == b'valuable' and path.exists()
    result = scan([a])
    assert result.backup_count == 0


def test_changed_file_rejected_and_partial_cleanup(service, tmp_path):
    a = make_app(service, tmp_path)
    one, two = add_backup(a, 1), add_backup(a, 2)
    app = scan([a]).apps[0]
    one.write_bytes(b'changed')
    result = cleanup_backups([(a, b) for b in app.backups], [a.path], Event())
    assert result.removed == [(a.id, str(two))] and len(result.errors) == 1
    assert one.read_bytes() == b'changed' and Path(a.path).exists()


def test_protect_all_current_files_and_hardlinks(service, tmp_path):
    a = make_app(service, tmp_path)
    path = add_backup(a, 1)
    path.unlink()
    os.link(a.path, path)
    app = scan([a]).apps[0]
    assert app.backups[0].reclaimable == 0
    result = cleanup_backups([(a, app.backups[0])], [a.path], Event())
    assert not result.removed and path.exists()
    # A separate registered application placed inside the backup directory is protected too.
    b = AppEntry(name='Other', path=str(path))
    service.db.add(b)
    with pytest.raises(Exception):
        BackupService(service).delete_backup(a.id, str(path))
    assert path.exists()


def test_disappearing_and_permission_error(service, tmp_path, monkeypatch):
    a = make_app(service, tmp_path)
    path = add_backup(a, 1)
    app = scan([a]).apps[0]
    path.unlink()
    result = cleanup_backups([(a, app.backups[0])], [a.path], Event())
    assert result.errors and not result.removed
    import appforge.core.storage as storage
    monkeypatch.setattr(storage, 'scan_backup_records', lambda *a, **k: (_ for _ in ()).throw(PermissionError('denied')))
    assert scan([a]).apps[0].notices


def test_cleanup_cancel_stops_between_files(service, tmp_path):
    a = make_app(service, tmp_path)
    for i in range(4):
        add_backup(a, i)
    app = scan([a]).apps[0]
    stop = Event()
    result = cleanup_backups([(a, b) for b in app.backups], [a.path], stop, lambda *_: stop.set())
    assert result.cancelled and len(result.removed) == 1
    assert len(scan_backup_records(a)) == 3


def test_dialog_sort_filter_retention_and_workers(qapp, service, tmp_path, monkeypatch):
    a = make_app(service, tmp_path)
    make_app(service, tmp_path, 'Large', 2048)
    for i in range(5):
        add_backup(a, i)
    backups = BackupService(service)
    backups.set_retention(2)
    main_thread = get_ident()
    reads = []
    original = service.list_applications
    def read():
        reads.append(get_ident())
        return original()
    monkeypatch.setattr(service, 'list_applications', read)
    import appforge.ui.storage_dialog as ui
    worker_threads = []
    scanner = ui.scan_storage
    def background(*args):
        worker_threads.append(get_ident())
        return scanner(*args)
    monkeypatch.setattr(ui, 'scan_storage', background)
    dialog = StorageDialog(service, backups, {})
    dialog.show()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert all(t == main_thread for t in reads) and worker_threads[0] != main_thread
    assert dialog.apps.topLevelItem(0).text(0) == 'Large'
    dialog.only_backups.setChecked(True)
    assert dialog.apps.topLevelItemCount() == 1
    assert dialog.files.topLevelItemCount() == 5
    dialog._select_older()
    assert len(dialog._selected()) == 3
    assert dialog.delete_btn.isEnabled()
    assert '90 B' in dialog.savings.text()
    backups.set_retention(0)
    dialog._select_older()
    assert not dialog._selected()
    assert dialog.chart.application_size == 2148
    dialog.close()


def test_ui_confirmation_cleanup_and_main_thread_write(qapp, service, tmp_path, monkeypatch):
    a = make_app(service, tmp_path)
    backup = add_backup(a, 1)
    a.backup_info = {'backups': [{'file': str(backup), 'version': '1', 'created': 100}]}
    service.db.update(a)
    dialog = StorageDialog(service, BackupService(service), {})
    assert wait_for(qapp, lambda: dialog._job is None)
    dialog._check_backups(True)
    # Cancel requires no file work.
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: None)
    dialog._delete()
    assert backup.exists()
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda box: next(b for b in box.buttons() if b.text() == 'Delete backups'))
    owner = get_ident()
    writes = []
    original = service.db.update
    def write(entry):
        writes.append(get_ident())
        return original(entry)
    monkeypatch.setattr(service.db, 'update', write)
    dialog._delete()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert not backup.exists() and Path(a.path).exists()
    assert writes and all(t == owner for t in writes)
    assert service.get(a.id).backup_info['backups'] == []
    assert dialog.snapshot.backup_count == 0
    dialog.close()


def test_close_cancels_and_waits(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.storage_dialog as ui
    import time
    make_app(service, tmp_path)
    scanner = ui.scan_storage
    def delayed(entries, cancel, progress):
        while not cancel.is_set():
            time.sleep(.005)
        return scanner(entries, cancel, progress)
    monkeypatch.setattr(ui, 'scan_storage', delayed)
    dialog = StorageDialog(service, BackupService(service), {})
    dialog.show()
    dialog.reject()
    assert dialog._pending_close is not None
    assert wait_for(qapp, lambda: dialog._job is None)
    assert not dialog.isVisible()


def test_main_window_entry_point(qapp, service, monkeypatch):
    from appforge.ui.main_window import MainWindow
    import appforge.ui.storage_dialog as ui
    calls = []
    monkeypatch.setattr(ui.StorageDialog, 'exec', lambda dialog: calls.append(dialog.windowTitle()))
    win = MainWindow(service)
    win.storage_btn.click()
    assert calls == ['Storage · AppForge']
    assert wait_for(qapp, lambda: not any(isinstance(w, StorageDialog) and w._job for w in qapp.topLevelWidgets()))
    win.close()


def test_symlink_swap_after_preview_is_rejected(service, tmp_path):
    a = make_app(service, tmp_path)
    backup = add_backup(a, 1)
    row = scan([a]).apps[0].backups[0]
    backup.unlink()
    backup.symlink_to(a.path)
    result = cleanup_backups([(a, row)], [a.path], Event())
    assert result.errors and not result.removed
    assert backup.is_symlink() and Path(a.path).exists()


def test_permission_failure_continues_cleanup(service, tmp_path, monkeypatch):
    import appforge.core.backups.files as files
    a = make_app(service, tmp_path)
    one, two = add_backup(a, 1), add_backup(a, 2)
    rows = scan([a]).apps[0].backups
    unlink = files.os.unlink
    def denied(name, **kwargs):
        if name == one.name:
            raise PermissionError('read-only backup')
        return unlink(name, **kwargs)
    monkeypatch.setattr(files.os, 'unlink', denied)
    result = cleanup_backups([(a, b) for b in rows], [a.path], Event())
    assert len(result.errors) == 1 and result.removed == [(a.id, str(two))]
    assert one.exists()


def test_busy_or_changed_app_after_confirmation_is_rejected(qapp, service, tmp_path, monkeypatch):
    a = make_app(service, tmp_path)
    path = add_backup(a, 1)
    busy = {}
    dialog = StorageDialog(service, BackupService(service), busy)
    assert wait_for(qapp, lambda: dialog._job is None)
    dialog._check_backups(True)
    def confirm(box):
        busy[a.id] = ('Installing', 20)
    monkeypatch.setattr(QMessageBox, 'exec', confirm)
    monkeypatch.setattr(QMessageBox, 'clickedButton',
                        lambda box: next(b for b in box.buttons() if b.text() == 'Delete backups'))
    dialog._delete()
    assert path.exists() and dialog._job is None
    assert 'busy' in dialog.notice.text()
    busy.clear()
    def change(box):
        entry = service.get(a.id)
        entry.name = 'Renamed'
        service.db.update(entry)
    monkeypatch.setattr(QMessageBox, 'exec', change)
    dialog._delete()
    assert path.exists() and 'changed' in dialog.notice.text()
    dialog.close()


def test_existing_backup_dialog_handles_unavailable_folder(qapp, service, tmp_path):
    from appforge.ui.backups_dialog import BackupsDialog
    a = make_app(service, tmp_path)
    folder = backup_dir_for(Path(a.path))
    folder.symlink_to(tmp_path, target_is_directory=True)
    dialog = BackupsDialog(BackupService(service), a)
    assert 'unavailable' in dialog.notice.text()
    dialog.keep.setValue(1)
    dialog._apply_retention()
    assert service.get(a.id).backup_info == {}
    dialog.close()
