"""Folder watching reuses safe discovery, stable snapshots and explicit review/import."""
import os
import threading

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from test_discovery import program, qapp, wait  # noqa: F401
from tuxshelf.core.discovery import IGNORED_KEY, ROOTS_KEY, import_candidate, save_paths
from tuxshelf.core.discovery_watch import WATCHED_KEY, scan_watched
from tuxshelf.ui.discovery_dialog import DiscoveryDialog
from tuxshelf.ui.discovery_watch import DiscoveryWatcher
from tuxshelf.ui.main_window import MainWindow


def watch(service, root):
    save_paths(service.db, ROOTS_KEY, [str(root)])
    save_paths(service.db, WATCHED_KEY, [str(root)])


def poll(qapp, watcher):
    watcher.poll()
    wait(qapp, lambda: watcher.job is None)


def test_stable_files_cached_but_changes_need_another_poll(tmp_path, monkeypatch):
    import tuxshelf.core.discovery as discovery
    app = program(tmp_path / 'nested' / 'app')
    original = discovery.inspect_file
    inspected = []
    def inspect(path):
        inspected.append(path)
        return original(path)
    monkeypatch.setattr(discovery, 'inspect_file', inspect)
    result, state = scan_watched([str(tmp_path)])
    assert not result.candidates and not inspected
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert [c.path for c in result.candidates] == [str(app)]
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert len(result.candidates) == 1 and len(inspected) == 1
    app.write_bytes(b'#!/bin/sh\necho new version\n')
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates and len(inspected) == 1
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert len(result.candidates) == 1 and len(inspected) == 2
    app.unlink()
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates and not state.metadata


def test_partial_downloads_rename_and_execute_permission(tmp_path):
    partial = program(tmp_path / 'download.AppImage.part')
    for name in ('thing.partial', 'thing.tmp', 'thing.download', 'thing.crdownload', '.hidden'):
        program(tmp_path / name)
    script = program(tmp_path / 'script', mode=0o644)
    _, state = scan_watched([str(tmp_path)])
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates
    final = tmp_path / 'download'
    partial.rename(final)
    script.chmod(0o755)
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert {c.path for c in result.candidates} == {str(final), str(script)}


def test_watching_uses_discovery_safety_and_excludes_known_ignored(tmp_path, service):
    root = tmp_path / 'root'
    known = program(root / 'known')
    ignored = program(root / 'ignored')
    new = program(root / 'nested' / 'new')
    os.link(known, root / 'known-alias')
    (root / 'symlink').symlink_to(new)
    program(root / '.app.backups' / 'backup')
    outside = program(tmp_path / 'outside' / 'external')
    (root / 'escape').symlink_to(outside.parent, target_is_directory=True)
    service.add_application(str(known))
    args = [str(root), str(root / 'nested')], [str(known)], [str(ignored)]
    _, state = scan_watched(*args)
    result, state = scan_watched(*args, previous=state)
    assert [c.path for c in result.candidates] == [str(new)]
    assert len(service.list_applications()) == 1
    cancel = threading.Event()
    cancel.set()
    result, _ = scan_watched(*args, previous=state, cancel=cancel)
    assert result.cancelled


def test_missing_root_reappears_and_hidden_selected_root_works(tmp_path):
    root = tmp_path / '.apps'
    result, state = scan_watched([str(root)])
    assert result.errors
    app = program(root / 'app')
    result, state = scan_watched([str(root)], previous=state)
    assert not result.candidates
    result, state = scan_watched([str(root)], previous=state)
    assert [c.path for c in result.candidates] == [str(app)]


def test_watch_checkboxes_persist_and_removed_folders_stop(qapp, service, tmp_path):
    root = tmp_path / 'apps'
    root.mkdir()
    save_paths(service.db, ROOTS_KEY, [str(root)])
    dialog = DiscoveryDialog(service)
    assert dialog.roots.item(0).checkState() == Qt.Unchecked
    dialog.roots.item(0).setCheckState(Qt.Checked)
    dialog.reject()
    reopened = DiscoveryDialog(service)
    assert reopened.roots.item(0).checkState() == Qt.Checked
    watcher = DiscoveryWatcher(service)
    assert watcher.roots == (str(root),) and watcher.timer.isActive()
    reopened.preferencesChanged.connect(watcher.refresh)
    reopened.roots.setCurrentRow(0)
    reopened._remove_folder()
    assert not watcher.roots and not watcher.timer.isActive()
    watcher.stop()
    reopened.reject()


def test_only_discovery_folders_are_watched_and_default_is_off(qapp, service, tmp_path):
    watcher = DiscoveryWatcher(service)
    assert not watcher.roots and not watcher.timer.isActive()
    save_paths(service.db, ROOTS_KEY, [str(tmp_path / 'allowed')])
    save_paths(service.db, WATCHED_KEY, [str(tmp_path / 'outside')])
    watcher.poll()
    assert watcher.job is None and not watcher.roots
    watcher.stop()


