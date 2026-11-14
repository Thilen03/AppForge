"""Details behavior using scripts, without AppImage build fixtures or network access."""
from copy import deepcopy
from pathlib import Path
import threading

from test_gui import qapp, wait_for  # noqa: F401
from appforge.core.details import inspect_details
from appforge.core.models import UpdateStatus
from appforge.core.updates.installer import backup_dir_for
from appforge.ui.main_window import MainWindow


def add_script(service, tmp_path):
    path = tmp_path / 'Example-1.0.sh'
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    return service.add_application(str(path), name='Example', github_repo='owner/repo')


def test_read_only_snapshot_sizes_and_missing(service, tmp_path):
    entry = add_script(service, tmp_path)
    folder = backup_dir_for(Path(entry.path))
    folder.mkdir()
    backup = folder / 'Example-0.9.bak'
    backup.write_bytes(b'old')
    snapshot = deepcopy(entry)
    result = inspect_details(entry)
    assert entry == snapshot
    assert result.size == 17
    assert result.state == 'Ready'
    assert result.backup_count == 1 and result.backup_size == 3
    assert result.backup_date
    assert service.get(entry.id).backup_info == {}
    Path(entry.path).unlink()
    assert inspect_details(entry).state == 'File missing'


def test_permission_failure_is_unavailable(service, tmp_path, monkeypatch):
    entry = add_script(service, tmp_path)
    import appforge.core.details as details
    monkeypatch.setattr(details, 'scan_backup_records', lambda _: (_ for _ in ()).throw(PermissionError()))
    result = inspect_details(entry)
    assert result.backup_count is None and result.backup_error


def test_details_menu_refresh_actions_and_removed(qapp, service, tmp_path, monkeypatch):
    entry = add_script(service, tmp_path)
    win = MainWindow(service)
    card = win._card(entry.id)
    menu = card._build_menu()
    next(a for a in menu.actions() if a.text() == 'Details…').trigger()
    dialog = win._details[entry.id]
    assert wait_for(qapp, lambda: dialog.fields['File status'].text() == 'Ready')
    assert dialog.fields['Format'].text() == 'Script'
    assert dialog.fields['Last checked'].text() == 'Never checked'
    assert dialog.buttons['launch'].isEnabled()
    assert not dialog.buttons['update'].isEnabled()
    calls = []
    for action, method in [('launch', 'launch'), ('check', 'check_updates'), ('folder', 'show_in_file_manager'),
                           ('edit', 'edit_application'), ('backups', 'show_backups')]:
        monkeypatch.setattr(win, method, lambda *args, key=action, **kw: calls.append((key, args)))
        dialog.buttons[action].click()
    assert [c[0] for c in calls] == ['launch', 'check', 'folder', 'edit', 'backups']
    current = service.get(entry.id)
    current.name = '<Renamed>'
    current.installed_version = '2.0'
    current.latest_version = '3.0'
    current.update_status = UpdateStatus.UPDATE_AVAILABLE
    current.metadata['update'] = {'asset': {'name': 'Example.sh'}, 'release_url': 'https://github.com/owner/repo/releases/tag/v3'}
    service.db.update(current)
    win.reload()
    assert wait_for(qapp, lambda: dialog.buttons['update'].isEnabled())
    assert dialog.name.text() == '<Renamed>'
    assert dialog.fields['Installed version'].text() == '2.0'
    assert dialog.buttons['release'].isEnabled()
    for action, method in [('update', 'start_update'), ('release', 'open_release_page')]:
        monkeypatch.setattr(win, method, lambda *args, key=action: calls.append((key, args)))
        dialog.buttons[action].click()
    assert [c[0] for c in calls][-2:] == ['update', 'release']
    win.show_details(entry.id)
    assert win._details[entry.id] is dialog
    win._set_busy(entry.id, 'Checking for updates…')
    assert not dialog.buttons['launch'].isEnabled()
    assert not dialog.buttons['backups'].isEnabled()
    win._set_busy(entry.id, None)
    # A rollback or relocation changes the same record, so the existing reload path refreshes it.
    current = service.get(entry.id)
    current.installed_version = '0.9'
    current.path = str(tmp_path / 'moved.sh')
    service.db.update(current)
    win.reload()
    assert wait_for(qapp, lambda: dialog.fields['File status'].text() == 'File missing')
    assert dialog.fields['Installed version'].text() == '0.9'
    assert not dialog.buttons['launch'].isEnabled()
    assert dialog.buttons['locate'].isVisible()
    service.remove_application(entry.id)
    win.reload()
    assert entry.id not in win._details
    win._quitting = True
    win.close()


