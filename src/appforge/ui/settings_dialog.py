"""Settings dialog (Phase 5): update checks, notifications, background running, GitHub token."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from ..core.settings import INTERVAL_CHOICES, AppSettings


def _label(text: str) -> QLabel:
    return QLabel(text, objectName="sectionLabel")


def _hint(text: str) -> QLabel:
    lbl = QLabel(text, objectName="hint")
    lbl.setWordWrap(True)
    return lbl


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, tray_available: bool, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setFixedSize(520, 560)
        lay = QVBoxLayout(self)
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
        self.interval = QComboBox()
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
        self.bg_cb = QCheckBox("Keep running in the system tray when the window is closed")
        self.bg_cb.setChecked(settings.run_in_background and tray_available)
        self.bg_cb.setEnabled(tray_available)
        lay.addWidget(self.bg_cb)
        lay.addWidget(_hint("Lets AppForge keep checking for updates after you close the window. Quit it "
                            "from the tray icon." if tray_available else
                            "No system tray was found on this desktop, so background running is unavailable."))

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
        self.error_lbl = QLabel(objectName="error")
        self.error_lbl.setWordWrap(True)
        lay.addWidget(self.error_lbl)

        lay.addStretch(1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save", objectName="primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _save(self):
        try:
            self.settings.set_github_token(self.token_edit.text())
        except ValueError as exc:
            self.error_lbl.setText(str(exc))
            return
        self.settings.auto_check = self.auto_cb.isChecked()
        self.settings.check_interval_hours = int(self.interval.currentData())
        self.settings.notifications = self.notify_cb.isChecked()
        self.settings.run_in_background = self.bg_cb.isChecked()
        self.accept()
