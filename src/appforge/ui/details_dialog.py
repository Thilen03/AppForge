"""Application details with existing main-window action routing and read-only workers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.details import FileDetails, inspect_details
from ..core.models import UpdateStatus
from ..core.updates.service import can_update
from .icons import app_pixmap


def date_text(value):
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M") if value else "Unknown"
    except (ValueError, TypeError, OverflowError, OSError):
        return "Unknown"


def size_text(value):
    if value is None:
        return "Unavailable"
    return f"{value / 1024**2:.2f} MiB ({value:,} bytes)" if value >= 1024**2 else f"{value:,} bytes"


class DetailsSignals(QObject):
    done = Signal(int, object)


class DetailsJob(QRunnable):
    def __init__(self, generation, entry):
        super().__init__()
        self.generation, self.entry = generation, deepcopy(entry)
        self.signals = DetailsSignals()

    def run(self):
        try:
            result = inspect_details(self.entry)
        except Exception:
            result = FileDetails(backup_error="Details unavailable; refresh to try again.")
        self.signals.done.emit(self.generation, result)


class DetailsDialog(QDialog):
    actionRequested = Signal(str, str)

    def __init__(self, service, app_id, busy, parent=None):
        super().__init__(parent)
        self.service, self.app_id, self.busy = service, app_id, busy
        self._generation = 0
        self._job = None
        self._closed = False
        self._file_result = None
        self.resize(680, 760)
        self.setMinimumSize(460, 400)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        header = QHBoxLayout()
        self.icon = QLabel()
        self.name = QLabel(objectName="title")
        self.name.setTextFormat(Qt.PlainText)
        self.name.setWordWrap(True)
        header.addWidget(self.icon)
        header.addWidget(self.name, 1)
        root.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.fields = {}
        for section, rows in (
            ("Application", ("Description", "Format", "Installed version", "Location", "File status", "File size", "Date added")),
            ("Updates", ("Repository", "Latest version", "Update status", "Last checked", "Channel")),
            ("Backups", ("Backup count", "Backup storage", "Newest backup", "Backup notice")),
        ):
            layout.addWidget(QLabel(section, objectName="sectionLabel"))
            form = QFormLayout()
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            for title in rows:
                label = QLabel()
                label.setWordWrap(True)
                label.setTextFormat(Qt.PlainText)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                form.addRow(title, label)
                self.fields[title] = label
            layout.addLayout(form)
        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.buttons = {}
        for actions in (
            (("launch", "Launch"), ("check", "Check for updates"), ("update", "Update")),
            (("folder", "Open folder"), ("edit", "Edit application…"), ("backups", "Backups & rollback…")),
            (("notes", "Release notes…"), ("release", "View release page"), ("locate", "Locate file…"), ("executable", "Make executable")),
        ):
            row = QHBoxLayout()
            for key, title in actions:
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, action=key: self.actionRequested.emit(action, self.app_id))
                self.buttons[key] = button
                row.addWidget(button)
            root.addLayout(row)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def refresh(self):
        if self._closed:
            return
        entry = self.service.get(self.app_id)
        if entry is None:
            self.close()
            return
        self.setWindowTitle(f"{entry.name} — Details")
        self.name.setText(entry.name)
        self.icon.setPixmap(app_pixmap(entry.icon_path, entry.name, 64, self.devicePixelRatioF()))
        kind = entry.metadata.get("executable_kind")
        format_name = "AppImage" if entry.format == "appimage" else {"elf": "ELF binary", "script": "Script"}.get(kind, "Executable")
        status = {
            UpdateStatus.UP_TO_DATE: "Up to date", UpdateStatus.UPDATE_AVAILABLE: "Update available",
            UpdateStatus.CHECKING: "Checking…", UpdateStatus.FAILED: "Failed", UpdateStatus.UNAVAILABLE: "Unavailable",
        }.get(entry.update_status, "Unknown")
        busy = self.busy.get(self.app_id)
        info = entry.metadata.get("update") or {}
        values = {
            "Description": entry.description or "No description available", "Format": format_name,
            "Installed version": entry.installed_version or "Unknown", "Location": entry.path,
            "Date added": date_text(entry.added_at), "Repository": entry.github_repo or "Not linked",
            "Latest version": entry.latest_version or "Unknown", "Update status": busy[0] if busy else status,
            "Last checked": date_text(entry.last_update_check) if entry.last_update_check else "Never checked",
            "Channel": "Stable and prereleases" if entry.metadata.get("include_prereleases") else "Stable",
        }
        if not busy and info.get("message"):
            values["Update status"] += f" — {info['message']}"
        for key, value in values.items():
            self.fields[key].setText(value)
        for button in self.buttons.values():
            button.setEnabled(not busy)
        self.buttons["check"].setEnabled(bool(entry.github_repo) and not busy)
        self.buttons["update"].setEnabled(can_update(entry) and not busy)
        self.buttons["notes"].setEnabled(bool(entry.github_repo and info.get("tag")))
        self.buttons["release"].setEnabled(bool(info.get("release_url")))
        self._sync_file_buttons(entry)
        # Disable file-dependent actions until the current snapshot has been inspected.
        if getattr(self, "_snapshot", None) != entry:
            self._snapshot = deepcopy(entry)
            self._file_result = None
            self._generation += 1
            for key in ("File status", "File size", "Backup count", "Backup storage", "Newest backup"):
                self.fields[key].setText("Loading…")
            self._sync_file_buttons(entry)
        if self._job is None:
            self._start_scan(entry)

    def _start_scan(self, entry):
        job = DetailsJob(self._generation, entry)
        self._job = job
        job.signals.done.connect(self._on_details)
        QThreadPool.globalInstance().start(job)

    def _on_details(self, generation, result):
        self._job = None
        if self._closed:
            return
        if generation != self._generation:
            self.refresh()
            return
        entry = self.service.get(self.app_id)
        if entry != self._snapshot:
            self.refresh()
            return
        newest = ("Unavailable" if result.backup_count is None else
                  date_text(result.backup_date) if result.backup_count else "None")
        for key, value in {
            "File status": result.state, "File size": size_text(result.size),
            "Backup count": str(result.backup_count) if result.backup_count is not None else "Unavailable",
            "Backup storage": size_text(result.backup_size), "Newest backup": newest,
            "Backup notice": result.backup_error,
        }.items():
            self.fields[key].setText(value)
        self._file_result = result
        self._sync_file_buttons(entry)

    def _sync_file_buttons(self, entry):
        result = self._file_result
        state = result.state if result else "Loading"
        idle = self.app_id not in self.busy
        self.buttons["launch"].setEnabled(state == "Ready" and idle)
        self.buttons["update"].setEnabled(state == "Ready" and idle and can_update(entry))
        self.buttons["locate"].setVisible(state in ("File missing", "Not a regular file"))
        self.buttons["executable"].setVisible(state == "Not executable")

    def done(self, result):
        self._closed = True
        self.timer.stop()
        super().done(result)
