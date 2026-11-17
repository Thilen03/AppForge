"""Download a custom icon without blocking the Add/Edit form."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout

from ..core.icon_download import MAX_ICON_BYTES, IconDownloadError, download_icon


class _Signals(QObject):
    done = Signal(object)
    progress = Signal(int, int)


class _Download(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cancel = Event()
        self.signals = _Signals()

    def run(self):
        try:
            result = download_icon(self.url, self.cancel, self.signals.progress.emit)
        except IconDownloadError as exc:
            result = str(exc)
        self.signals.done.emit(result)


class IconUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image from a link")
        self.resize(460, 220)
        self.image = None
        self._job = None
        self._cancelled = False
        layout = QVBoxLayout(self)
        hint = QLabel("Paste a direct image link (HTTP or HTTPS, up to 10 MB).")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/icon.png")
        layout.addWidget(self.url_edit)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.download_btn = QPushButton("Download")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._start)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.download_btn)
        layout.addLayout(buttons)

    def _start(self):
        if self._job:
            return
        self._cancelled = False
        self.download_btn.setEnabled(False)
        self.url_edit.setEnabled(False)
        self.status.setText("Downloading image…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self._job = _Download(self.url_edit.text())
        self._job.signals.done.connect(self._finished)
        self._job.signals.progress.connect(self._progress)
        QThreadPool.globalInstance().start(self._job)

    def _progress(self, received, total):
        if self._cancelled:
            return
        self.progress.setRange(0, total if total else 0)
        self.progress.setValue(received)

    def _finished(self, result):
        self._job = None
        if self._cancelled:
            return
        self.progress.hide()
        self.download_btn.setEnabled(True)
        self.url_edit.setEnabled(True)
        if isinstance(result, str):
            self.status.setText(result)
            return
        buffer = QBuffer()
        buffer.setData(QByteArray(result))
        buffer.open(QIODevice.ReadOnly)
        reader = QImageReader(buffer)
        if not reader.canRead():
            self.status.setText("That link didn't return a readable image. Use a direct image link, not a web page.")
            return
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 16_000_000:
            self.status.setText("Choose a readable image with no more than 16 million pixels.")
            return
        image = reader.read()
        if image.isNull():
            self.status.setText("That link didn't return a readable image. Use a direct image link, not a web page.")
            return
        # Normalize downloaded content instead of trusting a URL's extension or MIME type.
        self.image = image
        self.accept()

    def reject(self):
        self._cancelled = True
        if self._job:
            self._job.cancel.set()
        super().reject()


def choose_icon_url(parent) -> str | None:
    dialog = IconUrlDialog(parent)
    try:
        if dialog.exec() != QDialog.Accepted:
            return None
        # Keep previews available until their owning Add/Edit dialog is discarded.
        if not hasattr(parent, "_downloaded_icons"):
            parent._downloaded_icons = TemporaryDirectory(prefix="tuxshelf-icons-")
        from uuid import uuid4
        path = Path(parent._downloaded_icons.name) / f"{uuid4().hex}.png"
        if not dialog.image.save(str(path), "PNG"):
            raise OSError("Could not save the downloaded image.")
        if path.stat().st_size > MAX_ICON_BYTES:
            path.unlink()
            raise OSError("The converted image exceeds 10 MB.")
        return str(path)
    finally:
        dialog.deleteLater()
