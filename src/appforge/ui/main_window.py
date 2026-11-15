"""Main window: header, searchable application library, launching and updating."""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QRunnable, QSettings, QSize, QThreadPool, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication, QWindow
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressDialog, QPushButton, QScrollArea, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from .. import APP_DISPLAY_NAME, __version__
from ..core.library import FileState, LibraryError, LibraryService, file_state
from ..core.models import AppEntry, UpdateStatus
from ..core.organize import (
    ALL, SORT_NAME, SORTS, STATUS_FILTERS, Filter, categories_in_use, matches, sort_entries,
)
from ..core.selfupdate import appimage_path, install_blocker
from ..core.settings import AppSettings
from ..core.tray import TrayShortcuts
from ..core.updates.assets import is_candidate_name, compatible_arch, host_arch
from ..core.updates.installer import InstallCancelled, InstallResult
from ..core.updates.service import UpdateService, can_update
from ..core.update_policy import updates_paused, updates_suppressed
from ..services import launcher
from ..services.notifier import send_desktop_notification, summarize_updates
from .app_card import AppCard, CARD_W
from .backups_dialog import BackupsDialog
from .dialogs import FILE_FILTER, AddApplicationDialog, AssetPickerDialog, EditApplicationDialog
from .flow_layout import FlowLayout
from .icons import gear_icon, placeholder_pixmap, theme_icon
from . import theme
from .popups import RoundedComboBox
from .settings_dialog import SettingsDialog
from .tray import TrayController, tray_available
from .kwin_tray import KWinTrayBridge, plasma_wayland
from .workers import CheckJob, InstallJob, SelfInstallJob, SelfUpdateJob
from .discovery_watch import DiscoveryWatcher

log = logging.getLogger(__name__)
STALE_AFTER = 30 * 60   # re-check automatically at startup if the last check is older than this
CARD_GAP = 18
BACKGROUND_TICK_MS = 10 * 60 * 1000   # how often the idle checker looks at whether a check is due


class _FnJob(QRunnable):
    """Runs a small blocking function (e.g. notify-send) off the UI thread."""

    def __init__(self, fn, *args):
        super().__init__()
        self._fn, self._args = fn, args

    def run(self):
        try:
            self._fn(*self._args)
        except Exception:  # noqa: BLE001
            log.debug("background helper failed", exc_info=True)


def _ago(ts: float | None) -> str:
    if not ts:
        return ""
    secs = max(0, int(time.time() - ts))
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


