"""Backups & rollback dialog for one application."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)

from ..core.backups import MAX_KEEP, BackupRecord, BackupService
from ..core.library import LibraryError
from ..core.models import AppEntry


def _size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} KB"


class BackupsDialog(QDialog):
    """Lists the saved versions of an app; restore, delete and retention are handled here.

    ``changed`` is True when the installed version was replaced, so the caller can refresh.
    """

    def __init__(self, backups: BackupService, entry: AppEntry, parent=None):
        super().__init__(parent)
        self.backups, self.entry = backups, entry
        self.changed = False
        self.setWindowTitle("Backups & rollback")
        self.setFixedSize(560, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Backups & rollback", objectName="title"))
        self.sub = QLabel(objectName="subtitle")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

        self.notice = QLabel(objectName="hint")
        self.notice.setWordWrap(True)
        self.notice.hide()
        lay.addWidget(self.notice)

        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._sync_buttons)
        self.list.itemDoubleClicked.connect(lambda *_: self._restore())
        lay.addWidget(self.list, 1)

        self.empty = QLabel("No backups yet. When AppForge updates this app, the version it replaces "
                            "is kept here so you can go back to it.", objectName="subtitle")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty, 1)

        self.total = QLabel(objectName="hint")
        lay.addWidget(self.total)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.restore_btn = QPushButton("Restore this version", objectName="primary")
        self.restore_btn.clicked.connect(self._restore)
        self.folder_btn = QPushButton("Show in folder")
        self.folder_btn.clicked.connect(self._show_folder)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        for b in (self.restore_btn, self.folder_btn, self.delete_btn):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        keep_row = QHBoxLayout()
        keep_row.setSpacing(8)
        keep_row.addWidget(QLabel("Keep up to"))
        self.keep = QSpinBox()
        self.keep.setRange(0, MAX_KEEP)
        self.keep.setSpecialValueText("unlimited")
        self.keep.setValue(self.backups.retention())
        self.keep.valueChanged.connect(self._sync_buttons)
        keep_row.addWidget(self.keep)
        keep_row.addWidget(QLabel("backups per app"))
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_retention)
        keep_row.addWidget(self.apply_btn)
        keep_row.addStretch(1)
        lay.addLayout(keep_row)
        lay.addWidget(QLabel("Older backups are removed automatically after an update. Other apps "
                             "are trimmed the next time they are updated.", objectName="hint"))

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        lay.addLayout(close_row)

        self._refresh()

    # -- helpers ------------------------------------------------------------------------
    def _selected(self) -> BackupRecord | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _refresh(self):
        fresh = self.backups.library.get(self.entry.id)
        if fresh:
            self.entry = fresh
        records = self.backups.list_backups(self.entry.id)
        v = self.entry.installed_version
        self.sub.setText(f"{self.entry.name}  ·  installed: {v if v else 'unknown version'}")
        self.list.clear()
        for rec in records:
            when = datetime.fromtimestamp(rec.created).strftime("%Y-%m-%d %H:%M") if rec.created else "unknown date"
            item = QListWidgetItem(f"{rec.version or 'Unknown version'}   ·   {when}   ·   {_size(rec.size)}")
            item.setData(Qt.UserRole, rec)
            item.setToolTip(rec.path)
            self.list.addItem(item)
        if records:
            self.list.setCurrentRow(0)
        self.list.setVisible(bool(records))
        self.empty.setVisible(not records)
        self.total.setText(f"{len(records)} backup{'s' if len(records) != 1 else ''}  ·  "
                           f"{_size(sum(r.size for r in records))} on disk" if records else "")
        self._sync_buttons()

    def _sync_buttons(self):
        has = self._selected() is not None
        for b in (self.restore_btn, self.folder_btn, self.delete_btn):
            b.setEnabled(has)
        self.apply_btn.setEnabled(self.keep.value() != self.backups.retention())

    def _say(self, text: str):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    # -- actions ------------------------------------------------------------------------
    def _restore(self):
        rec = self._selected()
        if rec is None:
            return
        cur = self.entry.installed_version or "the current version"
        box = QMessageBox(QMessageBox.Question, "Restore this version",
                          f"Restore {self.entry.name} {rec.version or '(unknown version)'}?", parent=self)
        box.setInformativeText(f"{cur} is saved as a backup first, so you can switch back at any time. "
                               "If the app is running, restart it to use the restored version.")
        go = box.addButton("Restore", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        try:
            result = self.backups.rollback(self.entry.id, rec.path)
        except LibraryError as exc:
            QMessageBox.warning(self, "Couldn't restore", f"{exc}\n\nYour installed version was not changed.")
            return
        self.changed = True
        self._refresh()
        self._say(f"Restored {result.restored_version or 'the selected version'}. "
                  f"{result.saved_version or 'The previous version'} is in the list if you want it back.")

    def _delete(self):
        rec = self._selected()
        if rec is None:
            return
        box = QMessageBox(QMessageBox.Question, "Delete backup",
                          f"Delete the backup of {rec.version or 'this version'}?", parent=self)
        box.setInformativeText("The file is removed from disk. Your installed version is not affected.")
        go = box.addButton("Delete", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        try:
            self.backups.delete_backup(self.entry.id, rec.path)
        except LibraryError as exc:
            QMessageBox.warning(self, "Couldn't delete", str(exc))
        self._say("")
        self._refresh()

    def _show_folder(self):
        rec = self._selected()
        if rec:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(rec.path).parent)))

    def _apply_retention(self):
        keep = self.keep.value()
        doomed = self.backups.excess(self.entry.id, keep)
        if doomed:
            box = QMessageBox(QMessageBox.Question, "Delete older backups",
                              f"This deletes {len(doomed)} older backup{'s' if len(doomed) != 1 else ''} "
                              f"of {self.entry.name}.", parent=self)
            box.setInformativeText("Versions: " + ", ".join(r.version or "unknown" for r in doomed))
            go = box.addButton("Delete and apply", QMessageBox.DestructiveRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not go:
                return
        self.backups.set_retention(keep)
        self.backups.prune(self.entry.id)
        self._say("")
        self._refresh()
