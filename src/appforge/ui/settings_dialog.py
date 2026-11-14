"""Settings dialog (Phase 5): update checks, notifications, background running, GitHub token."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core import autostart
from ..core.settings import INTERVAL_CHOICES, AppSettings
from .popups import RoundedComboBox


def _label(text: str) -> QLabel:
    return QLabel(text, objectName="sectionLabel")


def _hint(text: str) -> QLabel:
    lbl = QLabel(text, objectName="hint")
    lbl.setWordWrap(True)
    return lbl


class SettingsDialog(QDialog):
    exportRequested = Signal()
    importRequested = Signal()

    def __init__(self, settings: AppSettings, tray_available: bool, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.resize(560, 660)
        self.setMinimumSize(520, 440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Settings", objectName="title"))

        lay.addSpacing(6)
        lay.addWidget(_label("Update checks"))
        self.auto_cb = QCheckBox("Check for updates automatically")
        self.auto_cb.setChecked(settings.auto_check)
        lay.addWidget(self.auto_cb)
        row = QHBoxLayout()
        row.addWidget(QLabel("Check every"))
        self.interval = RoundedComboBox()
        for h in INTERVAL_CHOICES:
            self.interval.addItem("1 hour" if h == 1 else f"{h} hours", h)
        cur = settings.check_interval_hours
        if cur not in INTERVAL_CHOICES:
            self.interval.addItem(f"{cur} hours", cur)
        self.interval.setCurrentIndex(self.interval.findData(cur))
        row.addWidget(self.interval)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_hint("Checks run at startup and then in the background while AppForge is open."))
        self.auto_cb.toggled.connect(self.interval.setEnabled)
        self.interval.setEnabled(self.auto_cb.isChecked())

        lay.addSpacing(8)
        lay.addWidget(_label("Notifications and background"))
        self.notify_cb = QCheckBox("Notify me when an update is found")
        self.notify_cb.setChecked(settings.notifications)
        lay.addWidget(self.notify_cb)
        self.bg_cb = QCheckBox("Minimize or close to the system tray")
        self.bg_cb.setChecked(settings.run_in_background and tray_available)
        self.bg_cb.setEnabled(tray_available)
        lay.addWidget(self.bg_cb)
        lay.addWidget(_hint("Keeps AppForge out of the taskbar when minimized or closed. Quit it "
                            "from the tray icon." if tray_available else
                            "No system tray was found on this desktop, so background running is unavailable."))

        lay.addSpacing(8)
        lay.addWidget(_label("Startup"))
        self.startup_cb = QCheckBox("Start AppForge at login")
        self.startup_cb.setChecked(settings.start_at_login)
        lay.addWidget(self.startup_cb)
        self.start_minimized_cb = QCheckBox("Start minimized to the system tray")
        self.start_minimized_cb.setChecked(settings.start_minimized)
        lay.addWidget(self.start_minimized_cb)
        lay.addWidget(_hint("Applies when you log in to your desktop. Starting minimized enables "
                            "tray background mode; without a tray, AppForge opens normally."))
        self.startup_cb.toggled.connect(
            lambda enabled: self.start_minimized_cb.setEnabled(enabled and tray_available))
        self.start_minimized_cb.setEnabled(self.startup_cb.isChecked() and tray_available)
        self.start_minimized_cb.toggled.connect(
            lambda enabled: self.bg_cb.setChecked(True) if enabled and tray_available else None)
        self.bg_cb.toggled.connect(
            lambda enabled: self.start_minimized_cb.setChecked(False) if not enabled else None)

        lay.addSpacing(8)
        lay.addWidget(_label("GitHub access token (optional)"))
        self.token_edit = QLineEdit(settings.github_token)
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("ghp_…  (leave empty for none)")
        lay.addWidget(self.token_edit)
        src = settings.token_source()
        lay.addWidget(_hint(
            "Raises GitHub's rate limit from 60 to 5000 requests per hour. It is only ever sent to "
            "api.github.com and is stored unencrypted in AppForge's library file (readable only by you)."
            + (" Currently using GITHUB_TOKEN from the environment." if src == "environment" else "")))

        lay.addWidget(_label("Library transfer"))
        transfer = QHBoxLayout()
        self.export_btn = QPushButton("Export Library…")
        self.import_btn = QPushButton("Import Library…")
        self.export_btn.clicked.connect(self.exportRequested.emit)
        self.import_btn.clicked.connect(self.importRequested.emit)
        transfer.addWidget(self.export_btn)
        transfer.addWidget(self.import_btn)
        lay.addLayout(transfer)
        lay.addWidget(_hint("Transfer application configuration and icons as JSON. "
                            "Application files and AppForge tokens are excluded. "
                            "Transfers apply immediately, independently of Save."))

        lay.addStretch(1)
        self.error_lbl = QLabel(objectName="error")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setContentsMargins(24, 0, 24, 0)
        outer.addWidget(self.error_lbl)
        btns = QHBoxLayout()
        btns.setContentsMargins(24, 4, 24, 20)
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save", objectName="primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        outer.addLayout(btns)

    def _save(self):
        try:
            token = self.settings.validate_github_token(self.token_edit.text())
            if self.startup_cb.isChecked() or self.settings.start_at_login:
                autostart.set_enabled(self.startup_cb.isChecked())
        except (ValueError, autostart.AutostartError) as exc:
            self.error_lbl.setText(str(exc))
            return
        self.settings.set_github_token(token)
        self.settings.auto_check = self.auto_cb.isChecked()
        self.settings.check_interval_hours = int(self.interval.currentData())
        self.settings.notifications = self.notify_cb.isChecked()
        if self.bg_cb.isEnabled():
            self.settings.run_in_background = self.bg_cb.isChecked()
        self.settings.start_at_login = self.startup_cb.isChecked()
        self.settings.start_minimized = self.start_minimized_cb.isChecked()
        self.accept()
