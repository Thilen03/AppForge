"""System tray navigation, live update status and application shortcuts."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from .. import APP_DISPLAY_NAME
from ..core.library import FileState, file_state
from .popups import RoundedMenu


def tray_available() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()


def _label(text):
    # Labels are plain, single-line text; '&' must not create menu mnemonics.
    return " ".join(text.split()).replace("&", "&&")[:100]


class TrayController(QObject):
    showRequested = Signal()
    settingsRequested = Signal()
    checkRequested = Signal()
    updateAllRequested = Signal()
    launchRequested = Signal(str)
    favoriteRequested = Signal(str, bool)
    refreshRequested = Signal()
    quitRequested = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_DISPLAY_NAME)
        menu = RoundedMenu()
        menu.addAction(f"Open {APP_DISPLAY_NAME}", self.showRequested.emit)
        menu.addAction("Settings…", self.settingsRequested.emit)
        menu.addSeparator()
        self.status_action = menu.addAction("No updates available")
        self.status_action.setEnabled(False)
        self.activity_action = menu.addAction("Idle")
        self.activity_action.setEnabled(False)
        self.check_action = menu.addAction("Check for updates", self.checkRequested.emit)
        self.update_action = menu.addAction("Update All", self.updateAllRequested.emit)
        menu.addSeparator()
        self.favorites_menu = RoundedMenu("Favorites", menu)
        self.recent_menu = RoundedMenu("Recently used", menu)
        self.apps_menu = RoundedMenu("Applications", menu)
        self.manage_menu = RoundedMenu("Choose favorites", menu)
        for submenu in (self.favorites_menu, self.recent_menu, self.apps_menu, self.manage_menu):
            menu.addMenu(submenu)
        menu.addSeparator()
        menu.addAction("Exit AppForge", self.quitRequested.emit)
        self._menu = menu  # the tray does not own its menu
        menu.aboutToShow.connect(self.refreshRequested.emit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self.tray.messageClicked.connect(self.showRequested.emit)

    def set_status(self, count, ready, checking=False, activity="Idle", running=False):
        summary = f"{count} application update{'s' if count != 1 else ''} available"
        self.status_action.setText(summary)
        self.activity_action.setText(_label(activity))
        self.tray.setToolTip(f"{APP_DISPLAY_NAME} — {summary}\n{activity}")
        self.check_action.setEnabled(not checking and not running)
        self.update_action.setText(f"Update All ({ready})" if ready else "Update All")
        self.update_action.setEnabled(bool(ready) and not running)

    def set_applications(self, entries, favorites, recent, busy=()):
        by_id = {e.id: e for e in entries}
        ordered = sorted(entries, key=lambda e: (e.name.casefold(), e.id))
        for menu, items in (
            (self.favorites_menu, [by_id[i] for i in favorites if i in by_id]),
            (self.recent_menu, [by_id[i] for i in recent if i in by_id]),
            (self.apps_menu, ordered),
        ):
            menu.clear()
            for entry in items:
                action = menu.addAction(_label(entry.name))
                action.setToolTip(entry.path)
                action.setEnabled(entry.id not in busy and file_state(entry) is FileState.OK)
                action.triggered.connect(lambda checked=False, i=entry.id: self.launchRequested.emit(i))
            if not items:
                menu.addAction("None yet").setEnabled(False)
        self.manage_menu.clear()
        for entry in ordered:
            action = self.manage_menu.addAction(_label(entry.name))
            action.setToolTip(entry.path)
            action.setCheckable(True)
            action.setChecked(entry.id in favorites)
            action.triggered.connect(lambda checked, i=entry.id: self.favoriteRequested.emit(i, checked))
        if not ordered:
            self.manage_menu.addAction("Add applications to choose favorites").setEnabled(False)

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
