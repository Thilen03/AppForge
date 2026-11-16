"""Session-only KWin minimize notifications for Plasma's Wayland backend.

Wayland does not report all compositor-driven minimizes to Qt. This observer only
reads the owning process's normal windows; it never changes KWin configuration.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusServiceWatcher

log = logging.getLogger(__name__)
SERVICE = "org.kde.KWin"
SCRIPTING = "org.kde.kwin.Scripting"
CALLBACK = "org.tuxshelf.TrayObserver"


def plasma_wayland(platform: str) -> bool:
    desktop = ":".join(os.environ.get(key, "") for key in
                       ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")).lower()
    return platform.startswith("wayland") and any(name in desktop for name in ("kde", "plasma"))


def render_observer(pid: int, destination: str, path: str, token: str) -> str:
    # JSON encoding keeps every generated argument a literal, never executable input.
    return """(function () {
    const ownPid = %d;
    function observe(window) {
        if (window.pid !== ownPid || !window.normalWindow || window.dialog) return;
        function changed() {
            callDBus(%s, %s, %s, "stateChanged", %s, Boolean(window.minimized));
        }
        window.minimizedChanged.connect(changed);
        changed();
    }
    workspace.windowAdded.connect(observe);
    workspace.windowList().forEach(observe);
})();
""" % (pid, json.dumps(destination), json.dumps(path), json.dumps(CALLBACK), json.dumps(token))


class SessionBus(QObject):
    ownerChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bus = QDBusConnection.sessionBus()
        self.watcher = QDBusServiceWatcher(SERVICE, self.bus,
                                         QDBusServiceWatcher.WatchForOwnerChange, self)
        self.watcher.serviceOwnerChanged.connect(lambda name, old, new: self.ownerChanged.emit(bool(new)))

    @property
    def destination(self):
        return self.bus.baseService() if self.bus.isConnected() else ""

    def register(self, path, receiver):
        return self.bus.registerObject(path, CALLBACK, receiver, QDBusConnection.ExportAllSlots)

    def unregister(self, path):
        self.bus.unregisterObject(path)

    def request(self, path, interface, method, args, callback):
        message = QDBusMessage.createMethodCall(SERVICE, path, interface, method)
        message.setArguments(args)
        message.setAutoStartService(False)
        watcher = QDBusPendingCallWatcher(self.bus.asyncCall(message, 5000), self)

        def finished(*_):
            reply = watcher.reply()
            error = reply.errorMessage() if reply.type() == QDBusMessage.ErrorMessage else None
            try:
                callback(reply.arguments(), error)
            finally:
                watcher.deleteLater()

        watcher.finished.connect(finished)


@dataclass
class _Session:
    token: str
    path: str
    name: str
    directory: tempfile.TemporaryDirectory


class KWinTrayBridge(QObject):
    minimized = Signal()
    failed = Signal(str)

    def __init__(self, parent=None, transport=None):
        super().__init__(parent)
        self.transport = transport or SessionBus(self)
        self.transport.ownerChanged.connect(self._owner_changed)
        self._enabled = False
        self._session = None

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if not enabled:
            self._stop()
        elif self._session is None:
            self._start()

    def _start(self):
        destination = self.transport.destination
        if not destination:
            self._failure("The session D-Bus connection is unavailable.")
            return
        token = uuid.uuid4().hex
        path = f"/org/tuxshelf/TrayObserver/s{token}"
        directory = None
        try:
            directory = tempfile.TemporaryDirectory(prefix="tuxshelf-kwin-")
            session = _Session(token, path, f"tuxshelf-tray-{os.getpid()}-{token}", directory)
            script = Path(directory.name) / "observer.js"
            script.write_text(render_observer(os.getpid(), destination, path, token), encoding="utf-8")
            if not self.transport.register(path, self):
                raise RuntimeError("Could not register TuxShelf's KWin callback.")
            self._session = session
            self.transport.request("/Scripting", SCRIPTING, "loadScript", [str(script), session.name],
                                   lambda values, error: self._loaded(session, values, error))
        except Exception as exc:
            if self._session is not None:
                self._stop()
            else:
                self.transport.unregister(path)
                if directory is not None:
                    directory.cleanup()
            self._failure(str(exc))

    def _loaded(self, session, values, error):
        if session is not self._session:
            self._unload(session)
            return
        if error or not values or type(values[0]) is not int or values[0] < 0:
            self._stop()
            self._failure(error or "KWin could not load its TuxShelf observer.")
            return
        try:
            self.transport.request(f"/Scripting/Script{values[0]}", "org.kde.kwin.Script", "run", [],
                                   lambda values, error: self._running(session, error))
        except Exception as exc:
            self._stop()
            self._failure(str(exc))

    def _running(self, session, error):
        if session is not self._session:
            self._unload(session)
        elif error:
            self._stop()
            self._failure(error)
        else:
            log.info("KWin minimize observer active for TuxShelf")

    @Slot(str, bool)
    def stateChanged(self, token, minimized):
        if self._enabled and self._session is not None and token == self._session.token and minimized:
            self.minimized.emit()

    def _unload(self, session):
        try:
            self.transport.request("/Scripting", SCRIPTING, "unloadScript", [session.name],
                                   lambda values, error: log.warning("KWin observer cleanup: %s", error) if error else None)
        except Exception:
            log.warning("Could not unload KWin observer", exc_info=True)

    def _stop(self):
        session, self._session = self._session, None
        if session is None:
            return
        self.transport.unregister(session.path)
        self._unload(session)
        try:
            session.directory.cleanup()
        except OSError:
            log.warning("Could not remove temporary KWin observer file", exc_info=True)

    def _owner_changed(self, present):
        self._stop()
        if present and self._enabled:
            self._start()

    def _failure(self, message):
        log.warning("KWin minimize observer unavailable: %s", message)
        self.failed.emit(message)
