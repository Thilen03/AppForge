"""Single-instance guard (Qt-free).

Only one AppForge may run per user (and per data directory).  The first instance takes an exclusive
``flock`` on a lock file and listens on a Unix socket; every later launch connects to that socket,
asks the running instance to come to the front, and exits.  The kernel drops the lock when the
process dies, so a crash can never leave AppForge "stuck as already running".
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Sequence

from .paths import data_dir

log = logging.getLogger(__name__)
_MAX_MESSAGE = 64 * 1024
_SUN_PATH_LIMIT = 100          # sockaddr_un.sun_path is ~108 bytes on Linux


def default_socket_path() -> str:
    """Per-user socket path, keyed on the data directory so separate data dirs never collide."""
    key = hashlib.sha1(str(data_dir().resolve()).encode("utf-8")).hexdigest()[:10]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        path = os.path.join(runtime, f"appforge-{key}.sock")
        if len(path.encode()) <= _SUN_PATH_LIMIT:
            return path
    return os.path.join(tempfile.gettempdir(), f"appforge-{os.getuid()}-{key}.sock")


class InstanceGuard:
    def __init__(self, lock_path: str | os.PathLike | None = None, socket_path: str | None = None):
        self.lock_path = Path(lock_path) if lock_path else data_dir() / "appforge.lock"
        self.socket_path = socket_path or default_socket_path()
        self._lock_fd: int | None = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._callback: Callable[[list[str]], None] | None = None

    # -- startup ------------------------------------------------------------------------
    def acquire(self, args: Sequence[str] = (), wait: float = 5.0) -> bool:
        """True: this process is the (only) running instance.

        False: another instance is running and has been asked to show its window; the caller
        should exit.  ``wait`` is how long to keep trying to reach an instance that is still starting.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:                                   # somebody else holds the lock
            os.close(fd)
            if self._notify_running(args, wait):
                return False
            log.warning("AppForge is already running but did not answer within %.0f s", wait)
            return False
        self._lock_fd = fd
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        try:
            self._bind()
        except OSError:
            log.warning("Couldn't open the single-instance socket %s", self.socket_path, exc_info=True)
        return True

    def _bind(self) -> None:
        try:
            os.unlink(self.socket_path)                   # stale socket of a crashed instance
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        srv.listen(8)
        srv.settimeout(0.5)
        self._server = srv

    def _notify_running(self, args: Sequence[str], wait: float) -> bool:
        message = json.dumps({"cmd": "show", "args": [str(a) for a in args]}).encode() + b"\n"
        deadline = time.monotonic() + wait
        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as cli:
                    cli.settimeout(2.0)
                    cli.connect(self.socket_path)
                    cli.sendall(message)
                    try:
                        cli.recv(16)                      # wait for the "ok" so we don't exit too early
                    except OSError:
                        pass
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.1)

    # -- serving ------------------------------------------------------------------------
    def serve(self, callback: Callable[[list[str]], None]) -> None:
        """Call ``callback(args)`` (on a helper thread!) whenever another launch asks us to show up."""
        self._callback = callback
        if self._server is None or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="appforge-instance", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()           # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2.0)
                    data = b""
                    while b"\n" not in data and len(data) < _MAX_MESSAGE:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    msg = json.loads(data.decode("utf-8", "replace").strip() or "{}")
                    args = [a for a in msg.get("args", []) if isinstance(a, str)]
                    if msg.get("cmd") == "show" and self._callback:
                        self._callback(args)
                    conn.sendall(b"ok\n")
                except Exception:  # noqa: BLE001 - a bad client must never kill the listener
                    log.debug("Ignoring a bad single-instance message", exc_info=True)

    # -- shutdown -----------------------------------------------------------------------
    def release(self) -> None:
        """Give the instance slot back (also called before restarting into a new version)."""
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
