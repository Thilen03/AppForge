"""Preview and explicitly import applications found in user-selected directories."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from ..core.discovery import (
    IGNORED_KEY, ROOTS_KEY, default_roots, import_candidate, load_paths, save_paths,
)
from ..core.library import LibraryError, normalize_path, normalize_repo
from ..core.formats.appimage_update import metadata_source, source_detection_message
from ..core.discovery_watch import WATCHED_KEY
from .icons import placeholder_pixmap
from .workers import DiscoveryJob


class _ResultItem(QTableWidgetItem):
    def __lt__(self, other):
        return self.text().casefold() < other.text().casefold()


class DiscoveryDialog(QDialog):
    preferencesChanged = Signal()

    def __init__(self, service, parent=None, *, preview=None):
        super().__init__(parent)
        self.service = service
        self.job = None
        self.candidates = []
        self._candidate_by_path = {}
        self._rendering = False
        self._closing = False
        self._importing = False
        self._cancel_import = False
        self._queue = []
        self._imported = 0
        self._failures = []
        self._source_choices = {}
        self._import_sources = {}
        self.ignored = set(load_paths(service.db, IGNORED_KEY))
        self.setWindowTitle("Discover applications")
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(QLabel("Discover applications", objectName="title"))
        hint = QLabel("Choose folders to scan. Check a folder to watch for new apps while TuxShelf is running. "
                      "Review the results and suggested update sources before importing. "
                      "Application files are never run or changed.", objectName="subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.roots = QListWidget(objectName="discoveryRoots")
        self.roots.setSpacing(2)
        self.roots.setMaximumHeight(126)
        watched = set(load_paths(service.db, WATCHED_KEY))
        for path in load_paths(service.db, ROOTS_KEY, default_roots()):
            self._add_root(path, path in watched)
        self.roots.itemChanged.connect(self._save_folders)
        layout.addWidget(self.roots)
        row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add folder…")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_folder_btn = QPushButton("Remove folder")
        self.remove_folder_btn.clicked.connect(self._remove_folder)
        self.defaults_btn = QPushButton("Default folders")
        self.defaults_btn.clicked.connect(self._defaults)
        self.scan_btn = QPushButton("Scan folders", objectName="primary")
        self.scan_btn.clicked.connect(self.start_scan)
        for button in (self.add_folder_btn, self.remove_folder_btn, self.defaults_btn, self.scan_btn):
            row.addWidget(button)
        layout.addLayout(row)
        self.search_edit = QLineEdit(placeholderText="Search scanned applications…")
        self.search_edit.setAccessibleName("Search scanned applications")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)
        self.result_count = QLabel("0 applications", objectName="hint")
        layout.addWidget(self.result_count)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Application", "Version", "Format", "Location", "Status", "Update source (editable)"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.setColumnWidth(5, 250)
        self.table.itemChanged.connect(lambda *_: self._actions())
        self.table.sortItems(0, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.model().layoutChanged.connect(self._filter_results)
        self.search_edit.textChanged.connect(self._filter_results)
        layout.addWidget(self.table, 1)
        choices = QHBoxLayout()
        self.select_btn = QPushButton("Select all")
        self.select_btn.clicked.connect(lambda: self._select(True))
        self.select_btn.setToolTip("Check all eligible applications in the visible results.")
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
        if preview is not None:
            self._scanned(preview)
            self.status.setText(f"{len(preview.candidates)} new apps found in watched folders. "
                                "Select applications to import; nothing has been added yet.")

    def _add_root(self, path, watched=False):
        item = QListWidgetItem(path)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if watched else Qt.Unchecked)
        item.setToolTip("Check to watch this folder and its subfolders for new apps.")
        self.roots.addItem(item)

    def _save_folders(self, *_):
        save_paths(self.service.db, ROOTS_KEY, self._roots())
        save_paths(self.service.db, WATCHED_KEY,
                   [self.roots.item(i).text() for i in range(self.roots.count())
                    if self.roots.item(i).checkState() == Qt.Checked])
        self.preferencesChanged.emit()

    def _remove_folder(self):
        if self.roots.currentRow() >= 0:
            self.roots.takeItem(self.roots.currentRow())
            self._save_folders()

    def _defaults(self):
        watched = set(load_paths(self.service.db, WATCHED_KEY))
        self.roots.clear()
        for path in default_roots():
            self._add_root(path, path in watched)
        self._save_folders()

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if path:
            norm = normalize_path(path)
            if norm not in self._roots():
                self._add_root(norm)
                self._save_folders()

    def _roots(self):
        return [self.roots.item(i).text() for i in range(self.roots.count())]

    def _eligible(self, c):
        return not c.registered and not c.ignored

    def _rows(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                candidate = self._candidate_by_path.get(item.data(Qt.UserRole))
                if candidate is not None:
                    yield row, candidate

    def _visible_eligible(self):
        return [c for row, c in self._rows() if not self.table.isRowHidden(row) and self._eligible(c)]

    def _selected(self):
        return [c for row, c in self._rows() if not self.table.isRowHidden(row) and self._eligible(c)
                and self.table.item(row, 0).checkState() == Qt.Checked]

    def _filter_results(self, *_):
        if self._rendering:
            return
        query = self.search_edit.text().strip().casefold()
        shown = 0
        for row in range(self.table.rowCount()):
            text = " ".join(self.table.item(row, col).text() for col in range(self.table.columnCount())
                            if self.table.item(row, col) is not None)
            matches = not query or query in text.casefold()
            self.table.setRowHidden(row, not matches)
            shown += int(matches)
        total = self.table.rowCount()
        self.result_count.setText(f"Showing {shown} of {total} applications" if shown or not query
                                  else f"No matching applications · {total} scanned")
        self.import_all_btn.setText("Import all matching" if query else "Import all eligible")
        self._actions()

    def _source_changed(self, path, value):
        self._source_choices[path] = value
        for row, c in self._rows():
            if c.path == path:
                # The backing item follows its editor when Qt sorts the rows.
                self.table.item(row, 5).setText(value)
                break
        self._filter_results()

    def _actions(self):
        busy = self.job is not None or self._importing
        for widget in (self.roots, self.add_folder_btn, self.remove_folder_btn, self.defaults_btn,
                       self.scan_btn, self.search_edit, self.table, self.select_btn, self.clear_btn,
                       self.reset_ignore_btn, self.desktop_cb):
            widget.setEnabled(not busy)
        selected = bool(self._selected())
        self.import_btn.setEnabled(not busy and selected)
        self.ignore_btn.setEnabled(not busy and selected)
        self.import_all_btn.setEnabled(not busy and bool(self._visible_eligible()))
        self.cancel_btn.setVisible(busy)

    def start_scan(self):
        if self.job is not None or self._importing:
            return
        roots = self._roots()
        if not roots:
            self.status.setText("Add at least one folder first.")
            return
        self._save_folders()
        self.candidates = []
        self._candidate_by_path.clear()
        self._source_choices.clear()
        self.table.setRowCount(0)
        self._filter_results()
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
        self._candidate_by_path = {c.path: c for c in self.candidates}
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
        checked = {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())
                   if self.table.item(row, 0) is not None
                   and self.table.item(row, 0).checkState() == Qt.Checked}
        self._rendering = True
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self.candidates))
        for row, c in enumerate(self.candidates):
            md = c.metadata
            kind = "AppImage" if md.format_id == "appimage" else (
                "Script" if md.extra.get("executable_kind") == "script" else "ELF binary")
            status = "Already registered" if c.registered else "Ignored" if c.ignored else "New"
            for col, value in enumerate((md.name_suggestion, md.version or "Unknown", kind, c.path, status)):
                item = _ResultItem(value)
                item.setToolTip("\n".join(md.warnings) if col == 0 else value)
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setData(Qt.UserRole, c.path)
                    item.setCheckState(Qt.Checked if c.path in checked and self._eligible(c) else Qt.Unchecked)
                    pixmap = QPixmap()
                    if md.icon_data:
                        pixmap.loadFromData(md.icon_data)
                    if pixmap.isNull():
                        pixmap = placeholder_pixmap(md.name_suggestion, 32)
                    item.setIcon(QIcon(pixmap))
                    if not self._eligible(c):
                        item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsUserCheckable)
                self.table.setItem(row, col, item)
            source = QLineEdit(self._source_choices.get(c.path, metadata_source(md) or ""))
            source.setCursorPosition(0)
            source.setPlaceholderText("No source detected" if md.format_id == "appimage" and not metadata_source(md)
                                      else "Optional repository URL")
            source.setAccessibleName(f"Update source for {md.name_suggestion}")
            source.setToolTip((source.text() + "\n" if source.text() else "") +
                              (source_detection_message(md) if md.format_id == "appimage" else
                               "Optional repository URL. Review, change or clear before importing."))
            source.setEnabled(self._eligible(c))
            source.textChanged.connect(
                lambda value, path=c.path: self._source_changed(path, value))
            self.table.setItem(row, 5, _ResultItem(source.text()))
            self.table.setCellWidget(row, 5, source)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self._rendering = False
        self._filter_results()

    def _select(self, checked):
        blocked = self.table.blockSignals(True)
        for row, c in self._rows():
            if not self.table.isRowHidden(row) and self._eligible(c):
                self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(blocked)
        self._actions()

    def _ignore(self):
        for c in self._selected():
            c.ignored = True
            self.ignored.add(c.path)
        save_paths(self.service.db, IGNORED_KEY, self.ignored)
        self.preferencesChanged.emit()
        self._render()
        self._actions()

    def _reset_ignored(self):
        self.ignored.clear()
        save_paths(self.service.db, IGNORED_KEY, [])
        self.preferencesChanged.emit()
        for c in self.candidates:
            c.ignored = False
        self._render()
        self._actions()

    def _import(self, all_eligible):
        if self.job is not None or self._importing:
            return
        chosen = self._visible_eligible() if all_eligible else self._selected()
        if not chosen:
            return
        try:
            sources = {c.path: normalize_repo(self._source_choices.get(
                c.path, metadata_source(c.metadata) or "")) for c in chosen}
        except LibraryError as exc:
            self.status.setText(f"Check the update sources before importing: {exc}")
            return
        answer = QMessageBox.question(self, "Import applications?",
            f"Add {len(chosen)} applications to your library? Their files will stay where they are.\n"
            "The update sources shown in the preview will be saved. Clear or change them before importing if needed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._queue = list(chosen)
        self._import_sources = sources
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
            entry = import_candidate(self.service, c, integrate_desktop=self.desktop_cb.isChecked(),
                                     github_repo=self._import_sources.get(c.path))
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