def test_controller_async_import_ignore_removal_and_no_repeat_count(qapp, service, tmp_path):
    one = program(tmp_path / 'one')
    two = program(tmp_path / 'two')
    watch(service, tmp_path)
    watcher = DiscoveryWatcher(service)
    changes = []
    watcher.changed.connect(lambda result: changes.append(len(result.candidates)))
    poll(qapp, watcher)
    assert not watcher.result.candidates
    poll(qapp, watcher)
    assert len(watcher.result.candidates) == 2 and not service.list_applications()
    poll(qapp, watcher)
    assert changes[-1] == 2
    c = next(c for c in watcher.result.candidates if c.path == str(one))
    import_candidate(service, c)
    watcher.prune_registered()
    assert len(watcher.result.candidates) == 1
    save_paths(service.db, IGNORED_KEY, [str(two)])
    poll(qapp, watcher)
    poll(qapp, watcher)
    assert not watcher.result.candidates
    save_paths(service.db, IGNORED_KEY, [])
    poll(qapp, watcher)
    poll(qapp, watcher)
    assert [c.path for c in watcher.result.candidates] == [str(two)]
    two.unlink()
    poll(qapp, watcher)
    assert not watcher.result.candidates
    watcher.stop()


def test_busy_reconfiguration_discards_stale_result_and_stop_cancels(qapp, service, tmp_path, monkeypatch):
    import tuxshelf.ui.discovery_watch as module
    from tuxshelf.core.discovery import ScanResult
    from tuxshelf.core.discovery_watch import WatchState
    watch(service, tmp_path)
    started = threading.Event()
    cancels = []
    def slow(roots, registered, ignored, state, cancel):
        started.set()
        assert cancel.wait(5)
        cancels.append(True)
        return ScanResult(cancelled=True), WatchState()
    monkeypatch.setattr(module, 'scan_watched', slow)
    watcher = DiscoveryWatcher(service)
    watcher.poll()
    assert started.wait(2)
    job = watcher.job
    watcher.poll()
    assert watcher.job is job
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    wait(qapp, lambda: bool(ticks))
    save_paths(service.db, WATCHED_KEY, [])
    watcher.refresh()
    wait(qapp, lambda: watcher.job is None)
    assert cancels and not watcher.result.candidates and not watcher.timer.isActive()
    save_paths(service.db, WATCHED_KEY, [str(tmp_path)])
    started.clear()
    watcher.poll()
    assert started.wait(2)
    watcher.stop()
    wait(qapp, lambda: watcher.job is None)
    assert len(cancels) == 2


def test_review_banner_uses_existing_unchecked_preview_and_import(qapp, service, tmp_path, monkeypatch):
    for name in ('one', 'two', 'three'):
        program(tmp_path / name)
    watch(service, tmp_path)
    window = MainWindow(service)
    wait(qapp, lambda: window.discovery_watcher.job is None)
    poll(qapp, window.discovery_watcher)
    assert window.discovery_found_btn.text() == '3 new apps found — Review…'
    assert not window.discovery_found_btn.isHidden()
    assert not service.list_applications()
    def review(dialog):
        assert len(dialog.candidates) == 3
        assert not dialog._selected() and not dialog.import_btn.isEnabled()
        assert all(dialog.table.item(row, 0).checkState() == Qt.Unchecked for row in range(3))
        dialog.table.item(0, 0).setCheckState(Qt.Checked)
        dialog._import(False)
        wait(qapp, lambda: not dialog._importing)
    monkeypatch.setattr(DiscoveryDialog, 'exec', review)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    window.discovery_found_btn.click()
    assert len(service.list_applications()) == 1
    assert window.discovery_found_btn.text() == '2 new apps found — Review…'
    window.close()
    wait(qapp, lambda: window.discovery_watcher.job is None)
    assert not window.discovery_watcher.timer.isActive()
    window.deleteLater()


def test_timer_detects_new_arrivals_without_manual_scan(qapp, service, tmp_path):
    watch(service, tmp_path)
    watcher = DiscoveryWatcher(service)
    watcher.timer.setInterval(20)
    app = program(tmp_path / 'arriving')
    wait(qapp, lambda: len(watcher.result.candidates) == 1)
    assert watcher.result.candidates[0].path == str(app)
    assert not service.list_applications()
    service.add_application(str(app))
    wait(qapp, lambda: not watcher.result.candidates)
    watcher.stop()
    wait(qapp, lambda: watcher.job is None)


def test_unchanged_non_apps_are_not_reopened(tmp_path, monkeypatch):
    import tuxshelf.core.discovery as discovery
    program(tmp_path / 'notes.txt', b'not an application')
    _, state = scan_watched([str(tmp_path)])
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates
    monkeypatch.setattr(discovery, 'detect_format', lambda path: pytest.fail('Unchanged file reopened'))
    result, _ = scan_watched([str(tmp_path)], previous=state)
    assert not result.candidates


def test_watching_does_not_observe_or_cache_unrelated_files(tmp_path):
    app = program(tmp_path / 'emulator')
    for i in range(50):
        program(tmp_path / 'roms' / f'game-{i}.extm')
    _, state = scan_watched([str(tmp_path)])
    assert set(state.observations) == {str(app)}
    result, state = scan_watched([str(tmp_path)], previous=state)
    assert [c.path for c in result.candidates] == [str(app)]
    assert set(state.metadata) == {str(app)}