class MainWindow(QMainWindow):
    def __init__(self, service: LibraryService, github_client=None, auto_check: bool = False,
                 settings: AppSettings | None = None, tray_icon=None):
        """``auto_check=True`` is the real application: startup check, periodic idle checks and
        notifications. Tests leave it off, so nothing runs (or pops up) by itself."""
        super().__init__()
        self.service = service
        self.updates = UpdateService(service)
        self.settings = settings or AppSettings(service.db)
        theme.apply_theme(QApplication.instance(), self.settings.theme_mode,
                          self.settings.card_badge_colors)
        self._client = github_client
        self._live = auto_check
        self._quitting = False
        self._kwin_bridge = None
        self._tray_window_handle = None
        self._tray_minimize_timer = QTimer(self)
        self._tray_minimize_timer.setSingleShot(True)
        self._tray_minimize_timer.setInterval(0)
        self._tray_minimize_timer.timeout.connect(self._minimize_to_tray)
        self.restart_requested = False   # set by the self-update: app.main() relaunches after quitting
        self._self_offer_open = False
        self._pending_self_update = None
        self._self_install: SelfInstallJob | None = None
        self._self_progress: QProgressDialog | None = None
        self._tray_check = False
        self._tray_hint_shown = False
        self.shortcuts = TrayShortcuts(service.db)
        self._issue_notified = set()
        self.tray: TrayController | None = None
        try:
            if tray_icon is not None and tray_available():
                self.tray = TrayController(tray_icon, self)
                self.tray.showRequested.connect(self.bring_to_front)
                self.tray.settingsRequested.connect(self._settings_from_tray)
                self.tray.checkRequested.connect(self._check_from_tray)
                self.tray.updateAllRequested.connect(self._update_from_tray)
                self.tray.launchRequested.connect(self._launch_from_tray)
                self.tray.favoriteRequested.connect(self._favorite_from_tray)
                self.tray.refreshRequested.connect(self._refresh_tray_shortcuts)
                self.tray.quitRequested.connect(self.quit_app)
        except Exception:
            log.warning("System tray unavailable", exc_info=True)
            self.tray = None
        self.setWindowTitle(f"{APP_DISPLAY_NAME} {__version__}")
        self.setAcceptDrops(True)
        self.resize(1040, 700)
        self.setMinimumSize(620, 420)
        self._details = {}
        self._release_notes = {}
        self._cards: list[AppCard] = []
        self._busy: dict[str, tuple[str, float | None]] = {}
        self._jobs: dict[str, object] = {}
        self._batch: dict | None = None
        self._user_check = False
        self.check_pool = QThreadPool()
        self.check_pool.setMaxThreadCount(4)
        self.install_pool = QThreadPool()
        self.install_pool.setMaxThreadCount(1)   # one download/replace at a time
        self._build()
        self.statusBar().setSizeGripEnabled(False)
        geo = QSettings().value("geometry")
        if geo:
            self.restoreGeometry(geo)
        self._fit_library_width()
        self.reload()
        self.discovery_watcher = DiscoveryWatcher(service, self)
        self.discovery_watcher.changed.connect(self._discovery_found)
        self.discovery_watcher.poll()
        QApplication.instance().aboutToQuit.connect(self.discovery_watcher.stop)
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)
        self.apply_settings()
        QApplication.instance().aboutToQuit.connect(self._stop_kwin_bridge)
        if auto_check:
            QTimer.singleShot(1500, self._check_self_update)
            if self.settings.auto_check:
                QTimer.singleShot(800, lambda: self.check_updates(only_stale=True))
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._scheduled_check)
            self._timer.start(BACKGROUND_TICK_MS)

    def _build_settings_gear(self):
        """Settings control next to Add Application, sized to match the header buttons."""
        self.settings_btn = QToolButton(objectName="gear")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setAccessibleName("Settings")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setAutoRaise(True)
        self.add_btn.ensurePolished()
        side = self.add_btn.sizeHint().height()
        self.settings_btn.setFixedSize(side, side)
        self.settings_btn.setIconSize(QSize(24, 24))
        self.add_btn.installEventFilter(self)
        self.settings_btn.clicked.connect(self.open_settings)
        self._refresh_gear()

    def _build_theme_toggle(self):
        self.theme_btn = QToolButton(objectName="themeToggle")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setAutoRaise(True)
        self.theme_btn.setFixedSize(self.settings_btn.size())
        self.theme_btn.setIconSize(QSize(24, 24))
        self.theme_btn.clicked.connect(self.toggle_theme)
        self._refresh_theme_toggle()

    def _refresh_theme_toggle(self):
        dark = theme.tokens().dark
        label = "Switch to light mode" if dark else "Switch to dark mode"
        self.theme_btn.setToolTip(label)
        self.theme_btn.setAccessibleName(label)
        self.theme_btn.setIcon(theme_icon(dark, theme.tokens().accent_text))

    def toggle_theme(self):
        mode = "light" if theme.tokens().dark else "dark"
        self.settings.theme_mode = mode
        theme.apply_theme(QApplication.instance(), mode, self.settings.card_badge_colors)
        self._refresh_theme_toggle()

    def _fit_library_width(self):
        # Open with four columns when the screen permits, including when an older,
        # narrower saved geometry exists. Resizing later remains unrestricted.
        margins = self.centralWidget().layout().contentsMargins()
        target = 4 * CARD_W + 3 * CARD_GAP + margins.left() + margins.right()
        available = self.screen().availableGeometry().width()
        frame = self.frameGeometry().width() - self.width()
        self.resize(min(max(self.width(), target), available - frame), self.height())

    def _refresh_gear(self):
        """Match the primary button text colour; re-tint when the theme flips."""
        self.settings_btn.setIcon(gear_icon(theme.tokens().accent_text, 24))
        if hasattr(self, "theme_btn"):
            self._refresh_theme_toggle()

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "add_btn", None) and ev.type() == QEvent.Resize:
            side = ev.size().height()
            self.settings_btn.setFixedSize(side, side)
            if hasattr(self, "theme_btn"):
                self.theme_btn.setFixedSize(side, side)
        return super().eventFilter(obj, ev)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self._tray_minimize_timer.start()
            else:
                self._tray_minimize_timer.stop()
        if ev.type() in (QEvent.PaletteChange, QEvent.StyleChange) and hasattr(self, "settings_btn"):
            self._refresh_gear()

    # -- layout -------------------------------------------------------------------------
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 26, 32, 8)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(QLabel("Library", objectName="title"))
        sub = QHBoxLayout()
        sub.setSpacing(header.spacing())
        self.count_lbl = QLabel(objectName="subtitle")
        sub.addWidget(self.count_lbl)
        self.check_btn = QPushButton("Check for updates", objectName="primary")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.clicked.connect(lambda: self.check_updates(user_initiated=True))
        sub.addWidget(self.check_btn)
        self.discover_btn = QPushButton("Discover apps…", objectName="primary")
        self.discover_btn.clicked.connect(self.discover_applications)
        sub.addWidget(self.discover_btn)
        self.storage_btn = QPushButton("Storage…", objectName="primary")
        self.storage_btn.clicked.connect(self.show_storage)
        sub.addWidget(self.storage_btn)
        sub.addStretch(1)
        titles.addLayout(sub)
        header.addLayout(titles)
        header.addStretch(1)
        self.search = QLineEdit(placeholderText="Search applications")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._apply_filter)
        header.addWidget(self.search)
        self.update_all_btn = QPushButton("Update All")
        self.update_all_btn.clicked.connect(self.update_all)
        header.addWidget(self.update_all_btn)
        self.add_btn = QPushButton("Add Application", objectName="primary")
        self.add_btn.clicked.connect(self.add_application)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(self.add_btn)
        self._build_settings_gear()
        header.addWidget(self.settings_btn)
        self._build_theme_toggle()
        header.addWidget(self.theme_btn)
        root.addLayout(header)

        self.filter_row = QWidget()
        fl = QHBoxLayout(self.filter_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)
        self.category_cb = RoundedComboBox()
        self.category_cb.setToolTip("Show one category")
        self.status_cb = RoundedComboBox()
        self.status_cb.setToolTip("Filter by status")
        for key, label in STATUS_FILTERS:
            self.status_cb.addItem(label, key)
        fl.addWidget(self.category_cb)
        fl.addWidget(self.status_cb)
        fl.addStretch(1)
        fl.addWidget(QLabel("Sort by", objectName="subtitle"))
        self.sort_cb = RoundedComboBox()
        for key, label in SORTS:
            self.sort_cb.addItem(label, key)
        fl.addWidget(self.sort_cb)
        self.category_cb.addItem("All categories", None)
        self.category_cb.currentIndexChanged.connect(lambda *_: self._apply_filter())
        self.status_cb.currentIndexChanged.connect(lambda *_: self._apply_filter())
        self.sort_cb.currentIndexChanged.connect(lambda *_: self.reload())
        root.addWidget(self.filter_row)

        self.banner = QLabel(objectName="banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        root.addWidget(self.banner)

        self.discovery_found_btn = QPushButton(objectName="soft")
        self.discovery_found_btn.setAccessibleName("Review new applications in watched folders")
        self.discovery_found_btn.clicked.connect(self.review_discovered)
        self.discovery_found_btn.hide()
        root.addWidget(self.discovery_found_btn)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.flow = FlowLayout(self.grid_host, CARD_GAP, CARD_GAP)
        self.flow.setContentsMargins(0, 4, 0, 24)
        self.scroll.setWidget(self.grid_host)
        self.stack.addWidget(self.scroll)

        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(2)
        icon = QLabel(alignment=Qt.AlignCenter)
        icon.setPixmap(placeholder_pixmap("A", 72, self.devicePixelRatioF()))
        el.addWidget(icon)
        el.addWidget(QLabel("No applications yet", objectName="emptyTitle", alignment=Qt.AlignCenter))
        s = QLabel("Add an AppImage from anywhere on your computer, or drop one onto this window.",
                   objectName="subtitle", alignment=Qt.AlignCenter)
        s.setWordWrap(True)
        el.addWidget(s)
        b = QPushButton("Add your first AppImage", objectName="primary")
        b.clicked.connect(self.add_application)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(b)
        row.addStretch(1)
        el.addLayout(row)
        el.addStretch(3)
        self.stack.addWidget(empty)

        self.no_results = QLabel("No applications match your search or filters.", objectName="subtitle",
                                 alignment=Qt.AlignCenter)
        self.stack.addWidget(self.no_results)

    # -- cards --------------------------------------------------------------------------
    def _make_card(self, entry: AppEntry) -> AppCard:
        card = AppCard(entry, file_state(entry), self._busy.get(entry.id), self.grid_host,
                       favorite=entry.id in self.shortcuts.favorites)
        card.pauseUpdatesRequested.connect(self.set_updates_paused)
        card.skipVersionRequested.connect(self.skip_update_version)
        card.clearSkippedVersionRequested.connect(self.clear_skipped_version)
        card.favoriteRequested.connect(self._favorite_from_tray)
        card.detailsRequested.connect(self.show_details)
        card.launchRequested.connect(self.launch)
        card.editRequested.connect(self.edit_application)
        card.removeRequested.connect(self.remove_application)
        card.openFolderRequested.connect(self.show_in_file_manager)
        card.copyPathRequested.connect(self.copy_path)
        card.relinkRequested.connect(self.locate_file)
        card.makeExecutableRequested.connect(self.make_executable)
        card.updateRequested.connect(self.start_update)
        card.checkRequested.connect(lambda i: self.check_updates([i], user_initiated=True))
        card.releasePageRequested.connect(self.open_release_page)
        card.releaseNotesRequested.connect(self.show_release_notes)
        card.chooseAssetRequested.connect(self.choose_asset)
        card.prereleasesRequested.connect(self.set_prereleases_enabled)
        card.backupsRequested.connect(self.show_backups)
        card.desktopToggleRequested.connect(self.toggle_desktop_entry)
        return card

    def set_updates_paused(self, app_id: str, paused: bool):
        if app_id in self._busy:
            return
        if self.updates.set_paused(app_id, paused):
            self._refresh_card(app_id)
            if not paused:
                self.check_updates([app_id])

    def skip_update_version(self, app_id: str):
        if app_id not in self._busy and self.updates.skip_version(app_id):
            self._refresh_card(app_id)

    def clear_skipped_version(self, app_id: str):
        if app_id not in self._busy and self.updates.clear_skipped_version(app_id):
            self._refresh_card(app_id)

    def _card(self, app_id: str) -> AppCard | None:
        return next((c for c in self._cards if c.entry.id == app_id), None)

    def _current_filter(self) -> Filter:
        return Filter(self.search.text(), self.category_cb.currentData(),
                      self.status_cb.currentData() or ALL)

    def _matches(self, entry: AppEntry) -> bool:
        return matches(entry, self._current_filter(),
                       file_ok=lambda e: file_state(e) is FileState.OK)

    def _refresh_card(self, app_id: str):
        """Rebuild one card in place (state changed) without touching the others."""
        entry = self.service.get(app_id)
        old = self._card(app_id)
        if entry is None or old is None:
            return self.reload()
        new = self._make_card(entry)
        if self.flow.replace_widget(old, new):
            self._cards[self._cards.index(old)] = new
            new.setVisible(self._matches(entry))
        self._refresh_header()
        self._refresh_details()

    def _set_busy(self, app_id: str, text: str | None, fraction: float | None = None, rebuild=False):
        if text is None:
            self._busy.pop(app_id, None)
        else:
            self._busy[app_id] = (text, fraction)
        card = self._card(app_id)
        if card and not rebuild:
            card.set_busy(text, fraction)
        else:
            self._refresh_card(app_id)

        self._refresh_details()
        self._refresh_tray()

    def _refresh_details(self):
        for dialog in list(self._details.values()):
            dialog.refresh()
        for dialog in list(self._release_notes.values()):
            dialog.sync()

    def show_details(self, app_id: str):
        if not self.service.get(app_id):
            return
        if app_id not in self._details:
            from .details_dialog import DetailsDialog
            dialog = DetailsDialog(self.service, app_id, self._busy, self)
            dialog.actionRequested.connect(self._details_action)
            dialog.finished.connect(lambda _: self._details.pop(app_id, None))
            dialog.finished.connect(dialog.deleteLater)
            self._details[app_id] = dialog
        dialog = self._details[app_id]
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _details_action(self, action, app_id):
        actions = {
            "launch": self.launch, "check": lambda i: self.check_updates([i], user_initiated=True),
            "update": self.start_update, "folder": self.show_in_file_manager,
            "edit": self.edit_application, "backups": self.show_backups,
            "release": self.open_release_page, "notes": self.show_release_notes, "locate": self.locate_file,
            "executable": self.make_executable,
        }
        actions[action](app_id)
        self._refresh_details()

    # -- data ---------------------------------------------------------------------------
    def reload(self):
        apps = sort_entries(self.service.list_applications(), self.sort_cb.currentData() or SORT_NAME)
        favorites = set(self.shortcuts.favorites)
        # Stable partition preserves the selected sort within each group.
        apps.sort(key=lambda entry: entry.id not in favorites)
        self._refresh_categories(apps)
        for c in self._cards:
            self.flow.removeWidget(c)
            c.deleteLater()
        self._cards = []
        missing = 0
        for entry in apps:
            if file_state(entry) in (FileState.MISSING, FileState.NOT_A_FILE):
                missing += 1
            card = self._make_card(entry)
            self.flow.addWidget(card)
            self._cards.append(card)
        self.search.setEnabled(bool(apps))
        self.filter_row.setVisible(bool(apps))
        if missing:
            self.banner.setText(
                f"{missing} application{' file is' if missing == 1 else ' files are'} missing from "
                "disk. Use “Locate file…” on the marked cards to reconnect them.")
        self.banner.setVisible(bool(missing))
        self._refresh_header()
        self._apply_filter()
        self._refresh_details()
        if hasattr(self, "discovery_watcher"):
            self.discovery_watcher.prune_registered()

    def _refresh_categories(self, apps: list[AppEntry]):
        """Rebuild the category list from the library, keeping the current choice if it still exists."""
        current = self.category_cb.currentData()
        names = categories_in_use(apps)
        self.category_cb.blockSignals(True)
        self.category_cb.clear()
        self.category_cb.addItem("All categories", None)
        for n in names:
            self.category_cb.addItem(n, n)
        idx = self.category_cb.findData(current) if current in names else 0
        self.category_cb.setCurrentIndex(max(0, idx))
        self.category_cb.blockSignals(False)

    def _refresh_header(self):
        apps = [c.entry for c in self._cards]
        n = len(apps)
        text = "Nothing here yet" if n == 0 else f"{n} application{'s' if n != 1 else ''}"
        checks = [a.last_update_check for a in apps if a.github_repo and a.last_update_check]
        if checks:
            text += f"  ·  updates checked {_ago(max(checks))}"
        self.count_lbl.setText(text + "  ")
        linked = any(a.github_repo for a in apps)
        checking = any(t == "Checking for updates…" for t, _ in self._busy.values())
        self.check_btn.setVisible(linked)
        self.check_btn.setEnabled(not checking)
        ready = [a for a in apps if can_update(a) and a.id not in self._busy
                 and file_state(a) is FileState.OK]
        running = self._batch is not None
        self.update_all_btn.setText("Updating…" if running else
                                    f"Update All ({len(ready)})" if ready else "Update All")
        self.update_all_btn.setEnabled(bool(ready) and not running)
        self.update_all_btn.setObjectName("primary" if ready and not running else "")
        self.update_all_btn.style().unpolish(self.update_all_btn)
        self.update_all_btn.style().polish(self.update_all_btn)
        self.update_all_btn.setToolTip("" if ready else
                                       "No updates available. Link a GitHub repository to an app to enable updates.")

        self._refresh_tray()

    def _tray_call(self, method, *args):
        if self.tray is None:
            return
        try:
            getattr(self.tray, method)(*args)
        except Exception:
            log.warning("System tray failed; returning to the library", exc_info=True)
            try:
                self.tray.set_visible(False)
            except Exception:
                pass
            self.tray = None
            self._stop_kwin_bridge()
            QApplication.instance().setQuitOnLastWindowClosed(True)
            self.showNormal()

    def _refresh_tray(self):
        if self.tray is None:
            return
        apps = self.service.list_applications()
        count = sum(e.update_status is UpdateStatus.UPDATE_AVAILABLE and not updates_suppressed(e) for e in apps)
        ready = sum(can_update(e) and e.id not in self._busy and file_state(e) is FileState.OK
                    for e in apps)
        installs = [(i, status) for i, status in self._busy.items()
                    if status[0] != "Checking for updates…"]
        checking = any(t == "Checking for updates…" for t, _ in self._busy.values())
        activity = "Checking for updates…" if checking else "Idle"
        if installs:
            i, (text, _) = next(((i, s) for i, s in installs if s[0] != "Waiting…"), installs[0])
            entry = next((e for e in apps if e.id == i), None)
            activity = f"{entry.name if entry else 'Application'}: {text}"
            if self._batch:
                activity = f"{self._batch['done']}/{self._batch['total']} completed — {activity}"
        self._tray_call("set_status", count, ready, checking, activity,
                        bool(installs) or self._batch is not None)

    def _refresh_tray_shortcuts(self):
        self._refresh_tray()
        self._tray_call("set_applications", self.service.list_applications(),
                        self.shortcuts.favorites, self.shortcuts.recent, self._busy)

    def _favorite_from_tray(self, app_id, enabled):
        if self.service.get(app_id):
            self.shortcuts.set_favorite(app_id, enabled)
            self.reload()

    def _settings_from_tray(self):
        self.bring_to_front()
        self.open_settings()

    def _update_from_tray(self):
        self.bring_to_front()
        self.update_all()

    def _launch_from_tray(self, app_id):
        if app_id not in self._busy:
            self.launch(app_id)

    def _apply_filter(self):
        shown = 0
        for c in self._cards:
            vis = self._matches(c.entry)
            c.setVisible(vis)
            shown += vis
        self.stack.setCurrentIndex(1 if not self._cards else 2 if shown == 0 else 0)
        self.flow.invalidate()

    def _on_app_state(self, state):
        if (state == Qt.ApplicationActive and self.isVisible()
                and QApplication.activeModalWidget() is None):
            self.reload()  # picks up files that were moved/restored while we were in the background

    # -- update checks ------------------------------------------------------------------
    def check_updates(self, ids: list[str] | None = None, only_stale: bool = False,
                      user_initiated: bool = False, stale_after: float | None = None):
        now = time.time()
        limit = STALE_AFTER if stale_after is None else stale_after
        token = self.settings.effective_github_token()
        targets = []
        for e in self.service.list_applications():
            if not e.github_repo or updates_paused(e) or e.id in self._busy or (ids is not None and e.id not in ids):
                continue
            if only_stale and e.last_update_check and now - e.last_update_check < limit:
                continue
            targets.append(e)
        if not targets:
            if user_initiated:
                self.statusBar().showMessage("Nothing to check: add an update source or resume paused updates.", 4000)
            return
        self._user_check = self._user_check or user_initiated
        for e in targets:
            job = CheckJob(
                e.id, repo_url=e.github_repo, installed_version=e.installed_version,
                current_filename=Path(e.path).name, app_name=e.name,
                asset_pattern=e.metadata.get("asset_pattern"),
                include_prereleases=bool(e.metadata.get("include_prereleases")), client=self._client,
                token=token, format_id=e.format, installed_path=e.path)
            job.signals.done.connect(self._on_check_done)
            self._jobs[e.id] = job
            self._set_busy(e.id, "Checking for updates…", None)
            self.check_pool.start(job)
        self._refresh_header()

    def _on_check_done(self, app_id: str, outcome):
        self._jobs.pop(app_id, None)
        self.updates.apply_check(app_id, outcome)
        self._set_busy(app_id, None, rebuild=True)
        all_done = not any(t == "Checking for updates…" for t, _ in self._busy.values())
        user = self._user_check
        if all_done:
            self._after_checks(user)
        if all_done and self._user_check:
            self._user_check = False
            n = sum(1 for c in self._cards if can_update(c.entry) and c.entry.update_status is UpdateStatus.UPDATE_AVAILABLE)
            self.statusBar().showMessage(
                f"{n} update{'s' if n != 1 else ''} available" if n else "No updates available for apps with updates enabled", 5000)

    # -- AppForge's own updates -----------------------------------------------------------
    def _check_self_update(self):
        job = SelfUpdateJob(self._client, self.settings.effective_github_token())
        job.signals.found.connect(self._offer_self_update)
        self._self_check = job                     # keep the signal object alive
        self.check_pool.start(job)

    def _offer_self_update(self, found):
        """Startup popup. "Later" just closes it: the check runs at every start, so it asks again next time."""
        if not self.isVisible() and self.tray is not None and self.tray.visible:
            self._pending_self_update = found
            return
        if self._self_offer_open or self._self_install is not None:
            return
        self._self_offer_open = True
        try:
            blocker = install_blocker(found)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("AppForge update available")
            box.setText(f"A new version of AppForge is available: {found.version} (you have {__version__}).")
            if blocker is None:
                box.setInformativeText("Do you want to update now? AppForge downloads the new version, "
                                       "replaces itself (the old build is kept as a backup) and restarts.")
                yes = box.addButton("Update now", QMessageBox.AcceptRole)
            else:
                box.setInformativeText(f"{blocker}\n\nOpen the download page instead?")
                yes = box.addButton("Open download page", QMessageBox.AcceptRole)
            box.addButton("Later", QMessageBox.RejectRole)
            box.exec()
            chosen = box.clickedButton() is yes
        finally:
            self._self_offer_open = False
        if not chosen:
            return
        if blocker is None:
            self._start_self_install(found)
        else:
            self._open_release_url(found.url)

    @staticmethod
    def _open_release_url(url: str):
        if url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url))

    def _start_self_install(self, found):
        job = SelfInstallJob(found)
        dlg = QProgressDialog(f"Downloading AppForge {found.version}…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("Updating AppForge")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.canceled.connect(job.cancel.set)
        job.signals.progress.connect(lambda done, total: self._on_self_progress(dlg, done, total))
        job.signals.done.connect(lambda result: self._on_self_done(found, dlg, result))
        self._self_install, self._self_progress = job, dlg
        self.check_pool.start(job)

    @staticmethod
    def _on_self_progress(dlg: QProgressDialog, done: int, total: int):
        if total:
            dlg.setMaximum(100)
            dlg.setValue(min(99, done * 100 // total))
            dlg.setLabelText(f"Downloading… {done / 1e6:.1f} / {total / 1e6:.1f} MB")
        else:
            dlg.setMaximum(0)

    def _on_self_done(self, found, dlg: QProgressDialog, result):
        dlg.close()
        dlg.deleteLater()
        self._self_install = self._self_progress = None
        if isinstance(result, InstallCancelled):
            return
        if not isinstance(result, InstallResult):
            box = QMessageBox(QMessageBox.Warning, "Couldn't update AppForge",
                              f"{result}\n\nThe version you are running was not changed.", parent=self)
            page = box.addButton("Open download page", QMessageBox.ActionRole)
            box.addButton("Close", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is page:
                self._open_release_url(found.url)
            return
        box = QMessageBox(QMessageBox.Information, "AppForge updated",
                          f"AppForge {found.version} is installed.", parent=self)
        box.setInformativeText("Restart now to start using it? Otherwise it takes effect the next time "
                               "you start AppForge.")
        restart = box.addButton("Restart now", QMessageBox.AcceptRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is restart and appimage_path() is not None:
            self.restart_requested = True
            self.quit_app()
            if self.restart_requested:      # quit_app() clears it again if the user cancelled the quit
                return
        self.statusBar().showMessage(f"AppForge {found.version} will be used the next time you start it", 8000)

    # -- idle checks, notifications, tray, settings (Phase 5) -----------------------------
    def _scheduled_check(self):
        """Timer tick: check apps whose last check is older than the configured interval."""
        if not self.settings.auto_check or self._batch is not None:
            return
        if any(isinstance(j, InstallJob) for j in self._jobs.values()):
            return
        self.check_updates(only_stale=True, stale_after=self.settings.check_interval_seconds)

    def _after_checks(self, user_initiated: bool):
        """All pending checks finished: tell the user about updates they haven't heard of yet."""
        pending = self.updates.pending_notifications()
        from_tray, self._tray_check = self._tray_check, False
        if not self._live:
            return
        if user_initiated or (self.isVisible() and self.isActiveWindow()):
            for e in pending:                       # they can see the cards: don't also pop up
                self.updates.mark_notified(e.id)
            return
        if not self.settings.notifications:
            return
        apps = [e for e in self.service.list_applications() if e.github_repo and not updates_suppressed(e)]
        failures = [(e.id, (e.metadata.get("update") or {}).get("message", "Check failed"))
                    for e in apps if e.update_status is UpdateStatus.FAILED]
        fresh_failures = [issue for issue in failures if issue not in self._issue_notified]
        self._issue_notified.update(failures)
        if pending:
            title, body = summarize_updates(pending)
            if failures:
                body += f"\nCould not check {len(failures)} application(s); open the library for details."
            self._notify(title, body)
            for e in pending:
                self.updates.mark_notified(e.id)
        elif fresh_failures:
            self._notify("Update checks failed",
                         f"Could not check {len(failures)} application(s). Open the library for details.")
        elif from_tray and not failures:
            # Already announced versions need no repeated balloon; failed or
            # unavailable sources must never produce an all-up-to-date claim.
            if any(e.update_status is UpdateStatus.UPDATE_AVAILABLE for e in apps):
                return
            incomplete = any(e.update_status is not UpdateStatus.UP_TO_DATE for e in apps)
            self._notify("AppForge", "Some update sources need attention. Open the library for details."
                         if incomplete else "Everything is up to date." if apps else "No active update sources to check.")

    def _notify(self, title: str, body: str):
        if not self.settings.notifications:
            return
        if self.tray is not None and self.tray.visible:
            self._tray_call("message", title, body)
            if self.tray is not None:
                return
        self.check_pool.start(_FnJob(send_desktop_notification, title, body))

    def _check_from_tray(self):
        self._tray_check = True
        self.check_updates()
        if not any(t == "Checking for updates…" for t, _ in self._busy.values()):
            self._after_checks(False)

    def bring_to_front(self):
        """Show the window whatever state it is in: hidden in the tray, minimized, or behind others.

        Used by the tray icon and when a second AppForge is started (that one exits and asks this
        instance to come forward instead of opening a duplicate).
        """
        self._tray_minimize_timer.stop()
        modal = QApplication.activeModalWidget()
        if self.isMinimized() or not self.isVisible():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
            self.showNormal()
        self.raise_()
        self.activateWindow()
        handle = self.windowHandle()
        if handle is not None:
            handle.requestActivate()          # Wayland: the compositor decides, but this is the proper ask
        if modal is not None and modal is not self:
            modal.raise_()                    # a dialog is open: keep it on top instead of reloading under it
            modal.activateWindow()
        else:
            self.reload()

        if self._pending_self_update is not None:
            found, self._pending_self_update = self._pending_self_update, None
            QTimer.singleShot(0, lambda: self._offer_self_update(found))

    show_from_tray = bring_to_front

    def show_initial(self, autostart=False):
        if (autostart and self.settings.start_at_login and self.settings.start_minimized
                and self.settings.run_in_background and self.tray is not None and self.tray.visible):
            self.hide()
        else:
            self.show()

    def showEvent(self, ev):
        super().showEvent(ev)
        handle = self.windowHandle()
        if handle is not None and handle is not self._tray_window_handle:
            self._tray_window_handle = handle
            handle.windowStateChanged.connect(self._native_window_state_changed)
            handle.visibilityChanged.connect(self._native_window_visibility_changed)

    def _native_window_state_changed(self, state):
        if state & Qt.WindowMinimized:
            self._tray_minimize_timer.start()
        else:
            self._tray_minimize_timer.stop()

    def _native_window_visibility_changed(self, visibility):
        if visibility == QWindow.Minimized:
            self._tray_minimize_timer.start()
        else:
            self._tray_minimize_timer.stop()

    def _minimize_to_tray(self):
        handle = self.windowHandle()
        native_minimized = handle is not None and (
            bool(handle.windowState() & Qt.WindowMinimized) or handle.visibility() == QWindow.Minimized)
        if self.isMinimized() or native_minimized:
            self._hide_to_tray()

    def apply_settings(self):
        """Apply preferences that affect the running window (tray icon, quit behaviour)."""
        background = bool(self.tray is not None and self.settings.run_in_background)
        if self.tray is not None:
            self._tray_call("set_visible", background)
            background = background and self.tray is not None
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(not background)
        if background and self._kwin_bridge is None and plasma_wayland(QGuiApplication.platformName()):
            try:
                self._kwin_bridge = KWinTrayBridge(self)
                self._kwin_bridge.minimized.connect(self._hide_to_tray)
                self._kwin_bridge.failed.connect(self._kwin_bridge_failed)
            except Exception as exc:
                log.warning("Could not initialize KWin tray integration", exc_info=True)
                self._kwin_bridge_failed(str(exc))
        if self._kwin_bridge is not None:
            self._kwin_bridge.set_enabled(background)

    def _kwin_bridge_failed(self, message):
        self.statusBar().showMessage(
            "KDE minimize-to-tray is unavailable. Closing still hides to the tray. " + message, 15000)

    def _stop_kwin_bridge(self):
        if self._kwin_bridge is not None:
            self._kwin_bridge.set_enabled(False)

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.tray is not None, self)
        dlg.exportRequested.connect(lambda: self.open_library_transfer("export", dlg))
        dlg.importRequested.connect(lambda: self.open_library_transfer("import", dlg))
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.apply_settings()
            theme.apply_theme(QApplication.instance(), self.settings.theme_mode,
                              self.settings.card_badge_colors)
            self.statusBar().showMessage("Settings saved", 3000)

    def open_library_transfer(self, mode, parent=None):
        from .library_transfer_dialog import LibraryTransferDialog
        dialog = LibraryTransferDialog(self.service, mode, parent or self)
        dialog.libraryChanged.connect(self.reload)
        dialog.exec()
        self.reload()

    def quit_app(self):
        """Really quit (the window's close button only hides it while background running is on)."""
        self._quitting = True
        if self.close():
            QApplication.quit()
        else:
            self._quitting = False
            self.restart_requested = False

    def show_release_notes(self, app_id: str):
        if not self.service.get(app_id):
            return
        if app_id not in self._release_notes:
            from .release_notes_dialog import ReleaseNotesDialog
            dialog = ReleaseNotesDialog(self.service, app_id, self._client,
                                        self.settings.effective_github_token(), self)
            dialog.finished.connect(lambda _: self._release_notes.pop(app_id, None))
            dialog.finished.connect(dialog.deleteLater)
            self._release_notes[app_id] = dialog
        dialog = self._release_notes[app_id]
        dialog.sync()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_release_page(self, app_id: str):
        entry = self.service.get(app_id)
        url = ((entry.metadata.get("update") or {}).get("release_url")) if entry else None
        if url and url.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(url))

    def set_prereleases_enabled(self, app_id: str, enabled: bool):
        entry = self.service.get(app_id)
        if not entry or not entry.github_repo or app_id in self._busy:
            return
        self.service.update_application(app_id, settings={"include_prereleases": enabled})
        self._recheck_update_preferences(app_id)

    def _recheck_update_preferences(self, app_id: str):
        # A cached install target must not survive a change of update channel.
        entry = self.updates.clear_update_state(app_id)
        self._refresh_card(app_id)
        if entry and updates_paused(entry):
            self.statusBar().showMessage("Update preferences saved. Resume updates to check this app.", 6000)
        else:
            self.check_updates([app_id], user_initiated=True)

    def choose_asset(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry or app_id in self._busy:
            return
        info = entry.metadata.get("update") or {}
        assets = [a for a in info.get("assets", [])
                  if is_candidate_name(a["name"], entry.format) and compatible_arch(a["name"], host_arch())]
        name = self._pick_asset(assets, (info.get("asset") or {}).get("name"),
                                "Pick the file AppForge should download for this app.")
        if name and app_id not in self._busy:
            excluded_pre = (not entry.metadata.get("include_prereleases")
                            and (info.get("prereleases_only")
                                 or (info.get("notes") or {}).get("prerelease")))
            if excluded_pre:
                answer = QMessageBox.question(
                    self, "Enable pre-releases?",
                    f"The selected release for “{entry.name}” is a pre-release/nightly build.\n\n"
                    "Enable pre-release updates for this app and check the selected file? "
                    "Pre-release builds may be less stable.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes or app_id in self._busy:
                    return
            self.updates.set_asset_pattern(app_id, name)
            if excluded_pre:
                self.service.update_application(app_id, settings={"include_prereleases": True})
            self._recheck_update_preferences(app_id)

    def _pick_asset(self, assets: list[dict], preselect: str | None, message: str) -> str | None:
        if not assets:
            QMessageBox.information(self, "No files", "This release has no files to choose from.")
            return None
        dlg = AssetPickerDialog(assets, preselect, message, self)
        return dlg.chosen if dlg.exec() == AssetPickerDialog.Accepted else None

    # -- installing updates -------------------------------------------------------------
    def start_update(self, app_id: str, from_batch: bool = False):
        entry = self.service.get(app_id)
        if not entry or app_id in self._busy or not can_update(entry):
            return
        info = entry.metadata["update"]
        if info.get("comparison") == "checksum" and not from_batch:
            if QMessageBox.question(self, "Version ordering unknown",
                                    info.get("message", "") + "\n\nInstall this release file?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        if info.get("ambiguous") and not entry.metadata.get("asset_pattern"):
            cands = info.get("candidates") or info.get("assets", [])
            name = self._pick_asset(cands, (info.get("asset") or {}).get("name"),
                                    "Several files in this release could match. Choose the right one.")
            if not name:
                return
            entry = self.updates.set_asset_pattern(app_id, name) or entry
            info = entry.metadata["update"]
        job = InstallJob(app_id, entry.path, info["asset"], info.get("assets", []), entry.installed_version,
                         entry.format)
        job.signals.progress.connect(self._on_install_progress)
        job.signals.done.connect(self._on_install_done)
        self._jobs[app_id] = job
        self._set_busy(app_id, "Waiting…", None)
        self.install_pool.start(job)
        self._refresh_header()

    def update_all(self):
        if self._batch is not None:
            return
        ready, skipped = [], []
        for c in self._cards:
            e = c.entry
            if not (can_update(e) and e.id not in self._busy and file_state(e) is FileState.OK):
                continue
            (skipped if e.metadata["update"].get("ambiguous") and not e.metadata.get("asset_pattern")
             else ready).append(e)
        if not ready:
            if skipped:
                QMessageBox.information(self, "Choose a file first",
                                        "These updates need you to choose a release file first (use each app's Update button):\n\n"
                                        + "\n".join(e.name for e in skipped))
            return
        lines = "\n".join(f"•  {e.name}:  {e.installed_version or '?'}  →  {e.latest_version}" for e in ready)
        box = QMessageBox(QMessageBox.Question, "Update all", f"Update {len(ready)} application"
                          f"{'s' if len(ready) != 1 else ''}?", parent=self)
        uncertain = [e.name for e in ready if e.metadata["update"].get("comparison") == "checksum"]
        if uncertain:
            lines += ("\n\nVersion ordering is unknown for: " + ", ".join(uncertain)
                      + ". Their release files have different checksums; review their release notes before updating.")
        box.setInformativeText(lines + "\n\nThe current version of each app is kept as a backup next to its file.")
        go = box.addButton("Update", QMessageBox.AcceptRole)
        notes_btn = box.addButton("Release notes…", QMessageBox.ActionRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        while True:
            box.exec()
            if box.clickedButton() is not notes_btn:
                break
            self._show_batch_notes(ready)
        if box.clickedButton() is not go:
            return
        self._batch = {"total": len(ready), "done": 0, "ok": [], "failed": [], "ids": {e.id for e in ready}}
        self.statusBar().showMessage(f"Updating {len(ready)} applications…")
        for e in ready:
            self.start_update(e.id, from_batch=True)
        self._refresh_header()

    def _show_batch_notes(self, entries):
        choices = [f"{e.name} — {e.latest_version} ({i + 1})" for i, e in enumerate(entries)]
        selected, ok = QInputDialog.getItem(self, "Release notes", "Application:", choices, 0, False)
        if ok:
            entry = entries[choices.index(selected)]
            self.show_release_notes(entry.id)
            self._release_notes[entry.id].exec()

    def _on_install_progress(self, app_id: str, done: int, total: int):
        if total:
            text = f"Downloading… {done * 100 // total}%  ({done / 1e6:.1f} / {total / 1e6:.1f} MB)"
            self._set_busy(app_id, text, done / total)
        else:
            self._set_busy(app_id, f"Downloading… {done / 1e6:.1f} MB", None)

    def _on_install_done(self, app_id: str, result):
        self._jobs.pop(app_id, None)
        entry = self.service.get(app_id)
        name = entry.name if entry else "Application"
        ok = isinstance(result, InstallResult)
        cancelled = isinstance(result, InstallCancelled)
        if ok:
            new = self.updates.apply_install(app_id, result, (entry.metadata.get("update") or {}).get("tag"))
            msg = f"Updated {name} to {new.installed_version}" if new else f"Updated {name}"
            self.statusBar().showMessage(msg, 6000)
        elif not cancelled:
            self.updates.apply_install_failure(app_id, str(result))
        self._set_busy(app_id, None, rebuild=True)

        in_batch = bool(self._batch and app_id in self._batch["ids"])
        if in_batch:
            self._batch["done"] += 1
            if ok:
                self._batch["ok"].append(name)
            elif not cancelled:
                self._batch["failed"].append((name, str(result)))
            self._refresh_tray()
            if self._batch["done"] >= self._batch["total"]:
                b, self._batch = self._batch, None
                self._refresh_header()
                self._show_batch_summary(b)
        elif not ok and not cancelled and (self.isVisible() and self.isActiveWindow()):
            QMessageBox.warning(self, f"Couldn't update {name}",
                                f"{result}\n\nYour existing version was not changed.")

        if not in_batch and not cancelled and not (self.isVisible() and self.isActiveWindow()):
            self._notify("Application updated" if ok else "Application update failed",
                         msg if ok else f"{name}: {result}. Open the library for details.")

    def _show_batch_summary(self, b: dict):
        self.statusBar().showMessage(f"Updated {len(b['ok'])} of {b['total']} applications", 6000)
        if not (self.isVisible() and self.isActiveWindow()):
            self._notify("AppForge updates finished",
                         f"{len(b['ok'])} updated, {len(b['failed'])} failed, "
                         f"{b['total'] - len(b['ok']) - len(b['failed'])} cancelled. "
                         "Open the library for details.")
            return
        if b["failed"]:
            box = QMessageBox(QMessageBox.Warning, "Some updates failed",
                              f"{len(b['ok'])} updated, {len(b['failed'])} failed. "
                              "The failed apps were not changed.", parent=self)
            box.setInformativeText("\n".join(f"•  {n}: {m}" for n, m in b["failed"]))
            box.exec()

    # -- backups & rollback -------------------------------------------------------------
    def show_backups(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return self.reload()
        if app_id in self._busy:
            QMessageBox.information(self, "Busy", f"“{entry.name}” is being checked or updated right now.")
            return
        dlg = BackupsDialog(self.updates.backups, entry, self)
        dlg.exec()
        if dlg.changed:
            self.reload()
            after = self.service.get(app_id)
            if after:
                self.statusBar().showMessage(
                    f"{after.name} is now at {after.installed_version or 'the restored version'}", 6000)
                if after.github_repo:
                    self.check_updates([app_id])

    # -- application menu (launcher) integration ---------------------------------------
    def toggle_desktop_entry(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return self.reload()
        enable = not self.service.desktop_enabled(entry)
        try:
            self.service.set_desktop_integration(app_id, enable)
        except LibraryError as exc:
            QMessageBox.warning(self, "Couldn't update the application menu", str(exc))
            return
        self._refresh_card(app_id)
        self.statusBar().showMessage(
            f"Added {entry.name} to the application menu" if enable
            else f"Removed {entry.name} from the application menu", 4000)

    # -- other actions ------------------------------------------------------------------
    def show_storage(self):
        from .storage_dialog import StorageDialog
        dialog = StorageDialog(self.service, self.updates.backups, self._busy, self)
        dialog.exec()
        self.reload()
        dialog.deleteLater()

    def discover_applications(self):
        from .discovery_dialog import DiscoveryDialog
        dialog = DiscoveryDialog(self.service, self)
        if hasattr(dialog, "preferencesChanged"):
            dialog.preferencesChanged.connect(self.discovery_watcher.poll)
        dialog.exec()
        self.discovery_watcher.poll()
        self.reload()
        dialog.deleteLater()

    def _discovery_found(self, result):
        count = len(result.candidates)
        self.discovery_found_btn.setText(
            f"{count} new app{'s' if count != 1 else ''} found — Review…")
        self.discovery_found_btn.setToolTip("\n".join(result.errors) or
                                           "Review new apps before adding them to your library.")
        self.discovery_found_btn.setVisible(bool(count))

    def review_discovered(self):
        from .discovery_dialog import DiscoveryDialog
        self.discovery_watcher.prune_registered()
        if not self.discovery_watcher.result.candidates:
            return
        dialog = DiscoveryDialog(self.service, self, preview=self.discovery_watcher.result)
        dialog.preferencesChanged.connect(self.discovery_watcher.poll)
        dialog.exec()
        self.discovery_watcher.poll()
        self.reload()
        dialog.deleteLater()

    def add_application(self, initial_path: str | None = None):
        downloaded = None
        if not isinstance(initial_path, str):
            from .download_dialog import AddSourceDialog, DownloadApplicationDialog
            source = AddSourceDialog(self)
            accepted = source.exec() == AddSourceDialog.Accepted
            mode = source.mode
            source.deleteLater()
            if not accepted:
                return
            if mode == "link":
                download = DownloadApplicationDialog(self.service, self, client=self._client,
                                                       token=self.settings.effective_github_token())
                accepted = download.exec() == DownloadApplicationDialog.Accepted
                downloaded = download.downloaded
                download.deleteLater()
                if not accepted or not downloaded:
                    return
                initial_path = downloaded.path
        dlg = AddApplicationDialog(self.service, self, initial_path if isinstance(initial_path, str) else None,
                                   downloaded=downloaded)
        if dlg.exec() == AddApplicationDialog.Accepted and dlg.added:
            self.reload()
            msg = f"Added {dlg.added.name}"
            if dlg.menu_requested and not self.service.desktop_enabled(dlg.added):
                msg += " (couldn't add it to the application menu)"
            self.statusBar().showMessage(msg, 5000)
            if dlg.added.github_repo:
                self.check_updates([dlg.added.id])

    @staticmethod
    def _update_fingerprint(e: AppEntry | None):
        return None if e is None else (e.github_repo, e.installed_version,
                                       e.metadata.get("include_prereleases"), e.metadata.get("asset_pattern"))

    def edit_application(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return self.reload()
        before = self._update_fingerprint(entry)
        dlg = EditApplicationDialog(self.service, entry, self)
        if dlg.exec() == EditApplicationDialog.Accepted:
            self.reload()
            self.statusBar().showMessage("Changes saved", 3000)
            after = self.service.get(app_id)
            if after and after.github_repo and self._update_fingerprint(after) != before:
                self.check_updates([app_id])

    def remove_application(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return self.reload()
        if app_id in self._busy:
            QMessageBox.information(self, "Busy", f"“{entry.name}” is being checked or updated right now.")
            return
        box = QMessageBox(QMessageBox.Question, "Remove from library",
                          f"Remove “{entry.name}” from the library?", parent=self)
        box.setInformativeText("The AppImage file (and any backups) stay where they are; "
                               "only the library entry is removed.")
        remove = box.addButton("Remove", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is remove:
            self.service.remove_application(app_id)
            self.reload()
            self.statusBar().showMessage(f"Removed {entry.name}", 4000)

    def launch(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return self.reload()
        try:
            handle = launcher.launch(entry)
        except launcher.LaunchError as exc:
            if exc.state is FileState.MISSING:
                self.reload()
            self._launch_failed(entry.id, str(exc), exc.state)
            return
        self.shortcuts.launched(app_id)
        self.statusBar().showMessage(f"Launching {entry.name}…", 3000)
        QTimer.singleShot(2500, lambda: self._check_started(entry.name, handle))

    def _launch_failed(self, app_id: str, message: str, state):
        self.bring_to_front()
        if state is FileState.NOT_EXECUTABLE:
            if QMessageBox.question(self, "Not executable", message + "\n\nMake it executable and launch?") \
                    == QMessageBox.Yes:
                self.make_executable(app_id, then_launch=True)
        elif state is FileState.MISSING:
            if QMessageBox.question(self, "File not found", message + "\n\nLocate the file now?") \
                    == QMessageBox.Yes:
                self.locate_file(app_id)
        else:
            QMessageBox.warning(self, "Can't launch", message)

    def _check_started(self, name: str, handle: launcher.LaunchHandle):
        code = handle.early_exit_code()
        if code not in (None, 0):
            self.bring_to_front()
            tail = handle.log_tail()
            box = QMessageBox(QMessageBox.Warning, "Application closed unexpectedly",
                              f"“{name}” exited right after starting (exit code {code}).", parent=self)
            if tail:
                box.setDetailedText(tail)
            box.exec()

    def make_executable(self, app_id: str, then_launch: bool = False):
        entry = self.service.get(app_id)
        if not entry:
            return
        try:
            launcher.make_executable(entry.path)
        except OSError as exc:
            QMessageBox.warning(self, "Couldn't change permissions", f"{entry.path}\n\n{exc.strerror or exc}")
            return
        self.reload()
        if then_launch:
            self.launch(app_id)

    def _choose_relocation(self, entry: AppEntry, candidates: list[Path]) -> str | None:
        """Offer files that look like the missing app. Returns a path, ``""`` for "browse", None = cancel."""
        if len(candidates) == 1:
            box = QMessageBox(QMessageBox.Question, "Possible match found",
                              f"“{entry.name}” may have been moved or renamed.", parent=self)
            box.setInformativeText(f"Found:\n{candidates[0]}\n\nReconnect to this file?")
            use = box.addButton("Use this file", QMessageBox.AcceptRole)
            browse = box.addButton("Browse…", QMessageBox.ActionRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is use:
                return str(candidates[0])
            return "" if box.clickedButton() is browse else None
        other = "Browse for another file…"
        items = [str(c) for c in candidates] + [other]
        choice, ok = QInputDialog.getItem(
            self, "Possible matches found",
            f"“{entry.name}” may have been moved or renamed. Pick the right file:", items, 0, False)
        if not ok:
            return None
        return "" if choice == other else choice

    def locate_file(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return
        path = ""
        try:
            candidates = self.service.suggest_relocations(app_id)
        except Exception:  # noqa: BLE001 - suggestions are a convenience, never a blocker
            log.warning("Relocation search failed", exc_info=True)
            candidates = []
        if candidates:
            picked = self._choose_relocation(entry, candidates)
            if picked is None:
                return
            path = picked
        if not path:
            start = str(Path(entry.path).parent) if Path(entry.path).parent.exists() else str(Path.home())
            path, _ = QFileDialog.getOpenFileName(self, f"Locate {entry.name}", start, FILE_FILTER)
        if not path:
            return
        try:
            self.service.update_application(app_id, path=path)
            self.service.refresh_metadata(app_id)
        except LibraryError as exc:
            QMessageBox.warning(self, "Can't use that file", str(exc))
            return
        self.reload()
        self.statusBar().showMessage(f"{entry.name} reconnected", 4000)

    def show_in_file_manager(self, app_id: str):
        entry = self.service.get(app_id)
        if not entry:
            return
        p = Path(entry.path)
        if not p.parent.exists():
            QMessageBox.information(self, "Folder not found", f"The folder no longer exists:\n{p.parent}")
            return
        if p.exists() and (fm := shutil.which("dolphin")):
            try:
                subprocess.Popen([fm, "--select", str(p)], env=launcher.clean_environment(),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def copy_path(self, app_id: str):
        entry = self.service.get(app_id)
        if entry:
            QGuiApplication.clipboard().setText(entry.path)
            self.statusBar().showMessage("Path copied", 2500)

    # -- drag & drop / lifecycle --------------------------------------------------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() and any(u.isLocalFile() for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        files = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if files:
            ev.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.add_application(files[0]))

    def _hide_to_tray(self):
        if (self._quitting or self.tray is None or not self.tray.visible
                or not self.settings.run_in_background):
            return False
        QSettings().setValue("geometry", self.saveGeometry())
        self._tray_minimize_timer.stop()
        self.hide()
        # Explicitly unmap the platform window too: its minimized/visible state
        # can lead the QWidget state during compositor-driven minimization.
        handle = self.windowHandle()
        if handle is not None:
            handle.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        if handle is not None:
            handle.setWindowState(handle.windowState() & ~Qt.WindowMinimized)
        if not self._tray_hint_shown and self.settings.notifications:
            self._tray_hint_shown = True
            self._tray_call("message", "AppForge is still running",
                            "It keeps checking for updates. Use the tray icon to open or quit it.")
        return True

    def closeEvent(self, ev):
        if self._hide_to_tray():
            ev.ignore()
            return
        installing = [j for j in self._jobs.values() if isinstance(j, InstallJob)]
        if installing:
            if QMessageBox.question(self, "Updates in progress",
                                    "An update is still downloading. Cancel it and quit?\n"
                                    "(Your current version stays untouched.)") != QMessageBox.Yes:
                ev.ignore()
                return
            for j in installing:
                j.cancel.set()
            self.install_pool.waitForDone(8000)
        QSettings().setValue("geometry", self.saveGeometry())
        for dialog in list(self._details.values()) + list(self._release_notes.values()):
            dialog.close()
        self._stop_kwin_bridge()
        self.discovery_watcher.stop()
        super().closeEvent(ev)
