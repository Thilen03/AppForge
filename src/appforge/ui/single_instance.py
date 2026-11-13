"""Only one AppForge per user: a second start hands over to the running one and exits.

A lock file (``QLockFile``, stale-lock aware) decides who is the primary instance; a local socket
lets a later start tell the primary to come to the front (also out of the tray or the minimized
state). The names are derived from the data directory, so a throw-away data dir (tests, portable
setups) gets its own, independent instance.
"""
from __future__ import annotations

import hashlib
import logging

from PySide6.QtCore import QFile, QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ..core.paths import data_dir

log = logging.getLogger(__name__)
_MESSAGE = b"show\n"


class SingleInstance(QObject):
    activateRequested = Signal()            # another start asked us to show the window

    def __init__(self, parent=None):
        super().__init__(parent)
        base = data_dir()
        digest = hashlib.sha1(str(base).encode()).hexdigest()[:12]
        self._socket_name = f"appforge-{digest}"
        self._lock_path = str(base / "appforge.lock")
        self._lock = QLockFile(self._lock_path)
        self._lock.setStaleLockTime(0)       # a lock is stale as soon as its process is gone
        self._server: QLocalServer | None = None

    # -- public -------------------------------------------------------------------------
    def acquire(self, connect_timeout_ms: int = 3000) -> bool:
        """True: we are the primary instance. False: another one was told to show itself."""
        if self._become_primary():
            return True
        if self._notify_primary(connect_timeout_ms):
            return False
        # The lock is held but nobody answers: a leftover from a crash (or a recycled PID). Take over.
        log.warning("AppForge lock held but no instance answered; taking it over")
        QFile.remove(self._lock_path)
        return self._become_primary()

    def release(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            try:
                server.newConnection.disconnect(self._on_connection)
            except (RuntimeError, TypeError):
                pass
            server.close()
            server.setParent(None)
            server.deleteLater()
        self._lock.unlock()

    # -- internals ----------------------------------------------------------------------
    def _become_primary(self) -> bool:
        if not self._lock.tryLock(0):
            return False
        QLocalServer.removeServer(self._socket_name)          # stale socket file of a crashed run
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.UserAccessOption)
        if not server.listen(self._socket_name):
            log.warning("Single-instance socket failed: %s", server.errorString())
            self._lock.unlock()
            return False
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _notify_primary(self, timeout_ms: int) -> bool:
        sock = QLocalSocket()
        waited, step = 0, 250
        while waited <= timeout_ms:            # the primary may still be starting up: retry briefly
            sock.connectToServer(self._socket_name)
            if sock.waitForConnected(step):
                sock.write(_MESSAGE)
                sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()
                return True
            waited += step
        return False

    def _on_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.readyRead.connect(lambda c=conn: self._read(c))
            conn.disconnected.connect(conn.deleteLater)
            if conn.bytesAvailable():
                self._read(conn)

    def _read(self, conn: QLocalSocket) -> None:
        data = bytes(conn.readAll())
        if data.strip():
            self.activateRequested.emit()
