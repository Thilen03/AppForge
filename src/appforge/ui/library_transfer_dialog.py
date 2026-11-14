"""Review portable configuration before registration; all SQLite work stays in Qt."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)

from ..core.library_transfer import (
    PreparedImport, TransferCancelled, export_library, prepare_import, preview_import, read_export,
)


class TransferSignals(QObject):
    done = Signal(object)
    progress = Signal(int, int)


class TransferJob(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function, self.args, self.kwargs = function, args, kwargs
        self.cancel = threading.Event()
        self.signals = TransferSignals()

    def run(self):
        try:
            result = self.function(*self.args, cancel=self.cancel, **self.kwargs)
        except Exception as exc:
            result = exc
        self.signals.done.emit(result)


def load_preview(path, existing, *, cancel, progress):
    return preview_import(read_export(path, cancel=cancel, progress=progress), existing,
                          cancel=cancel, progress=progress)


class LibraryTransferDialog(QDialog):
    libraryChanged = Signal()

    def __init__(self, service, mode='import', parent=None):
        super().__init__(parent)
        self.service, self.mode = service, mode
        self.job = None
        self.candidates = []
        self._queue = []
        self._importing = False
        self._closing = False
        self._stopping = False
        self.imported = self.missing = self.duplicates = self.failed = 0
        self.warnings = []
        self._selected_total = 0
        self._done_count = 0
        self._current = None
        self.setWindowTitle('Export Library' if mode == 'export' else 'Import Library')
        self.resize(940 if mode == 'import' else 640, 640 if mode == 'import' else 310)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(QLabel(self.windowTitle(), objectName='title'))
        hint = QLabel(
            'Save application configuration and icons as JSON. Application files, backups, '
            'download links and AppForge access tokens are excluded.' if mode == 'export' else
            'Choose an AppForge JSON export, review the applications and select what to import. '
            'Existing entries stay unchanged. Missing files can be reconnected with Locate file…',
            objectName='hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.choose_btn = QPushButton('Choose JSON…')
        self.choose_btn.clicked.connect(self.choose_file)
        self.choose_btn.setVisible(mode == 'import')
        layout.addWidget(self.choose_btn)
        self.file_label = QLabel()
        self.file_label.setTextFormat(Qt.PlainText)
        self.file_label.setWordWrap(True)
        self.file_label.hide()
        layout.addWidget(self.file_label)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Application', 'Version', 'Format', 'Location', 'Menu', 'Status'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.horizontalHeader().resizeSection(5, 280)
        self.table.horizontalHeader().setMaximumSectionSize(380)
        self.table.setWordWrap(False)
        self.table.itemChanged.connect(self._actions)
        self.table.setVisible(mode == 'import')
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.select_btn = QPushButton('Select all eligible')
        self.none_btn = QPushButton('Select none')
        self.select_btn.clicked.connect(lambda: self._select(True))
        self.none_btn.clicked.connect(lambda: self._select(False))
        for button in (self.select_btn, self.none_btn):
            button.setVisible(mode == 'import')
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.ids_cb = QCheckBox('Assign new IDs to conflicting entries (import as separate applications)')
        self.ids_cb.setVisible(mode == 'import')
        self.ids_cb.toggled.connect(self._render)
        layout.addWidget(self.ids_cb)
        self.launchers_cb = QCheckBox('Restore exported application-menu preferences')
        self.launchers_cb.setChecked(True)
        self.launchers_cb.setVisible(mode == 'import')
        layout.addWidget(self.launchers_cb)
        self.environment_cb = QCheckBox('Include environment variables (values may contain credentials)'
                                        if mode == 'export' else
                                        'Restore environment variables from this file (review values first)')
        self.environment_cb.setToolTip('Disabled by default. Review the JSON before restoring environment variables; '
                                      'they affect future launches. AppForge access tokens are never exported.')
        layout.addWidget(self.environment_cb)
        self.status = QLabel(f'Ready to export {len(service.list_applications())} applications.'
                             if mode == 'export' else 'Choose a library export to preview.')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.errors = QTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(100)
        self.errors.hide()
        layout.addWidget(self.errors)
        footer = QHBoxLayout()
        self.cancel_btn = QPushButton('Cancel operation')
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        footer.addWidget(self.cancel_btn)
        footer.addStretch()
        self.close_btn = QPushButton('Close')
        self.close_btn.clicked.connect(self.reject)
        footer.addWidget(self.close_btn)
        self.go_btn = QPushButton('Export JSON…' if mode == 'export' else 'Import selected', objectName='primary')
        self.go_btn.clicked.connect(self.export if mode == 'export' else self.start_import)
        footer.addWidget(self.go_btn)
        layout.addLayout(footer)
        self._actions()

    def _eligible(self, candidate):
        return (not candidate.duplicate and not candidate.invalid_file and not candidate.imported
                and (not candidate.id_conflict or self.ids_cb.isChecked()))

    def _selected(self):
        return [c for row, c in enumerate(self.candidates) if self._eligible(c)
                and self.table.item(row, 0).checkState() == Qt.Checked]

    def _actions(self, *_):
        busy = self.job is not None or self._importing
        for widget in (self.choose_btn, self.table, self.select_btn, self.none_btn,
                       self.ids_cb, self.environment_cb, self.launchers_cb):
            widget.setEnabled(not busy)
        self.go_btn.setEnabled(not busy and (self.mode == 'export' or bool(self._selected())))
        self.cancel_btn.setVisible(busy)

    def _select(self, checked):
        self.table.blockSignals(True)
        for row, candidate in enumerate(self.candidates):
            if self._eligible(candidate):
                self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self._actions()

    def _render(self, *_):
        checked = {id(c) for row, c in enumerate(self.candidates)
                   if row < self.table.rowCount() and self.table.item(row, 0)
                   and self.table.item(row, 0).checkState() == Qt.Checked}
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.candidates))
        for row, candidate in enumerate(self.candidates):
            record = candidate.record
            status = 'Imported' if candidate.imported else candidate.status
            if candidate.id_conflict and self.ids_cb.isChecked() and not candidate.imported:
                status = status.replace('ID conflict — choose new IDs to import', 'ID conflict — will assign new ID')
            kind = 'AppImage' if record['format'] == 'appimage' else (
                'Script' if record['metadata'].get('executable_kind') == 'script' else 'Executable')
            values = (record['name'], record['installed_version'] or 'Unknown', kind,
                      record['path'], 'Yes' if record['metadata'].get('desktop_entry') else 'No', status)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if id(candidate) in checked and self._eligible(candidate) else Qt.Unchecked)
                    if not self._eligible(candidate):
                        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsEnabled)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self._actions()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose library export', '', 'JSON files (*.json)')
        if path:
            self.load_file(path)

    def _start_job(self, job, callback):
        self.job = job
        job.signals.done.connect(callback)
        job.signals.progress.connect(self._progress)
        self.progress.show()
        self.progress.setRange(0, 0)
        self._actions()
        QThreadPool.globalInstance().start(job)

    def load_file(self, path):
        if self.job is not None or self._importing:
            return
        self.candidates = []
        self.table.setRowCount(0)
        self.file_label.setText(str(path))
        self.file_label.show()
        self.errors.hide()
        self.status.setText('Reading export and checking application paths…')
        job = TransferJob(load_preview, path, deepcopy(self.service.list_applications()), progress=lambda *_: None)
        job.kwargs['progress'] = job.signals.progress.emit
        self._start_job(job, self._preview_done)

    def _progress(self, done, total):
        if not self._importing:
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(done)

    def _preview_done(self, result):
        self.job = None
        self.progress.hide()
        if self._closing:
            super().reject()
            return
        if isinstance(result, Exception):
            self.status.setText(str(result))
        else:
            self.candidates = result
            duplicates = sum(c.duplicate for c in result)
            missing = sum(c.fingerprint is None and not c.duplicate for c in result)
            self.status.setText(f'{len(result)} applications; {duplicates} duplicate files; {missing} missing or unavailable. '
                                'Select applications to import. Nothing has been added yet.')
            self._render()
        self._actions()

    def export(self):
        if self.job is not None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export library', 'AppForge-library.json', 'JSON files (*.json)')
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
            if Path(path).exists() and QMessageBox.question(
                    self, 'Replace existing export?', f'Replace {path}?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        self.errors.hide()
        self.status.setText('Exporting library…')
        entries = deepcopy(self.service.list_applications())
        job = TransferJob(export_library, entries, path, protected=[self.service.db.path],
                          include_environment=self.environment_cb.isChecked(), progress=lambda *_: None)
        job.kwargs['progress'] = job.signals.progress.emit
        self._export_count = len(entries)
        self._export_path = path
        self._start_job(job, self._export_done)

    def _export_done(self, result):
        self.job = None
        self.progress.hide()
        if isinstance(result, Exception):
            self.status.setText(str(result))
        else:
            self.status.setText(f'Exported {self._export_count} applications to {self._export_path}.')
            self.errors.setPlainText('\n'.join(result))
            self.errors.setVisible(bool(result))
        self._actions()
        if self._closing:
            super().reject()

    def start_import(self):
        if self.job is not None or self._importing:
            return
        chosen = self._selected()
        if not chosen:
            return
        if QMessageBox.question(self, 'Import selected applications?',
                                f'Add {len(chosen)} applications? Existing entries stay unchanged. '
                                'Application files will not be run or modified.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._queue = list(chosen)
        self._selected_total = len(chosen)
        self._done_count = 0
        self._importing, self._stopping = True, False
        self.imported = self.missing = self.duplicates = self.failed = 0
        self.warnings = []
        self.errors.hide()
        self._actions()
        self._next()

    def _next(self):
        if self._stopping or not self._queue:
            self._finish_import()
            return
        candidate = self._queue.pop(0)
        self._current = candidate
        self.status.setText(f'Importing {self._done_count + 1}/{self._selected_total}: {candidate.record["name"]}')
        job = TransferJob(prepare_import, deepcopy(candidate), deepcopy(self.service.list_applications()),
                          self.service.icons_dir, new_ids=self.ids_cb.isChecked(),
                          environment=self.environment_cb.isChecked(), launchers=self.launchers_cb.isChecked())
        self._start_job(job, self._record_prepared)
        self.progress.setRange(0, self._selected_total)
        self.progress.setValue(self._done_count)

    def _cleanup_icon(self, prepared):
        if prepared.icon_path:
            try:
                Path(prepared.icon_path).unlink(missing_ok=True)
            except OSError as exc:
                self.warnings.append(f'Could not remove unused imported icon: {exc}')

    def _record_prepared(self, result):
        self.job = None
        self._done_count += 1
        if isinstance(result, PreparedImport):
            if self._stopping:
                self._cleanup_icon(result)
                self._queue.insert(0, self._current)
            else:
                try:
                    self.service.import_configuration(result)
                except Exception as exc:
                    self._cleanup_icon(result)
                    self._failed_record(exc)
                else:
                    self.imported += 1
                    self.missing += int(result.missing)
                    self.warnings.extend(result.warnings)
                    self._current.imported = True
                    self.libraryChanged.emit()
        elif isinstance(result, TransferCancelled):
            self._queue.insert(0, self._current)
        else:
            self._failed_record(result)
        self._next()

    def _failed_record(self, error):
        if 'Duplicate file' in str(error):
            self.duplicates += 1
        else:
            self.failed += 1
        self.warnings.append(f'{self._current.record["name"]}: {error}')

    def _finish_import(self):
        self._importing = False
        self.progress.hide()
        duplicate_total = sum(c.duplicate for c in self.candidates) + self.duplicates
        skipped = len(self.candidates) - self.imported - self.failed - self.duplicates
        self.status.setText(f'Imported {self.imported} ({self.missing} missing/unavailable); '
                            f'skipped {skipped + self.duplicates} ({duplicate_total} duplicates); '
                            f'failed {self.failed}; not processed from selection {len(self._queue)}.')
        self.errors.setPlainText('\n'.join(self.warnings))
        self.errors.setVisible(bool(self.warnings))
        self._render()
        if self._closing:
            super().reject()

    def _cancel(self):
        self._stopping = True
        if self.job:
            self.job.cancel.set()
        self.status.setText('Stopping… Completed imports will be kept.')

    def reject(self):
        if self.job is not None or self._importing:
            self._closing = True
            self._cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.job is not None or self._importing:
            self._closing = True
            self._cancel()
            event.ignore()
        else:
            super().closeEvent(event)
