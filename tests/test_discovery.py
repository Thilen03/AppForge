"""Discovery safety and UI tests; no network or appimagetool required."""
import os
import threading
import time

import pytest

from tuxshelf.core.discovery import (
    IGNORED_KEY, ROOTS_KEY, default_roots, import_candidate, load_paths, save_paths, scan,
)
from tuxshelf.core.library import LibraryError


def program(path, data=b'#!/bin/sh\necho never-run\n', mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)
    return path


def test_scan_formats_metadata_and_read_only(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Discovery executed a file'))
    script = program(tmp_path / 'tool-1.2.sh')
    elf = program(tmp_path / 'nested' / 'binary-2.0', b'\x7fELF' + b'\0' * 100)
    program(tmp_path / 'plain.txt', b'not a program')
    program(tmp_path / 'unexecutable.sh', mode=0o644)
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in (script, elf)}
    updates = []
    result = scan([str(tmp_path)], progress=lambda *args: updates.append(args))
    assert {c.path for c in result.candidates} == {str(script), str(elf)}
    assert {c.metadata.extra['executable_kind'] for c in result.candidates} == {'elf', 'script'}
    assert next(c for c in result.candidates if c.path == str(script)).metadata.version == '1.2'
    assert updates and result.visited == 2 and not result.errors
    for p, original in before.items():
        assert (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) == original


def test_appimage_detection_reuses_metadata_reader(tmp_path, monkeypatch):
    from tuxshelf.core.formats.appimage import AppImageFormat
    from tuxshelf.core.formats import AppMetadata
    image = program(tmp_path / 'Example.AppImage', b'\x7fELF' + b'\0' * 4 + b'AI\x02' + b'\0' * 100, 0o644)
    monkeypatch.setattr(AppImageFormat, 'extract_metadata', lambda self, path:
                        AppMetadata('appimage', 'Embedded Name', '3.4', icon_data=b'icon', icon_ext='png'))
    result = scan([str(tmp_path)])
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.path == str(image) and c.metadata.name_suggestion == 'Embedded Name'
    assert c.metadata.icon_data == b'icon'


def test_symlinks_backup_roots_and_overlapping_scans(tmp_path):
    root = tmp_path / 'root'
    real = program(root / 'app')
    program(root / '.app.backups' / 'old')
    outside = program(tmp_path / 'outside' / 'escape')
    (root / 'alias').symlink_to(real)
    (root / 'escape').symlink_to(outside.parent, target_is_directory=True)
    (root / 'loop').symlink_to(root, target_is_directory=True)
    os.link(real, root / 'hardlink')
    result = scan([str(root), str(root)])
    assert len(result.candidates) == 1
    assert scan([str(root / '.app.backups')]).errors
    assert scan([str(root / 'escape')]).errors
    assert not scan([str(root / 'escape' / 'nested')]).candidates


def test_registered_path_and_hardlink_and_persisted_ignore(tmp_path, service):
    app = program(tmp_path / 'app')
    alias = tmp_path / 'alias'
    os.link(app, alias)
    service.add_application(str(app))
    result = scan([str(tmp_path)], registered=[str(alias)], ignored=[str(app), str(alias)])
    assert len(result.candidates) == 1
    assert result.candidates[0].registered and result.candidates[0].ignored
    save_paths(service.db, ROOTS_KEY, [str(tmp_path), str(tmp_path / '.')])
    assert load_paths(service.db, ROOTS_KEY) == [str(tmp_path)]
    save_paths(service.db, IGNORED_KEY, [str(app)])
    assert load_paths(service.db, IGNORED_KEY) == [str(app)]
    service.db.set_setting(ROOTS_KEY, '{broken')
    assert load_paths(service.db, ROOTS_KEY, default_roots()) == default_roots()


