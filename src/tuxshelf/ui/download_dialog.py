"""Repository download flow. Workers do network/file work; the UI owns preferences."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..core.discovery import ROOTS_KEY, _safe_path, default_roots, load_paths, save_paths
from ..core.downloads import download_application, download_choices, fetch_releases
from ..core.updates.installer import InstallCancelled
from ..core.updates.providers import parse_source
from .popups import RoundedComboBox


class AddSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = None
        self.setWindowTitle('Add application')
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel('Add application', objectName='title'))
        label = QLabel('Choose an application on your computer, or download one from a repository.',
                       objectName='subtitle')
        label.setWordWrap(True)
        layout.addWidget(label)
        for text, mode in [('Add a local file…', 'local'), ('Download from a link…', 'link')]:
            button = QPushButton(text, objectName='primary' if mode == 'local' else 'soft')
            button.clicked.connect(lambda checked=False, m=mode: self._choose(m))
            layout.addWidget(button)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _choose(self, mode):
        self.mode = mode
        self.accept()


class _Signals(QObject):
    done = Signal(object)
    progress = Signal(int, int)


class _Job(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.cancel = threading.Event()
        self.signals = _Signals()

    def run(self):
        try:
            result = self.action(self.cancel, self.signals.progress.emit)
        except Exception as exc:  # every completion must release the dialog's busy state
            result = exc
        self.signals.done.emit(result)


class DownloadApplicationDialog(QDialog):
    def __init__(self, service, parent=None, *, client=None, token=None):
        super().__init__(parent)
        self.service, self.client, self.token = service, client, token
        self.job = None
        self._closing = False
        self._downloading = False
        self._source = ''
        self._releases = []
        self.choices = []
        self.downloaded = None
        self.setWindowTitle('Download application')
        self.resize(780, min(640, self.screen().availableGeometry().height() - 80))
        self.setMinimumSize(580, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel('Download application', objectName='title'))
        hint = QLabel('Paste a GitHub, GitLab, Codeberg or self-hosted repository/release link. '
                      'Choose a file, download it, then review its library details.', objectName='subtitle')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.url_edit = QLineEdit(placeholderText='https://github.com/owner/repo')
        self.url_edit.textChanged.connect(self._source_changed)
        self.url_edit.returnPressed.connect(self.find_releases)
        self.find_btn = QPushButton('Find releases')
        self.find_btn.clicked.connect(self.find_releases)
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.find_btn)
        layout.addLayout(row)
        self.pre_cb = QCheckBox('Include pre-releases / nightly builds')
        self.pre_cb.toggled.connect(self._populate)
        layout.addWidget(self.pre_cb)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Release', 'File', 'Size'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._actions)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel('Download folder (shared with Discover applications)', objectName='sectionLabel'))
        folders = QHBoxLayout()
        self.folder_combo = RoundedComboBox()
        self.folder_combo.currentIndexChanged.connect(self._actions)
        self.folder_btn = QPushButton('Add folder…')
        self.folder_btn.clicked.connect(self.add_folder)
        folders.addWidget(self.folder_combo, 1)
        folders.addWidget(self.folder_btn)
        layout.addLayout(folders)
        self.folder_hint = QLabel(objectName='hint')
        self.folder_hint.setWordWrap(True)
        layout.addWidget(self.folder_hint)
        self.status = QLabel('Find releases to choose an AppImage or raw Linux executable.', objectName='hint')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        note = QLabel('Existing files are never overwritten. Nothing is run. A completed download '
                      'is kept if you cancel the final Add form. If the selected file already exists, '
                      'TuxShelf checks it and continues with it.', objectName='hint')
        note.setWordWrap(True)
        layout.addWidget(note)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.clicked.connect(self._cancel_clicked)
        self.download_btn = QPushButton('Download and continue', objectName='primary')
        self.download_btn.clicked.connect(self.start_download)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.download_btn)
        layout.addLayout(footer)
        self._load_folders()
        self._actions()

    def _load_folders(self, selected=None):
        self.folder_combo.clear()
        roots = load_paths(self.service.db, ROOTS_KEY, default_roots())
        for path in roots:
            if _safe_path(Path(path)) and Path(path).is_dir() and os.access(path, os.W_OK):
                self.folder_combo.addItem(path, path)
        if selected:
            self.folder_combo.setCurrentIndex(self.folder_combo.findData(selected))
        self.folder_hint.setText('Only existing writable discovery folders are listed.' if self.folder_combo.count()
                                else 'No writable discovery folders. Add a folder to store your applications.')

    def add_folder(self):
        if self.job:
            return
        path = QFileDialog.getExistingDirectory(self, 'Choose a folder to store applications', str(Path.home()))
        if not path:
            return
        root = Path(path)
        if not _safe_path(root) or not root.is_dir() or not os.access(root, os.W_OK):
            self.status.setText('Choose a writable folder without symlinks or backup directories.')
            return
        try:
            save_paths(self.service.db, ROOTS_KEY,
                       [*load_paths(self.service.db, ROOTS_KEY, default_roots()), path])
        except Exception as exc:
            self.status.setText(f'Could not save the download folder: {exc}')
            return
        self._load_folders(path)
        self._actions()

    def _source_changed(self):
        self._source, self._releases = '', []
        self.choices = []
        self.table.setRowCount(0)
        self._actions()

    def _actions(self):
        if not hasattr(self, 'download_btn'):
            return
        busy = self.job is not None
        for widget in (self.url_edit, self.pre_cb, self.table, self.folder_combo, self.folder_btn):
            widget.setEnabled(not busy)
        self.find_btn.setEnabled(not busy and parse_source(self.url_edit.text()) is not None)
        self.download_btn.setEnabled(not busy and bool(self.choices)
                                     and self.table.currentRow() >= 0 and self.folder_combo.currentData() is not None)
        self.cancel_btn.setText('Cancel download' if busy and self._downloading else 'Cancel search' if busy else 'Cancel')

    def find_releases(self):
        if self.job or parse_source(self.url_edit.text()) is None:
            return
        source = self.url_edit.text()
        self._source_changed()
        self._downloading = False
        self._start(_Job(lambda cancel, progress: fetch_releases(
            source, client=self.client, token=self.token, cancel=cancel)), 'Finding releases…')

    def _populate(self):
        self.choices = download_choices(self._source, self._releases, include_prereleases=self.pre_cb.isChecked())
        self.table.setRowCount(len(self.choices))
        for row, choice in enumerate(self.choices):
            release = choice.release.tag + (' (pre-release)' if choice.release.prerelease else '')
            size = f'{choice.asset.size / (1024 * 1024):.1f} MB' if choice.asset.size else 'Unknown'
            for col, text in enumerate((release, choice.asset.name, size)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
        if self.choices:
            self.table.selectRow(0)
            self.status.setText(f'{len(self.choices)} compatible release files. Select the file you want.')
        else:
            has_pre = any(r.prerelease and not r.draft for r in self._releases)
            self.status.setText('No compatible AppImage or raw Linux executable found. Archives/packages are excluded.'
                                + (' Try including pre-releases / nightly builds.' if has_pre and not self.pre_cb.isChecked() else ''))
        self._actions()

    def start_download(self):
        row = self.table.currentRow()
        folder = self.folder_combo.currentData()
        if self.job or not folder or not 0 <= row < len(self.choices):
            return
        choice = self.choices[row]
        self._downloading = True
        self._start(_Job(lambda cancel, progress: download_application(choice, folder, cancel=cancel,
                                                                       progress=progress)),
                    f'Checking {choice.asset.name}…' if os.path.lexists(Path(folder) / choice.asset.name)
                    else f'Downloading {choice.asset.name}…')

    def _start(self, job, message):
        self.job = job
        self.status.setText(message)
        self.progress.setRange(0, 0)
        self.progress.show()
        job.signals.done.connect(self._done)
        job.signals.progress.connect(self._progress)
        self._actions()
        QThreadPool.globalInstance().start(job)

    def _progress(self, done, total):
        self.progress.setRange(0, 1000 if total else 0)
        if total:
            self.progress.setValue(min(1000, int(done * 1000 / total)))
        self.status.setText(f'Preparing application… {done / (1024 * 1024):.1f} MB'
                            + (f' / {total / (1024 * 1024):.1f} MB' if total else ''))

    def _done(self, result):
        self.job = None
        self.progress.hide()
        if self._closing:
            super().reject()
            return
        if isinstance(result, Exception):
            self.status.setText('Cancelled. You can try again.' if isinstance(result, InstallCancelled) else str(result))
        elif self._downloading:
            self.downloaded = result
            self.accept()
        else:
            self._source, self._releases = result
            self._populate()
        self._actions()

    def _cancel_clicked(self):
        if self.job:
            self.job.cancel.set()
            self.status.setText('Cancelling… Waiting for the current request to finish.')
        else:
            self.reject()

    def reject(self):
        if self.job:
            self._closing = True
            self._cancel_clicked()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.job:
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
