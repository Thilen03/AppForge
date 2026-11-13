"""Background jobs. They run pure functions from core.updates and report back by signal;
all database writes happen on the main thread."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.updates.checker import check_for_update
from ..core.updates.installer import InstallError, install_update


class JobSignals(QObject):
    done = Signal(str, object)          # app_id, CheckOutcome | InstallResult | InstallError
    progress = Signal(str, int, int)    # app_id, bytes_done, bytes_total


class CheckJob(QRunnable):
    def __init__(self, app_id: str, **kwargs):
        super().__init__()
        self.app_id, self.kwargs, self.signals = app_id, kwargs, JobSignals()

    def run(self):
        self.signals.done.emit(self.app_id, check_for_update(**self.kwargs))


class InstallJob(QRunnable):
    def __init__(self, app_id: str, path: str, asset: dict, assets: list[dict], old_version: str | None,
                 format_id: str = "appimage"):
        super().__init__()
        self.app_id, self.signals = app_id, JobSignals()
        self._args = (path, asset, assets, old_version, format_id)
        self.cancel = threading.Event()

    def run(self):
        path, asset, assets, old_version, format_id = self._args
        try:
            result = install_update(
                path, asset, assets, old_version=old_version, cancel=self.cancel, format_id=format_id,
                progress=lambda done, total: self.signals.progress.emit(self.app_id, done, total))
        except InstallError as exc:
            result = exc
        except Exception as exc:  # noqa: BLE001 - never let a worker die silently
            result = InstallError(f"Unexpected error: {exc}")
        self.signals.done.emit(self.app_id, result)
