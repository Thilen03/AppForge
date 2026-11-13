"""System-tray icon: background running, "check now", and update balloons (Phase 5)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import APP_DISPLAY_NAME


def tray_available() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()


class TrayController(QObject):
    showRequested = Signal()
    checkRequested = Signal()
    quitRequested = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu()
        menu.addAction(f"Open {APP_DISPLAY_NAME}", self.showRequested.emit)
        menu.addAction("Check for updates now", self.checkRequested.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.quitRequested.emit)
        self._menu = menu                       # keep a reference: the tray doesn't own it
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self.tray.messageClicked.connect(self.showRequested.emit)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.showRequested.emit()

    @property
    def visible(self) -> bool:
        return self.tray.isVisible()

    def set_visible(self, on: bool) -> None:
        self.tray.setVisible(on)

    def message(self, title: str, body: str, ms: int = 10000) -> None:
        self.tray.showMessage(title, body, QSystemTrayIcon.Information, ms)