def test_cancellation_and_inaccessible_paths(tmp_path, monkeypatch):
    for i in range(80):
        program(tmp_path / str(i))
    cancel = threading.Event()
    result = scan([str(tmp_path)], cancel=cancel, progress=lambda *_: cancel.set())
    assert result.cancelled and result.visited <= 1
    cancelled = threading.Event()
    cancelled.set()
    assert scan([str(tmp_path)], cancel=cancelled).visited == 0
    import tuxshelf.core.discovery as discovery
    monkeypatch.setattr(discovery.os, 'scandir', lambda p: (_ for _ in ()).throw(PermissionError('denied')))
    result = scan([str(tmp_path)])
    assert 'denied' in result.errors[0]


def test_import_rechecks_identity_missing_permission_and_duplicates(tmp_path, service):
    app = program(tmp_path / 'tool')
    c = scan([str(tmp_path)]).candidates[0]
    assert service.list_applications() == []
    original = app.read_bytes()
    entry = import_candidate(service, c)
    assert entry.path == str(app) and app.read_bytes() == original
    with pytest.raises(LibraryError, match='already'):
        import_candidate(service, c)
    service.remove_application(entry.id)
    alias = tmp_path / 'alias'
    os.link(app, alias)
    service.add_application(str(alias))
    with pytest.raises(LibraryError, match='already'):
        import_candidate(service, c)
    service.remove_application(service.list_applications()[0].id)
    app.chmod(0o644)
    with pytest.raises(LibraryError, match='executable'):
        import_candidate(service, c)
    app.chmod(0o755)
    app.write_bytes(b'#!/bin/sh\nchanged-content\n')
    with pytest.raises(LibraryError, match='changed'):
        import_candidate(service, c)
    app.unlink()
    with pytest.raises(LibraryError, match="Couldn't read"):
        import_candidate(service, c)


def test_symlink_substitution_rejected(tmp_path, service):
    app = program(tmp_path / 'app')
    c = scan([str(tmp_path)]).candidates[0]
    target = tmp_path / 'moved'
    app.rename(target)
    app.symlink_to(target)
    with pytest.raises(LibraryError, match='non-symlink'):
        import_candidate(service, c)
    assert not service.list_applications()


@pytest.fixture(scope='module')
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def wait(qapp, condition):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return
        time.sleep(0.005)
    pytest.fail('GUI operation timed out')


def test_dialog_preview_confirmation_ignore_import_and_persistence(qapp, tmp_path, service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tuxshelf.ui.discovery_dialog import DiscoveryDialog
    program(tmp_path / 'one')
    program(tmp_path / 'two')
    dlg = DiscoveryDialog(service)
    dlg.roots.clear()
    dlg.roots.addItem(str(tmp_path))
    dlg.start_scan()
    wait(qapp, lambda: dlg.job is None)
    assert len(dlg.candidates) == 2 and not service.list_applications()
    assert not dlg.import_btn.isEnabled() and dlg.import_all_btn.isEnabled()
    dlg._select(True)
    assert dlg.import_btn.isEnabled()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.No)
    dlg._import(False)
    assert not service.list_applications()
    dlg._ignore()
    assert not dlg.import_all_btn.isEnabled()
    second = DiscoveryDialog(service)
    assert len(second.ignored) == 2 and second._roots() == [str(tmp_path)]
    second.close()
    dlg._reset_ignored()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    dlg.desktop_cb.setChecked(True)
    dlg._import(True)
    wait(qapp, lambda: not dlg._importing)
    assert len(service.list_applications()) == 2
    assert all(service.desktop_enabled(e) for e in service.list_applications())
    assert not dlg.import_all_btn.isEnabled()
    dlg.start_scan()
    wait(qapp, lambda: dlg.job is None)
    assert all(c.registered for c in dlg.candidates)
    dlg.close()
    dlg.deleteLater()


def test_worker_keeps_event_loop_responsive_and_close_cancels(qapp, tmp_path, service, monkeypatch):
    from PySide6.QtCore import QTimer
    from tuxshelf.ui.discovery_dialog import DiscoveryDialog
    import tuxshelf.core.discovery as discovery
    started = threading.Event()
    def slow_scan(roots, registered, ignored, cancel, progress):
        started.set()
        assert cancel.wait(5), 'Close did not cancel the scanner'
        return discovery.ScanResult(cancelled=True)
    monkeypatch.setattr(discovery, 'scan', slow_scan)
    dlg = DiscoveryDialog(service)
    dlg.start_scan()
    assert started.wait(2)
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    wait(qapp, lambda: bool(ticks))
    dlg.reject()
    wait(qapp, lambda: dlg.job is None)
    assert dlg._closing and 'cancelled' in dlg.status.text()
    dlg.deleteLater()


