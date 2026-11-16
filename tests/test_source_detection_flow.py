"""Drive the real local Add modals and worker, with source status always in view."""
import threading

import pytest
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QFileDialog, QPushButton, QScrollArea

from test_gui import qapp  # noqa: F401
from test_discovery import wait
from test_appimage_sources import INFO, SOURCE, image
from tuxshelf.core.library import LibraryError, inspect_file
from tuxshelf.ui import dialogs
from tuxshelf.ui.dialogs import AddApplicationDialog
from tuxshelf.ui.download_dialog import AddSourceDialog
from tuxshelf.ui.main_window import MainWindow


@pytest.mark.parametrize('outcome', ['found', 'not_found', 'failed'])
def test_add_local_browse_runs_detection_with_visible_progress(qapp, service, tmp_path, monkeypatch, outcome):
    path = image(tmp_path / 'Example.AppImage', INFO if outcome == 'found' else '')
    started, release = threading.Event(), threading.Event()
    def inspecting(value):
        started.set()
        assert release.wait(4), 'The UI never released the real inspection worker'
        if outcome == 'failed':
            raise LibraryError('Cannot read the selected file')
        return inspect_file(value)
    monkeypatch.setattr(dialogs, 'inspect_file', inspecting)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(path), 'AppImage'))
    window = MainWindow(service)
    monkeypatch.setattr(window, 'check_updates', lambda *a, **k: None)
    window.show()
    seen, errors = [], []
    checking_ticks = 0
    timer = QTimer()
    timer.setInterval(10)
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def abort(error):
        errors.append(error)
        release.set()
        timer.stop()
        active = qapp.activeModalWidget()
        if active:
            active.reject()

    def step():
        nonlocal checking_ticks
        try:
            active = qapp.activeModalWidget()
            if isinstance(active, AddSourceDialog):
                seen.append('local choice')
                next(b for b in active.findChildren(QPushButton) if b.text() == 'Add a local file…').click()
            elif isinstance(active, AddApplicationDialog):
                if not active.path_edit.text():
                    active.resize(520, 440)
                    assert active._source_state == 'waiting'
                    seen.append('browse')
                    next(b for b in active.findChildren(QPushButton) if b.text() == 'Browse…').click()
                    return
                scroll = active.findChild(QScrollArea)
                assert not scroll.isAncestorOf(active.source_panel)
                assert active.source_panel.isVisible() and active.source_status_lbl.isVisible()
                assert active.rect().contains(active.source_panel.geometry())
                if active._source_state == 'checking':
                    assert 'Checking this file' in active.source_status_lbl.text()
                    assert active.source_progress.isVisible()
                    assert not active.add_btn.isEnabled()
                    checking_ticks += 1
                    if started.is_set() and checking_ticks >= 2:
                        seen.append('checking')
                        release.set()
                elif active._source_state == outcome:
                    assert 'checking' in seen
                    assert not active.source_progress.isVisible()
                    text = active.source_status_lbl.text()
                    assert ('Update source found:' if outcome == 'found' else
                            'No automatic update source found' if outcome == 'not_found' else
                            'Source detection failed:') in text
                    if outcome == 'found':
                        assert SOURCE in text and active.repo_edit.text() == SOURCE
                    # Scrolling and ordinary field validation cannot hide/overwrite the result.
                    before = active.source_panel.mapTo(active, QPoint(0, 0))
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    active.name_edit.setText('Chosen app name')
                    assert active.source_panel.mapTo(active, QPoint(0, 0)) == before
                    assert active.source_status_lbl.text() == text
                    seen.append(outcome)
                    timer.stop()
                    if outcome == 'failed':
                        active.reject()
                    else:
                        assert active.add_btn.isEnabled()
                        active.add_btn.click()
        except BaseException as exc:
            abort(exc)

    timer.timeout.connect(step)
    watchdog.timeout.connect(lambda: abort(AssertionError('Local Add flow timed out')))
    timer.start()
    watchdog.start(5000)
    try:
        window.add_btn.click()
    finally:
        release.set()
        timer.stop()
        watchdog.stop()
        window.close()
        window.deleteLater()
        qapp.processEvents()
    if errors:
        raise errors[0]
    assert seen[:2] == ['local choice', 'browse'] and seen[-1] == outcome
    entries = service.list_applications()
    if outcome == 'failed':
        assert not entries
    else:
        assert len(entries) == 1 and entries[0].name == 'Chosen app name'
        assert entries[0].github_repo == (SOURCE if outcome == 'found' else None)


def test_stale_result_cannot_replace_visible_status(qapp, service, tmp_path, monkeypatch):
    class Pool:
        def start(self, job):
            pass
    monkeypatch.setattr(dialogs.QThreadPool, 'globalInstance', lambda: Pool())
    first = image(tmp_path / 'First.AppImage')
    second = image(tmp_path / 'Second.AppImage', '')
    dialog = AddApplicationDialog(service, initial_path=str(first))
    old_token = dialog._token
    dialog._set_path(str(second))
    dialog._on_inspected(old_token, inspect_file(first))
    assert dialog._source_state == 'checking'
    dialog._on_inspected(dialog._token, inspect_file(second))
    assert dialog._source_state == 'not_found'
    dialog._on_inspected(old_token, 'late error')
    assert dialog._source_state == 'not_found'
    dialog.close()


def test_manual_source_does_not_hide_detection_result(qapp, service, tmp_path):
    path = image(tmp_path / 'Example.AppImage')
    dialog = AddApplicationDialog(service)
    dialog.repo_edit.setText('https://codeberg.org/my/choice')
    dialog._set_path(str(path))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog._source_state == 'found'
    assert SOURCE in dialog.source_status_lbl.text()
    assert 'existing source choice has been kept' in dialog.source_status_lbl.text()
    dialog.repo_edit.clear()
    assert dialog._source_state == 'found'
    assert SOURCE in dialog.source_status_lbl.text()
    dialog.close()
