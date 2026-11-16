"""Cancellable discovery polling; all library/settings access stays on the UI thread."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from ..core.discovery import IGNORED_KEY, ROOTS_KEY, ScanResult, default_roots, load_paths
from ..core.discovery_watch import WATCHED_KEY, WatchState, scan_watched
from .workers import DiscoverySignals

POLL_MS = 10_000


class WatchJob(QRunnable):
    def __init__(self, roots, registered, ignored, state):
        super().__init__()
        self.args = roots, registered, ignored, state
        self.cancel = threading.Event()
        self.signals = DiscoverySignals()

    def run(self):
        try:
            result = scan_watched(*self.args, cancel=self.cancel)
        except Exception as exc:
            result = ScanResult(errors=[f"Folder watching failed: {exc}"]), self.args[3]
        self.signals.done.emit(result)


class DiscoveryWatcher(QObject):
    changed = Signal(object)  # ScanResult containing eligible stable candidates

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.roots = ()
        self.job = None
        self.state = WatchState()
        self.result = ScanResult()
        self._generation = 0
        self._job_generation = 0
        self._stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        self.refresh()

    def refresh(self):
        if self._stopped:
            return
        allowed = set(load_paths(self.service.db, ROOTS_KEY, default_roots()))
        roots = tuple(p for p in load_paths(self.service.db, WATCHED_KEY) if p in allowed)
        ignored = tuple(load_paths(self.service.db, IGNORED_KEY))
        config = roots, ignored
        if config != getattr(self, '_config', None):
            self._config = config
            if roots != self.roots:
                self.state = WatchState()
            self.roots = roots
            self._generation += 1
            self.result = ScanResult()
            self.changed.emit(self.result)
            if self.job:
                self.job.cancel.set()
        if self.roots:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def poll(self):
        self.refresh()
        if self._stopped or not self.roots or self.job is not None:
            return
        self._job_generation = self._generation
        self.job = WatchJob(self.roots, [e.path for e in self.service.list_applications()],
                            load_paths(self.service.db, IGNORED_KEY), self.state)
        self.job.signals.done.connect(self._done)
        QThreadPool.globalInstance().start(self.job)

    def _done(self, payload):
        self.job = None
        if self._stopped:
            return
        self.refresh()
        if self._job_generation != self._generation:
            QTimer.singleShot(0, self.poll)
            return
        result, state = payload
        if result.cancelled:
            return
        # A user may import files while this worker is running.
        registered = {e.path for e in self.service.list_applications()}
        result.candidates = [c for c in result.candidates if c.path not in registered]
        self.state, self.result = state, result
        self.changed.emit(result)

    def prune_registered(self):
        registered = {e.path for e in self.service.list_applications()}
        self.result.candidates = [c for c in self.result.candidates if c.path not in registered]
        self.changed.emit(self.result)

    def stop(self):
        self._stopped = True
        self.timer.stop()
        if self.job:
            self.job.cancel.set()
