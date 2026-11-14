"""Portable configuration, strict validation, read-only preview and GUI thread ownership."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import threading

import pytest
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from appforge.core.database import Database
from appforge.core.library import LibraryService
from appforge.core.library_transfer import (
    FORMAT, SCHEMA_VERSION, ImportCandidate, TransferCancelled, TransferError,
    export_library, read_export, preview_import, prepare_import, validate_record,
)
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.settings import AppSettings
from appforge.ui.library_transfer_dialog import LibraryTransferDialog
from appforge.ui.settings_dialog import SettingsDialog
from test_details import add_script
from test_gui import qapp, wait_for  # noqa: F401


def record(path='/missing/Example.AppImage', id='portable-id', **kwargs):
    return dict(id=id, name='Example', path=path, format='appimage', installed_version='2.0',
                description='A portable application', github_repo='owner/repo', added_at=1234,
                metadata={'category': 'Games', 'include_prereleases': True, 'asset_pattern': 'Example-*.AppImage',
                          'menu_category': 'Game', 'desktop_entry': True}, icon=None, **kwargs)


def write_export(tmp_path, records, **kwargs):
    destination = tmp_path / 'library.json'
    destination.write_text(json.dumps(dict(format=FORMAT, schema_version=SCHEMA_VERSION,
                                           appforge_version='0.5.7', applications=records, **kwargs)))
    return destination


def another_service(tmp_path):
    directory = tmp_path / 'target'
    directory.mkdir()
    icons = directory / 'icons'
    icons.mkdir()
    return LibraryService(Database(directory / 'library.db'), icons)


def test_roundtrip_all_configuration_icons_and_missing(service, tmp_path):
    entry = add_script(service, tmp_path)
    icon = service.icons_dir / 'source.png'
    icon.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7p8AAAAASUVORK5CYII='))
    entry.icon_path = str(icon)
    entry.description = 'Useful description\nwith details'
    entry.installed_version = '1.0'
    entry.metadata.update(category='Custom', categories='Utility;', menu_category='Utility',
                          env_vars={'DISPLAY_STYLE': 'compact', 'API_TOKEN': 'do-not-leak'},
                          include_prereleases=True, asset_pattern='Example-*', custom_icon=True,
                          desktop_entry=True, desktop_exec='Example --untrusted %U',
                          startup_wm_class='Example', generic_name='Editor', installed_version_source='manual',
                          update={'asset': {'url': 'https://secret.example.org/?token=do-not-leak'}},
                          github_token='do-not-leak', arbitrary_secret='do-not-leak')
    entry.backup_info = {'backups': [{'file': '/private/backup'}]}
    service.db.update(entry)
    service.db.set_setting('github_token', 'do-not-leak')
    destination = tmp_path / 'export.json'
    original = Path(entry.path).read_bytes()
    assert export_library(service.list_applications(), destination, protected=[service.db.path]) == []
    text = destination.read_text()
    assert 'do-not-leak' not in text and '/private/backup' not in text
    assert 'env_vars' not in text and 'backup_info' not in text and 'latest_version' not in text
    assert destination.stat().st_mode & 0o777 == 0o600
    records = read_export(destination)
    assert records[0]['metadata']['desktop_exec'] == '%U'
    Path(entry.path).unlink()  # exported configuration remains importable on another machine
    target = another_service(tmp_path)
    try:
        candidate = preview_import(records, [])[0]
        assert 'Missing' in candidate.status
        prepared = prepare_import(candidate, [], target.icons_dir)
        imported = target.import_configuration(prepared)
        assert imported.id == entry.id and imported.name == entry.name
        assert imported.path == entry.path and imported.github_repo == entry.github_repo
        assert imported.installed_version == '1.0' and imported.description == entry.description
        assert imported.added_at == entry.added_at
        assert imported.metadata['include_prereleases'] and imported.metadata['custom_icon']
        assert imported.metadata['asset_pattern'] == 'Example-*'
        assert imported.metadata['category'] == 'Custom'
        assert imported.metadata['menu_category'] == 'Utility'
        assert Path(imported.icon_path).read_bytes() == icon.read_bytes()
        assert imported.icon_path != entry.icon_path
        assert imported.backup_info == {} and imported.latest_version is None
        assert imported.update_status is UpdateStatus.UNAVAILABLE
        assert target.desktop.entry_path(imported.id).exists()
        # Reconnect with the existing library method; no file inspection ever runs it.
        restored = tmp_path / 'restored.sh'
        restored.write_bytes(original)
        restored.chmod(0o755)
        updated = target.update_application(imported.id, path=str(restored))
        assert updated.path == str(restored)
    finally:
        target.db.close()


def test_environment_requires_both_opt_ins(service, tmp_path):
    entry = add_script(service, tmp_path)
    entry.metadata['env_vars'] = {'HELLO': 'world', 'API_TOKEN': 'sensitive'}
    path = tmp_path / 'with-env.json'
    export_library([entry], path, include_environment=True)
    candidate = preview_import(read_export(path), [])[0]
    assert candidate.record['metadata']['env_vars']['API_TOKEN'] == 'sensitive'
    assert 'env_vars' not in prepare_import(candidate, [], service.icons_dir).record['metadata']
    assert prepare_import(candidate, [], service.icons_dir, environment=True).record['metadata']['env_vars'] == entry.metadata['env_vars']


@pytest.mark.parametrize('field,value', [
    ('id', '../escape'), ('id', ''), ('id', 'a' * 129), ('name', ''), ('name', 42),
    ('path', '~/Applications/X'), ('path', '/tmp/\0evil'), ('format', 'unknown'),
    ('installed_version', []), ('description', {'bad': True}), ('github_repo', 'https://'),
    ('added_at', True), ('added_at', -1), ('added_at', float('nan')),
    ('metadata', {'update': {'asset': {'url': 'https://evil'}}}),
    ('metadata', {'include_prereleases': 'yes'}), ('metadata', {'desktop_entry': 1}),
    ('metadata', {'category': 'x' * 41}), ('metadata', {'menu_category': 'Invalid'}),
    ('metadata', {'env_vars': {'bad name': 'x'}}), ('metadata', {'env_vars': {'KEY': 42}}),
    ('metadata', {'env_vars': {'KEY': 'a\nb'}}), ('metadata', {'asset_pattern': []}),
    ('metadata', {'desktop_exec': 'sh -c evil'}), ('metadata', {'executable_kind': 'archive'}),
    ('icon', {'extension': '../../escape', 'data': 'YWJj'}),
    ('icon', {'extension': '.png', 'data': 'not base64!!!'}),
    ('icon', {'extension': '.png', 'data': ''}), ('icon', {'path': '/private/icon.png'}),
])
def test_reject_invalid_records(field, value):
    raw = record()
    raw[field] = value
    with pytest.raises(TransferError):
        validate_record(raw)


@pytest.mark.parametrize('change', ['version', 'bool-version', 'type', 'apps', 'global-token', 'record', 'json', 'duplicate-key', 'deep'])
def test_reject_whole_document_before_any_write(service, tmp_path, change):
    path = write_export(tmp_path, [record(), record(id='other', path='/missing/other')])
    document = json.loads(path.read_text())
    if change == 'version':
        document['schema_version'] = 2
    elif change == 'bool-version':
        document['schema_version'] = True
    elif change == 'type':
        document['format'] = 'some-other-program'
    elif change == 'apps':
        document['applications'] = {}
    elif change == 'global-token':
        document['github_token'] = 'never-import-this'
    elif change == 'record':
        document['applications'][1]['name'] = None
    if change == 'json':
        path.write_text('{broken')
    elif change == 'duplicate-key':
        path.write_text('{"format":"appforge-library", "format":"appforge-library"}')
    elif change == 'deep':
        path.write_text('[' * 2000 + ']' * 2000)
    else:
        path.write_text(json.dumps(document))
    with pytest.raises(TransferError):
        read_export(path)
    assert service.list_applications() == []


def test_size_limits_regular_files_and_icon_errors(service, tmp_path, monkeypatch):
    import appforge.core.library_transfer as core
    path = write_export(tmp_path, [record()])
    monkeypatch.setattr(core, 'MAX_BYTES', 8)
    with pytest.raises(TransferError, match='32 MiB'):
        read_export(path)
    with pytest.raises(TransferError, match='regular'):
        read_export(tmp_path)
    entry = add_script(service, tmp_path)
    old = path.read_bytes()
    with pytest.raises(TransferError, match='32 MiB'):
        export_library([entry], path)
    assert path.read_bytes() == old
    monkeypatch.setattr(core, 'MAX_BYTES', 32 * 1024 * 1024)
    entry.icon_path = str(tmp_path / 'gone.png')
    entry.metadata['custom_icon'] = True
    warnings = export_library([entry], path)
    assert warnings and read_export(path)[0]['icon'] is None
    assert 'custom_icon' not in read_export(path)[0]['metadata']


def test_duplicate_paths_aliases_hardlinks_and_same_names(service, tmp_path):
    entry = add_script(service, tmp_path)
    link = tmp_path / 'alias.sh'
    link.symlink_to(entry.path)
    hard = tmp_path / 'hard.sh'
    os.link(entry.path, hard)
    rows = []
    for i, path in enumerate([entry.path, str(link), str(hard), str(tmp_path / 'missing.sh')]):
        raw = record(path=path, id=f'id{i}')
        raw['format'] = 'executable'
        raw['name'] = entry.name
        rows.append(raw)
    candidates = preview_import(rows, [entry])
    assert [c.duplicate for c in candidates] == [True, True, True, False]
    assert candidates[-1].same_name and 'separate' in candidates[-1].status
    internal = preview_import([rows[0], deepcopy(rows[0])], [])
    assert not internal[0].duplicate and internal[1].duplicate


def test_conflicting_id_explicit_new_id_preserves_existing(service, tmp_path):
    entry = add_script(service, tmp_path)
    original = deepcopy(entry)
    candidate = preview_import([record(id=entry.id)], [entry])[0]
    assert candidate.id_conflict and not candidate.duplicate
    with pytest.raises(TransferError, match='ID'):
        prepare_import(candidate, [entry], service.icons_dir)
    prepared = prepare_import(candidate, [entry], service.icons_dir, new_ids=True, launchers=False)
    imported = service.import_configuration(prepared)
    assert imported.id != entry.id and imported.id.isalnum()
    assert service.get(entry.id) == original
    assert 'desktop_entry' not in imported.metadata
    with pytest.raises(TransferError, match='Duplicate'):
        prepare_import(candidate, service.list_applications(), service.icons_dir, new_ids=True)


def test_unchanged_preview_and_changed_file_race(service, tmp_path):
    entry = add_script(service, tmp_path)
    raw = record(path=entry.path)
    raw['format'] = 'executable'
    candidate = preview_import([raw], [])[0]
    assert not candidate.invalid_file
    Path(entry.path).write_text('#!/bin/sh\n# changed\n')
    with pytest.raises(TransferError, match='changed'):
        prepare_import(candidate, [], service.icons_dir)
    candidate = preview_import([raw], [])[0]
    Path(entry.path).unlink()
    prepared = prepare_import(candidate, [], service.icons_dir)
    assert prepared.missing  # disappearing files preserve their configuration
    Path(entry.path).write_text('Not executable data')
    assert preview_import([raw], [])[0].invalid_file


def test_export_atomic_failures_protection_and_cancel(service, tmp_path, monkeypatch):
    import appforge.core.library_transfer as core
    entry = add_script(service, tmp_path)
    path = tmp_path / 'export.json'
    path.write_text('keep this')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TransferCancelled):
        export_library([entry], path, cancel=cancel)
    assert path.read_text() == 'keep this'
    with pytest.raises(TransferError, match='cannot replace'):
        export_library([entry], entry.path)
    with pytest.raises(TransferError, match='cannot replace'):
        export_library([entry], service.db.path, protected=[service.db.path])
    alias = tmp_path / 'alias.json'
    alias.symlink_to(path)
    with pytest.raises(TransferError, match='symbolic'):
        export_library([entry], alias)
    monkeypatch.setattr(core.os, 'replace', lambda *args: (_ for _ in ()).throw(PermissionError('read only')))
    with pytest.raises(TransferError, match='save'):
        export_library([entry], path)
    assert path.read_text() == 'keep this'
    assert not list(tmp_path.glob('.appforge-export-*'))


def test_import_registration_rechecks_id_and_path(service, tmp_path):
    candidate = preview_import([record()], [])[0]
    prepared = prepare_import(candidate, [], service.icons_dir)
    service.import_configuration(prepared)
    with pytest.raises(TransferError, match='Duplicate'):
        service.import_configuration(prepared)
    prepared.record['path'] = '/missing/different'
    with pytest.raises(TransferError, match='ID'):
        service.import_configuration(prepared)


def test_launcher_error_preserves_record(service, tmp_path, monkeypatch):
    candidate = preview_import([record()], [])[0]
    prepared = prepare_import(candidate, [], service.icons_dir)
    monkeypatch.setattr(service.desktop, 'write_entry', lambda _: (_ for _ in ()).throw(PermissionError('read only')))
    entry = service.import_configuration(prepared)
    assert service.get(entry.id) and prepared.warnings


def test_settings_actions_and_import_preview_selection(qapp, service, tmp_path, monkeypatch):
    settings = SettingsDialog(AppSettings(service.db), False)
    calls = []
    settings.importRequested.connect(lambda: calls.append('import'))
    settings.exportRequested.connect(lambda: calls.append('export'))
    settings.import_btn.click()
    settings.export_btn.click()
    assert calls == ['import', 'export']
    settings.close()
    existing = add_script(service, tmp_path)
    raw = record(path=existing.path)
    raw['format'] = 'executable'
    path = write_export(tmp_path, [raw, record(id=existing.id), record(id='independent', path='/missing/second')])
    dialog = LibraryTransferDialog(service)
    dialog.show()
    dialog.load_file(path)
    assert wait_for(qapp, lambda: dialog.job is None)
    assert len(dialog.candidates) == 3 and service.list_applications() == [existing]
    assert dialog.candidates[0].duplicate and dialog.candidates[1].id_conflict
    dialog._select(True)
    assert len(dialog._selected()) == 1
    dialog.ids_cb.setChecked(True)
    dialog._select(True)
    assert len(dialog._selected()) == 2
    assert not dialog.environment_cb.isChecked()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog.start_import()
    assert wait_for(qapp, lambda: not dialog._importing)
    assert dialog.imported == 2 and dialog.missing == 2
    assert '1 duplicates' in dialog.status.text()
    assert len(service.list_applications()) == 3
    dialog.close()


def test_gui_export_and_worker_sqlite_thread_ownership(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.library_transfer_dialog as ui
    entry = add_script(service, tmp_path)
    path = tmp_path / 'gui.json'
    main_thread = threading.get_ident()
    worker_threads = []
    original = ui.export_library
    def wrapped(*args, **kwargs):
        worker_threads.append(threading.get_ident())
        return original(*args, **kwargs)
    monkeypatch.setattr(ui, 'export_library', wrapped)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), 'JSON'))
    dialog = LibraryTransferDialog(service, 'export')
    dialog.go_btn.click()
    assert wait_for(qapp, lambda: dialog.job is None)
    assert 'Exported 1' in dialog.status.text() and read_export(path)[0]['id'] == entry.id
    assert worker_threads and worker_threads[0] != main_thread
    dialog.close()
    # Import also prepares files on a worker but registers through the main-thread service.
    path = write_export(tmp_path, [record()])
    dialog = LibraryTransferDialog(service)
    dialog.load_file(path)
    assert wait_for(qapp, lambda: dialog.job is None)
    dialog._select(True)
    original_import = service.import_configuration
    writes = []
    def register(prepared):
        writes.append(threading.get_ident())
        return original_import(prepared)
    monkeypatch.setattr(service, 'import_configuration', register)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog.start_import()
    assert wait_for(qapp, lambda: not dialog._importing)
    assert writes == [main_thread]
    dialog.close()


def test_close_during_prepare_discards_pending_row_and_icon(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.library_transfer_dialog as ui
    entered, unblock = threading.Event(), threading.Event()
    raw = record()
    raw['icon'] = {'extension': '.png', 'data': 'YWJj'}
    path = write_export(tmp_path, [raw])
    original = ui.prepare_import
    def blocked(*args, **kwargs):
        prepared = original(*args, **kwargs)
        entered.set()
        unblock.wait(5)
        return prepared
    monkeypatch.setattr(ui, 'prepare_import', blocked)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog = LibraryTransferDialog(service)
    dialog.load_file(path)
    assert wait_for(qapp, lambda: dialog.job is None)
    dialog._select(True)
    dialog.start_import()
    assert wait_for(qapp, entered.is_set)
    dialog.close()
    assert dialog._closing
    unblock.set()
    assert wait_for(qapp, lambda: not dialog._importing)
    assert not service.list_applications()
    assert not list(service.icons_dir.glob('*-import-*'))
    service.db.close()
    assert QThreadPool.globalInstance().waitForDone(2000)
    qapp.processEvents()


def test_cancel_keeps_completed_imports_and_reports_remaining(qapp, service, tmp_path, monkeypatch):
    path = write_export(tmp_path, [record(id='one'), record(id='two', path='/missing/two')])
    dialog = LibraryTransferDialog(service)
    dialog.load_file(path)
    assert wait_for(qapp, lambda: dialog.job is None)
    dialog._select(True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog.libraryChanged.connect(dialog._cancel)
    dialog.start_import()
    assert wait_for(qapp, lambda: not dialog._importing)
    assert dialog.imported == 1 and len(service.list_applications()) == 1
    assert 'not processed from selection 1' in dialog.status.text()
    dialog.close()


def test_gui_invalid_document_never_registers(qapp, service, tmp_path):
    path = write_export(tmp_path, [record(), {'id': 'bad'}])
    dialog = LibraryTransferDialog(service)
    dialog.load_file(path)
    assert wait_for(qapp, lambda: dialog.job is None)
    assert 'Application 2' in dialog.status.text()
    assert not dialog.candidates and not dialog.go_btn.isEnabled() and not service.list_applications()
    dialog.close()


def test_reject_registration_when_alias_added_after_preparation(service, tmp_path):
    script = tmp_path / 'original.sh'
    script.write_text('#!/bin/sh\nexit 0\n')
    script.chmod(0o755)
    alias = tmp_path / 'alias.sh'
    os.link(script, alias)
    raw = record(path=str(script))
    raw['format'] = 'executable'
    prepared = prepare_import(preview_import([raw], [])[0], [], service.icons_dir)
    service.add_application(str(alias))
    with pytest.raises(TransferError, match='library changed'):
        service.import_configuration(prepared)
    assert len(service.list_applications()) == 1


def test_directory_is_not_importable_and_permission_failure_is_preserved(service, tmp_path, monkeypatch):
    import appforge.core.library_transfer as core
    directory = preview_import([record(path=str(tmp_path))], [])[0]
    assert directory.invalid_file
    raw = record(path='/unavailable/Example.AppImage')
    monkeypatch.setattr(core.os, 'stat', lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))
    candidate = preview_import([raw], [])[0]
    assert candidate.fingerprint is None and not candidate.invalid_file
    assert 'unavailable' in candidate.status


def test_transfer_never_executes_or_changes_application(service, tmp_path, monkeypatch):
    import subprocess
    marker = tmp_path / 'must-not-exist'
    script = tmp_path / 'untrusted.sh'
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
    script.chmod(0o755)
    original = script.read_bytes()
    raw = record(path=str(script))
    raw['format'] = 'executable'
    for method in ('Popen', 'run', 'call'):
        monkeypatch.setattr(subprocess, method, lambda *args, **kwargs: pytest.fail('Executed an imported application'))
    prepared = prepare_import(preview_import([raw], [])[0], [], service.icons_dir)
    service.import_configuration(prepared)
    assert script.read_bytes() == original and not marker.exists()


def test_database_upgrade_and_reopen_preserves_import_and_settings(service, tmp_path):
    service.db.set_setting('github_token', 'private-token')
    schema = service.db._conn.execute('PRAGMA user_version').fetchone()[0]
    prepared = prepare_import(preview_import([record()], [])[0], [], service.icons_dir, launchers=False)
    entry = service.import_configuration(prepared)
    assert service.db._conn.execute('PRAGMA user_version').fetchone()[0] == schema
    service.db.close()
    service.db = Database(service.db.path)
    assert service.get(entry.id).metadata['asset_pattern'] == 'Example-*.AppImage'
    assert service.db.get_setting('github_token') == 'private-token'


def test_main_window_settings_route_transfer_actions(qapp, service, monkeypatch):
    from appforge.ui.main_window import MainWindow
    win = MainWindow(service)
    calls = []
    monkeypatch.setattr(win, 'open_library_transfer', lambda mode, parent=None: calls.append(mode))
    def execute(dialog):
        dialog.export_btn.click()
        dialog.import_btn.click()
        return SettingsDialog.Rejected
    monkeypatch.setattr(SettingsDialog, 'exec', execute)
    win.open_settings()
    assert calls == ['export', 'import']
    win._quitting = True
    win.close()


def test_export_appended_extension_does_not_overwrite_without_confirmation(qapp, service, tmp_path, monkeypatch):
    destination = tmp_path / 'existing.txt.json'
    destination.write_text('keep me')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(tmp_path / 'existing.txt'), 'JSON'))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.No)
    dialog = LibraryTransferDialog(service, 'export')
    dialog.export()
    assert dialog.job is None and destination.read_text() == 'keep me'
    dialog.close()


def test_imported_inaccessible_paths_do_not_crash_card_state(monkeypatch):
    from appforge.core.library import file_state, FileState
    entry = AppEntry(name='Inaccessible', path='/unavailable/Example.AppImage')
    monkeypatch.setattr(Path, 'exists', lambda _: (_ for _ in ()).throw(PermissionError()))
    assert file_state(entry) is FileState.MISSING
