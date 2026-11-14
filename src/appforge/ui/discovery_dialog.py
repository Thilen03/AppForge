"""Preview and explicitly import applications found in user-selected directories."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMessageBox, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from ..core.discovery import (
    IGNORED_KEY, ROOTS_KEY, default_roots, import_candidate, load_paths, save_paths,
)
from ..core.library import LibraryError, normalize_path
from .icons import placeholder_pixmap
from .workers import DiscoveryJob


class DiscoveryDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.job = None
        self.candidates = []
        self._closing = False
        self._importing = False
        self._cancel_import = False
        self._queue = []
        self._imported = 0
        self._failures = []
        self.ignored = set(load_paths(service.db, IGNORED_KEY))
        self.setWindowTitle("Discover applications")
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(QLabel("Discover applications", objectName="title"))
        hint = QLabel("Choose folders to scan. Review the results before importing. "
                      "Application files are never run or changed.", objectName="subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.roots = QListWidget()
        self.roots.setMaximumHeight(110)
        self.roots.addItems(load_paths(service.db, ROOTS_KEY, default_roots()))
        layout.addWidget(self.roots)
        row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add folder…")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_folder_btn = QPushButton("Remove folder")
        self.remove_folder_btn.clicked.connect(lambda: self.roots.takeItem(self.roots.currentRow()))
        self.defaults_btn = QPushButton("Default folders")
        self.defaults_btn.clicked.connect(self._defaults)
        self.scan_btn = QPushButton("Scan folders", objectName="primary")
        self.scan_btn.clicked.connect(self.start_scan)
        for button in (self.add_folder_btn, self.remove_folder_btn, self.defaults_btn, self.scan_btn):
            row.addWidget(button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Application", "Version", "Format", "Location", "Status"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda *_: self._actions())
        layout.addWidget(self.table, 1)
        choices = QHBoxLayout()
        self.select_btn = QPushButton("Select all")
        self.select_btn.clicked.connect(lambda: self._select(True))
        self.clear_btn = QPushButton("Select none")
        self.clear_btn.clicked.connect(lambda: self._select(False))
        self.ignore_btn = QPushButton("Ignore selected")
        self.ignore_btn.clicked.connect(self._ignore)
        self.reset_ignore_btn = QPushButton("Reset ignored files")
        self.reset_ignore_btn.clicked.connect(self._reset_ignored)
        for button in (self.select_btn, self.clear_btn, self.ignore_btn, self.reset_ignore_btn):
            choices.addWidget(button)
        layout.addLayout(choices)
        self.status = QLabel("Ready to scan.", objectName="hint")
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
        self.desktop_cb = QCheckBox("Add imported applications to the application menu")
        self.desktop_cb.setChecked(service.desktop_default())
        layout.addWidget(self.desktop_cb)
        footer = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel scan")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        self.import_all_btn = QPushButton("Import all eligible")
        self.import_all_btn.clicked.connect(lambda: self._import(True))
        self.import_btn = QPushButton("Import selected", objectName="primary")
        self.import_btn.clicked.connect(lambda: self._import(False))
        for button in (self.cancel_btn, self.close_btn, self.import_all_btn, self.import_btn):
            footer.addWidget(button)
        layout.addLayout(footer)
        self._actions()

    def _defaults(self):
        self.roots.clear()
        self.roots.addItems(default_roots())

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if path:
            norm = normalize_path(path)
            if norm not in self._roots():
                self.roots.addItem(norm)

    def _roots(self):
        return [self.roots.item(i).text() for i in range(self.roots.count())]

    def _eligible(self, c):
        return not c.registered and not c.ignored

    def _selected(self):
        return [c for i, c in enumerate(self.candidates) if self._eligible(c)
                and self.table.item(i, 0).checkState() == Qt.Checked]

    def _actions(self):
        busy = self.job is not None or self._importing
        for widget in (self.roots, self.add_folder_btn, self.remove_folder_btn, self.defaults_btn,
                       self.scan_btn, self.table, self.select_btn, self.clear_btn,
                       self.reset_ignore_btn, self.desktop_cb):
            widget.setEnabled(not busy)
        selected = bool(self._selected())
        self.import_btn.setEnabled(not busy and selected)
        self.ignore_btn.setEnabled(not busy and selected)
        self.import_all_btn.setEnabled(not busy and any(self._eligible(c) for c in self.candidates))
        self.cancel_btn.setVisible(busy)

    def start_scan(self):
        if self.job is not None or self._importing:
            return
        roots = self._roots()
        if not roots:
            self.status.setText("Add at least one folder first.")
            return
        save_paths(self.service.db, ROOTS_KEY, roots)
        self.candidates = []
        self.table.setRowCount(0)
        self.errors.hide()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_btn.setText("Cancel scan")
        self.status.setText("Scanning folders…")
        self.job = DiscoveryJob(roots, [e.path for e in self.service.list_applications()], self.ignored)
        self.job.signals.progress.connect(self._progress)
        self.job.signals.done.connect(self._scanned)
        self._actions()
        QThreadPool.globalInstance().start(self.job)

    def _progress(self, count, path):
        self.status.setText(f"Inspected {count} files" + (f" · {path}" if path else ""))

    def _scanned(self, result):
        self.job = None
        self.candidates = result.candidates
        self._render()
        self.progress.hide()
        state = "Scan cancelled" if result.cancelled else "Scan complete"
        self.status.setText(f"{state}: {result.visited} files inspected, "
                            f"{len(result.candidates)} applications found. "
                            "Select applications to import; nothing has been added yet.")
        self.errors.setPlainText("\n".join(result.errors))
        self.errors.setVisible(bool(result.errors))
        self._actions()
        if self._closing:
            super().reject()

    def _render(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.candidates))
        for row, c in enumerate(self.candidates):
            md = c.metadata
            kind = "AppImage" if md.format_id == "appimage" else (
                "Script" if md.extra.get("executable_kind") == "script" else "ELF binary")
            status = "Already registered" if c.registered else "Ignored" if c.ignored else "New"
            for col, value in enumerate((md.name_suggestion, md.version or "Unknown", kind, c.path, status)):
                item = QTableWidgetItem(value)
                item.setToolTip("\n".join(md.warnings) if col == 0 else value)
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    pixmap = QPixmap()
                    if md.icon_data:
                        pixmap.loadFromData(md.icon_data)
                    if pixmap.isNull():
                        pixmap = placeholder_pixmap(md.name_suggestion, 32)
                    item.setIcon(QIcon(pixmap))
                    if not self._eligible(c):
                        item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsUserCheckable)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)

    def _select(self, checked):
        for row, c in enumerate(self.candidates):
            if self._eligible(c):
                self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._actions()

    def _ignore(self):
        for c in self._selected():
            c.ignored = True
            self.ignored.add(c.path)
        save_paths(self.service.db, IGNORED_KEY, self.ignored)
        self._render()
        self._actions()

    def _reset_ignored(self):
        self.ignored.clear()
        save_paths(self.service.db, IGNORED_KEY, [])
        for c in self.candidates:
            c.ignored = False
        self._render()
        self._actions()

    def _import(self, all_eligible):
        if self.job is not None or self._importing:
            return
        chosen = [c for c in self.candidates if self._eligible(c)] if all_eligible else self._selected()
        if not chosen:
            return
        answer = QMessageBox.question(self, "Import applications?",
            f"Add {len(chosen)} applications to your library? Their files will stay where they are.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._queue = list(chosen)
        self._import_total = len(chosen)
        self._imported, self._failures = 0, []
        self._importing = True
        self._cancel_import = False
        self.progress.setRange(0, len(chosen))
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.setText("Stop importing")
        self._actions()
        QTimer.singleShot(0, self._import_next)

    def _import_next(self):
        if not self._queue or self._cancel_import:
            self._importing = False
            self.progress.hide()
            self.status.setText(f"Imported {self._imported}; failed or skipped {len(self._failures)}; "
                                f"not processed {len(self._queue)}.")
            self.errors.setPlainText("\n".join(self._failures))
            self.errors.setVisible(bool(self._failures))
            self._render()
            self._actions()
            if self._closing:
                super().reject()
            return
        c = self._queue.pop(0)
        try:
            entry = import_candidate(self.service, c, integrate_desktop=self.desktop_cb.isChecked())
            c.registered = True
            self._imported += 1
            if self.desktop_cb.isChecked() and not self.service.desktop_enabled(entry):
                self._failures.append(f"{c.path}: imported, but its desktop launcher could not be created.")
        except (LibraryError, OSError, sqlite3.Error) as exc:
            self._failures.append(f"{c.path}: {exc}")
        self.progress.setValue(self._import_total - len(self._queue))
        self.status.setText(f"Importing applications… {self._import_total - len(self._queue)}/{self._import_total}")
        QTimer.singleShot(0, self._import_next)

    def _cancel(self):
        if self.job is not None:
            self.job.cancel.set()
            self.status.setText("Cancelling after the current file…")
        self._cancel_import = True

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
            event.accept()