def test_worker_uses_no_sqlite_and_ignores_stale_results(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.details_dialog as ui
    entry = add_script(service, tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ui.inspect_details
    threads = []
    def blocked(snapshot):
        threads.append(threading.get_ident())
        entered.set()
        release.wait(5)
        return original(snapshot)
    monkeypatch.setattr(ui, 'inspect_details', blocked)
    win = MainWindow(service)
    win.show_details(entry.id)
    dialog = win._details[entry.id]
    assert wait_for(qapp, entered.is_set)
    current = service.get(entry.id)
    current.path = str(tmp_path / 'missing.sh')
    service.db.update(current)
    dialog.refresh()
    release.set()
    assert wait_for(qapp, lambda: dialog.fields['File status'].text() == 'File missing')
    assert all(t != threading.get_ident() for t in threads)
    dialog.close()
    assert not dialog.timer.isActive()
    win._quitting = True
    win.close()


def test_details_follow_update_install_and_real_rollback(qapp, service, tmp_path):
    from appforge.core.updates.checker import CheckOutcome
    from appforge.core.updates.installer import InstallResult
    entry = add_script(service, tmp_path)
    win = MainWindow(service)
    win.show_details(entry.id)
    dialog = win._details[entry.id]
    assert wait_for(qapp, lambda: dialog.fields['File status'].text() == 'Ready')
    win.updates.apply_check(entry.id, CheckOutcome(
        UpdateStatus.UPDATE_AVAILABLE, latest_version='2.0', tag='v2.0',
        asset={'name': 'Example.sh'}, release_url='https://github.com/owner/repo/releases/tag/v2.0'))
    win._refresh_card(entry.id)
    assert wait_for(qapp, lambda: dialog.buttons['update'].isEnabled())
    folder = backup_dir_for(Path(entry.path))
    folder.mkdir()
    backup = folder / 'Example-1.0.bak'
    original = Path(entry.path).read_bytes() + b'# padding\n' * 200
    backup.write_bytes(original)
    Path(entry.path).write_text('#!/bin/sh\necho updated\n')
    # Installation completion goes through the existing service, without a network download.
    result = InstallResult(entry.path, str(backup), 'not available', Path(entry.path).stat().st_size)
    win.updates.apply_install(entry.id, result, 'v2.0')
    win.reload()
    assert wait_for(qapp, lambda: dialog.fields['Backup count'].text() == '1')
    assert dialog.fields['Installed version'].text() == '2.0'
    win.updates.backups.rollback(entry.id, str(backup))
    win.reload()
    assert wait_for(qapp, lambda: dialog.fields['File size'].text() == f'{len(original):,} bytes')
    assert dialog.fields['Installed version'].text() == '1.0'
    assert dialog.fields['Backup count'].text() == '1'
    win._quitting = True
    win.close()


def test_close_during_scan_does_not_touch_closed_database(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.details_dialog as ui
    from PySide6.QtCore import QThreadPool
    entry = add_script(service, tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ui.inspect_details
    def blocked(snapshot):
        entered.set()
        release.wait(5)
        return original(snapshot)
    monkeypatch.setattr(ui, 'inspect_details', blocked)
    win = MainWindow(service)
    win.show_details(entry.id)
    assert wait_for(qapp, entered.is_set)
    win._quitting = True
    win.close()
    qapp.processEvents()
    service.db.close()
    release.set()
    assert QThreadPool.globalInstance().waitForDone(2000)
    qapp.processEvents()


def test_missing_metadata_and_appimage_elf_formats(qapp, service, tmp_path):
    from appforge.core.models import AppEntry
    for format_id, metadata, expected in (
        ('appimage', {}, 'AppImage'),
        ('executable', {'executable_kind': 'elf'}, 'ELF binary'),
    ):
        entry = AppEntry(name=expected, path=str(tmp_path / expected), format=format_id,
                         metadata=metadata)
        service.db.add(entry)
        win = MainWindow(service)
        win.show_details(entry.id)
        dialog = win._details[entry.id]
        assert wait_for(qapp, lambda: dialog.fields['File status'].text() == 'File missing')
        assert dialog.fields['Format'].text() == expected
        assert dialog.fields['Description'].text() == 'No description available'
        assert dialog.fields['Installed version'].text() == 'Unknown'
        assert dialog.fields['Repository'].text() == 'Not linked'
        assert not dialog.buttons['check'].isEnabled()
        assert not dialog.buttons['release'].isEnabled()
        win._quitting = True
        win.close()
        qapp.processEvents()
