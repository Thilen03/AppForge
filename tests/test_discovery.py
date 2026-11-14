"""Discovery safety and UI tests; no network or appimagetool required."""
import os
import threading
import time

import pytest

from appforge.core.discovery import (
    IGNORED_KEY, ROOTS_KEY, default_roots, import_candidate, load_paths, save_paths, scan,
)
from appforge.core.library import LibraryError


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
    assert updates and result.visited == 4 and not result.errors
    for p, original in before.items():
        assert (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) == original


def test_appimage_detection_reuses_metadata_reader(tmp_path, monkeypatch):
    from appforge.core.formats.appimage import AppImageFormat
    from appforge.core.formats import AppMetadata
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
    import appforge.core.discovery as discovery
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
    from appforge.ui.discovery_dialog import DiscoveryDialog
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
    from appforge.ui.discovery_dialog import DiscoveryDialog
    import appforge.core.discovery as discovery
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
    import appforge.core.discovery as discovery
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
    import appforge.core.discovery as discovery
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
    from appforge.ui.discovery_dialog import DiscoveryDialog
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
    import appforge.ui.discovery_dialog as discovery_dialog
    from appforge.ui.main_window import MainWindow
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