def test_changed_file_during_scan_is_reported(tmp_path, monkeypatch):
    import tuxshelf.core.discovery as discovery
    app = program(tmp_path / 'tool')
    original = discovery.inspect_file
    def changing(path):
        md = original(path)
        path.write_bytes(b'#!/bin/sh\nchanged while reading\n')
        return md
    monkeypatch.setattr(discovery, 'inspect_file', changing)
    result = scan([str(tmp_path)])
    assert not result.candidates and 'changed' in result.errors[0]
    assert app.exists()


def test_missing_root_and_unreadable_candidate_do_not_abort(tmp_path, monkeypatch):
    import tuxshelf.core.discovery as discovery
    program(tmp_path / 'bad')
    good = program(tmp_path / 'good')
    original = discovery.inspect_file
    def reading(path):
        if path.name == 'bad':
            raise PermissionError('unreadable')
        return original(path)
    monkeypatch.setattr(discovery, 'inspect_file', reading)
    result = scan([str(tmp_path / 'missing'), str(tmp_path)])
    assert [c.path for c in result.candidates] == [str(good)]
    assert len(result.errors) == 2


def test_import_can_stop_and_changed_candidate_does_not_block_next(qapp, tmp_path, service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from tuxshelf.ui.discovery_dialog import DiscoveryDialog
    one = program(tmp_path / 'one')
    program(tmp_path / 'two')
    dlg = DiscoveryDialog(service)
    dlg._scanned(scan([str(tmp_path)]))
    one.unlink()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    dlg._import(True)
    wait(qapp, lambda: not dlg._importing)
    assert len(service.list_applications()) == 1 and len(dlg._failures) == 1
    assert 'Imported 1' in dlg.status.text()
    dlg._scanned(scan([str(tmp_path)]))
    dlg._import(True)
    dlg._cancel()
    wait(qapp, lambda: not dlg._importing)
    assert len(service.list_applications()) == 1
    dlg.close()
    dlg.deleteLater()


def test_main_window_discovery_entry_refreshes_library(qapp, service, tmp_path, monkeypatch):
    import tuxshelf.ui.discovery_dialog as discovery_dialog
    from tuxshelf.ui.main_window import MainWindow
    app = program(tmp_path / 'new-tool')
    class Dialog:
        def __init__(self, library, parent):
            self.library = library
        def exec(self):
            self.library.add_application(str(app))
        def deleteLater(self):
            pass
    monkeypatch.setattr(discovery_dialog, 'DiscoveryDialog', Dialog)
    window = MainWindow(service)
    window.discover_btn.click()
    assert len(window._cards) == 1
    window.close()
    window.deleteLater()


def test_dialog_scans_all_saved_roots_regardless_of_watch_checkboxes(qapp, tmp_path, service):
    from tuxshelf.ui.discovery_dialog import DiscoveryDialog
    selected = program(tmp_path / 'applications' / 'tool')
    other = program(tmp_path / 'emulators' / 'other-tool')
    dlg = DiscoveryDialog(service)
    dlg.roots.clear()
    dlg._add_root(str(selected.parent), watched=True)
    dlg._add_root(str(other.parent))
    dlg.start_scan()
    wait(qapp, lambda: dlg.job is None)
    assert {c.path for c in dlg.candidates} == {str(selected), str(other)}
    dlg.close()
    dlg.deleteLater()


def test_scan_skips_roms_and_data_before_format_reads(tmp_path, monkeypatch):
    import tuxshelf.core.discovery as discovery
    app = program(tmp_path / 'emulator.AppImage')
    for i in range(200):
        program(tmp_path / 'roms' / f'game-{i}.extm')
    for name in ('game.iso', 'archive.zip', 'data.txt', 'part.AppImage.part', 'library.so',
                 'game-1.2.extm', 'game-1.2-beta.1.extm'):
        program(tmp_path / name)
    program(tmp_path / 'not-executable.sh', mode=0o644)
    original = discovery.detect_format
    inspected = []
    def detect(path):
        inspected.append(path)
        return original(path)
    monkeypatch.setattr(discovery, 'detect_format', detect)
    result = scan([str(tmp_path)])
    assert inspected == [app]
    assert [c.path for c in result.candidates] == [str(app)]
    assert result.visited == 1 and not result.errors


@pytest.mark.parametrize('name', [
    'tool', 'tool-1.2.3', 'tool-1.2.3-beta.1', 'tool.AppImage', 'tool.APPIMAGE',
    'tool.run', 'tool.bin', 'tool.elf', 'tool.out', 'tool.sh', 'tool.bash',
    'tool.py', 'tool.pl', 'tool.rb', 'tool.x86_64', 'tool.aarch64',
])
def test_scan_common_executable_names(tmp_path, name):
    app = program(tmp_path / name)
    assert [c.path for c in scan([str(tmp_path)]).candidates] == [str(app)]


def test_matching_extension_does_not_make_data_an_application(tmp_path):
    for name in ('fake.AppImage', 'fake.bin', 'fake.sh', 'fake'):
        program(tmp_path / name, data=b'ROM data, not executable content')
    assert not scan([str(tmp_path)]).candidates


@pytest.fixture
def results_dialog(qapp, service, tmp_path):
    from tuxshelf.ui.discovery_dialog import DiscoveryDialog
    for name in ('zulu-3.0.sh', 'Bravo-1.0.sh', 'alpha-2.0.sh'):
        program(tmp_path / name)
    result = scan([str(tmp_path)])
    names = {'zulu-3.0.sh': 'zulu', 'Bravo-1.0.sh': 'Bravo', 'alpha-2.0.sh': 'alpha'}
    from pathlib import Path
    for c in result.candidates:
        c.metadata.name_suggestion = names[Path(c.path).name]
    result.candidates.sort(key=lambda c: c.path, reverse=True)
    dlg = DiscoveryDialog(service, preview=result)
    yield dlg
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()


def visible_paths(dlg):
    from PySide6.QtCore import Qt
    return [dlg.table.item(row, 0).data(Qt.UserRole) for row in range(dlg.table.rowCount())
            if not dlg.table.isRowHidden(row)]


def result_row(dlg, path):
    from PySide6.QtCore import Qt
    return next(row for row in range(dlg.table.rowCount()) if dlg.table.item(row, 0).data(Qt.UserRole) == path)


def test_results_search_fields_clear_and_no_matches(results_dialog):
    dlg = results_dialog
    alpha = next(c.path for c in dlg.candidates if c.metadata.name_suggestion == 'alpha')
    for query in (' ALPHA ', 'alpha-2.0.sh', '2.0', 'script'):
        dlg.search_edit.setText(query)
        assert alpha in visible_paths(dlg)
    dlg.search_edit.setText('alpha-2.0.sh')
    assert visible_paths(dlg) == [alpha]
    assert dlg.result_count.text() == 'Showing 1 of 3 applications'
    dlg.search_edit.setText('nothing-matches')
    assert not visible_paths(dlg) and 'No matching' in dlg.result_count.text()
    assert not dlg.import_btn.isEnabled() and not dlg.import_all_btn.isEnabled()
    dlg.search_edit.clear()
    assert len(visible_paths(dlg)) == 3
    assert dlg.import_all_btn.isEnabled()


def test_header_click_sorts_and_filter_tracks_paths(results_dialog, qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    dlg = results_dialog
    dlg.show()
    qapp.processEvents()
    def names():
        return [dlg.table.item(row, 0).text() for row in range(dlg.table.rowCount())]
    assert names() == ['alpha', 'Bravo', 'zulu']
    dlg.search_edit.setText('alpha')
    header = dlg.table.horizontalHeader()
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(header.sectionViewportPosition(0) + header.sectionSize(0) // 2, header.height() // 2))
    qapp.processEvents()
    assert names() == ['zulu', 'Bravo', 'alpha']
    assert len(visible_paths(dlg)) == 1 and 'alpha-' in visible_paths(dlg)[0]
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(header.sectionViewportPosition(0) + header.sectionSize(0) // 2, header.height() // 2))
    qapp.processEvents()
    assert names() == ['alpha', 'Bravo', 'zulu']
    dlg.search_edit.clear()
    dlg.table.sortItems(1, Qt.AscendingOrder)
    assert [dlg.table.item(row, 1).text() for row in range(3)] == ['1.0', '2.0', '3.0']


def test_sorting_keeps_sources_and_selection_with_correct_import(results_dialog, qapp, service, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    dlg = results_dialog
    alpha = next(c.path for c in dlg.candidates if c.metadata.name_suggestion == 'alpha')
    row = result_row(dlg, alpha)
    dlg.table.cellWidget(row, 5).setText('https://github.com/example/alpha')
    dlg.table.item(row, 0).setCheckState(Qt.Checked)
    dlg.table.sortItems(0, Qt.DescendingOrder)
    assert [c.path for c in dlg._selected()] == [alpha]
    dlg.table.sortItems(5, Qt.DescendingOrder)
    row = result_row(dlg, alpha)
    assert dlg.table.cellWidget(row, 5).text() == 'https://github.com/example/alpha'
    # Editing the active sort column must keep the editor, source and app together.
    dlg.table.cellWidget(row, 5).setText('https://codeberg.org/example/alpha')
    assert [c.path for c in dlg._selected()] == [alpha]
    dlg.search_edit.setText('CODEBERG')
    assert visible_paths(dlg) == [alpha]
    dlg.desktop_cb.setChecked(False)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    dlg._import(False)
    wait(qapp, lambda: not dlg._importing)
    entries = service.list_applications()
    assert len(entries) == 1 and entries[0].path == alpha
    assert entries[0].github_repo == 'https://codeberg.org/example/alpha'
    row = result_row(dlg, alpha)
    assert not dlg.table.item(row, 0).flags() & Qt.ItemIsEnabled


@pytest.mark.parametrize('action', ['selected', 'all', 'ignore'])
def test_filtered_bulk_actions_do_not_affect_hidden_checked_apps(results_dialog, qapp, service, monkeypatch, action):
    from PySide6.QtWidgets import QMessageBox
    dlg = results_dialog
    dlg._select(True)
    dlg.search_edit.setText('Bravo')
    bravo = visible_paths(dlg)[0]
    assert [c.path for c in dlg._selected()] == [bravo]
    dlg._select(False)
    assert not dlg._selected()
    dlg.search_edit.clear()
    assert len(dlg._selected()) == 2  # Hidden checkboxes were preserved.
    dlg.search_edit.setText('Bravo')
    dlg._select(True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    dlg.desktop_cb.setChecked(False)
    if action == 'ignore':
        dlg._ignore()
        assert dlg.ignored == {bravo}
        assert not service.list_applications()
        dlg._reset_ignored()
        assert visible_paths(dlg) == [bravo]
    else:
        assert dlg.import_all_btn.text() == 'Import all matching'
        dlg._import(action == 'all')
        wait(qapp, lambda: not dlg._importing)
        assert [entry.path for entry in service.list_applications()] == [bravo]
    dlg.search_edit.clear()
    assert len(dlg._selected()) == 2


def test_rescan_reapplies_search_and_sort(results_dialog, qapp, tmp_path):
    from PySide6.QtCore import Qt
    dlg = results_dialog
    dlg.roots.clear()
    dlg.roots.addItem(str(tmp_path))
    dlg.search_edit.setText('alpha')
    dlg.table.sortItems(0, Qt.DescendingOrder)
    dlg.start_scan()
    wait(qapp, lambda: dlg.job is None)
    assert len(visible_paths(dlg)) == 1 and 'alpha-' in visible_paths(dlg)[0]
    assert dlg.table.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder
    assert not dlg._selected()
