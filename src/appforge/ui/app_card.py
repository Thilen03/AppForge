"""One application card in the library grid."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ..core.formats import get_format
from ..core.library import DESKTOP_FLAG, FileState
from ..core.models import AppEntry, UpdateStatus
from ..core.updates.service import can_update
from . import theme
from .icons import app_pixmap
from .popups import RoundedMenu

CARD_W, CARD_H, ICON = 340, 168, 64


class _DotsButton(QToolButton):
    """Three-dot menu button painted by hand so it never depends on font glyphs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolTip("More actions")
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("More actions")

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.tokens().muted))
        cx, cy = self.width() / 2, self.height() / 2
        for dx in (-7, 0, 7):
            p.drawEllipse(QPoint(int(cx + dx), int(cy)), 2, 2)


class AppCard(QFrame):
    detailsRequested = Signal(str)
    launchRequested = Signal(str)
    editRequested = Signal(str)
    removeRequested = Signal(str)
    openFolderRequested = Signal(str)
    copyPathRequested = Signal(str)
    relinkRequested = Signal(str)
    makeExecutableRequested = Signal(str)
    updateRequested = Signal(str)
    checkRequested = Signal(str)
    releasePageRequested = Signal(str)
    releaseNotesRequested = Signal(str)
    chooseAssetRequested = Signal(str)
    backupsRequested = Signal(str)
    desktopToggleRequested = Signal(str)

    def __init__(self, entry: AppEntry, state: FileState, busy: tuple[str, float | None] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.entry, self.state = entry, state
        self.setObjectName("card")
        self.setFixedSize(CARD_W, CARD_H)
        self.setProperty("missing", state in (FileState.MISSING, FileState.NOT_A_FILE))
        self.setAttribute(Qt.WA_Hover, True)
        self._menu_open = False
        self._build()
        if busy:
            self.set_busy(*busy)

    # -- construction -------------------------------------------------------------------
    def _status_chip(self) -> tuple[str, str, str]:
        """(text, kind, tooltip) for the update-status chip."""
        e = self.entry
        info = e.metadata.get("update") or {}
        msg = info.get("message") or ""
        if not e.github_repo:
            return "No update source", "muted", "Add a repository URL as update source in Edit to enable updates."
        if e.update_status is UpdateStatus.UNAVAILABLE and info.get("prereleases_only"):
            return "Pre-releases available", "muted", msg
        return {
            UpdateStatus.UP_TO_DATE: ("Up to date", "ok", ""),
            UpdateStatus.UPDATE_AVAILABLE: ("Update available", "update", msg),
            UpdateStatus.CHECKING: ("Checking for updates…", "muted", ""),
            UpdateStatus.FAILED: ("Update failed", "danger", msg),
            UpdateStatus.UNAVAILABLE: ("Update info unavailable", "muted",
                                       msg or "Not checked yet."),
        }[e.update_status]

    def _build(self):
        e, missing = self.entry, self.property("missing")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 12, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(14)
        icon = QLabel(objectName="iconTile")
        icon.setPixmap(app_pixmap(e.icon_path, e.name, ICON, self.devicePixelRatioF()))
        icon.setFixedSize(ICON, ICON)
        if missing:
            eff = QGraphicsOpacityEffect(icon)
            eff.setOpacity(0.45)
            icon.setGraphicsEffect(eff)
        top.addWidget(icon, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel(objectName="cardName")
        name.setText(QFontMetrics(name.font()).elidedText(e.name, Qt.ElideRight, CARD_W - ICON - 70))
        name.setToolTip(e.name)
        info.addWidget(name)
        version = QLabel(objectName="cardMeta")
        text = f"Version {e.installed_version}" if e.installed_version else "Version unknown"
        if e.latest_version and e.update_status in (UpdateStatus.UPDATE_AVAILABLE, UpdateStatus.FAILED) \
                and can_update(e):
            text += f"  →  {e.latest_version}"
        version.setText(text)
        info.addWidget(version)

        self._chips_w = QWidget()
        chips = QHBoxLayout(self._chips_w)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        fmt = get_format(e.format)
        chips.addWidget(self._chip(fmt.display_name if fmt else e.format, "accent"))
        if missing:
            chips.addWidget(self._chip("File not found", "danger"))
        elif self.state is FileState.NOT_EXECUTABLE:
            chips.addWidget(self._chip("Not executable", "danger"))
        else:
            t, kind, tip = self._status_chip()
            chips.addWidget(self._chip(t, kind, tip))
        chips.addStretch(1)
        info.addWidget(self._chips_w)

        self._busy_w = QWidget()
        bl = QVBoxLayout(self._busy_w)
        bl.setContentsMargins(0, 2, 0, 0)
        bl.setSpacing(4)
        self._busy_lbl = QLabel(objectName="cardMeta")
        self._busy_bar = QProgressBar(textVisible=False)
        bl.addWidget(self._busy_lbl)
        bl.addWidget(self._busy_bar)
        self._busy_w.hide()
        info.addWidget(self._busy_w)
        info.addStretch(1)
        top.addLayout(info, 1)
        root.addLayout(top)

        path = QLabel(objectName="cardPath")
        path.setText(QFontMetrics(path.font()).elidedText(e.path, Qt.ElideMiddle, CARD_W - 36))
        path.setToolTip(e.path)
        root.addWidget(path)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        if missing:
            self._primary = QPushButton("Locate file…", objectName="primary")
            self._primary.clicked.connect(lambda: self.relinkRequested.emit(e.id))
        elif self.state is FileState.NOT_EXECUTABLE:
            self._primary = QPushButton("Make executable", objectName="primary")
            self._primary.clicked.connect(lambda: self.makeExecutableRequested.emit(e.id))
        else:
            self._primary = QPushButton("Launch", objectName="primary")
            self._primary.clicked.connect(lambda: self.launchRequested.emit(e.id))
        self._primary.setCursor(Qt.PointingHandCursor)
        self._primary.setMinimumWidth(88)
        bottom.addWidget(self._primary)

        self._update_btn = None
        if self.state is FileState.OK and can_update(e):
            retry = e.update_status is UpdateStatus.FAILED
            self._update_btn = QPushButton("Retry update" if retry else "Update", objectName="soft")
            self._update_btn.setCursor(Qt.PointingHandCursor)
            self._update_btn.setToolTip(f"Update to {e.latest_version}")
            self._update_btn.clicked.connect(lambda: self.updateRequested.emit(e.id))
            bottom.addWidget(self._update_btn)
        bottom.addStretch(1)

        self._actions = QWidget()
        al = QHBoxLayout(self._actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(2)
        edit = QPushButton("Edit", objectName="ghost")
        edit.setCursor(Qt.PointingHandCursor)
        edit.clicked.connect(lambda: self.editRequested.emit(e.id))
        al.addWidget(edit)
        more = _DotsButton()
        more.setMenu(self._build_menu())
        al.addWidget(more)
        bottom.addWidget(self._actions)
        root.addLayout(bottom)

        self._fx = QGraphicsOpacityEffect(self._actions)
        self._fx.setOpacity(0.0)
        self._actions.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        for w in (edit, more):
            w.installEventFilter(self)  # keyboard focus also reveals the actions

    @staticmethod
    def _chip(text: str, kind: str, tip: str = "") -> QLabel:
        c = QLabel(text, objectName="chip")
        c.setProperty("kind", kind)
        if tip:
            c.setToolTip(tip)
        return c

    def _build_menu(self) -> RoundedMenu:
        e = self.entry
        info = e.metadata.get("update") or {}
        m = RoundedMenu(self)
        m.setToolTipsVisible(True)
        m.addAction("Details…", lambda: self.detailsRequested.emit(e.id))
        m.addAction("Edit information…", lambda: self.editRequested.emit(e.id))
        if e.github_repo:
            m.addSeparator()
            m.addAction("Check for updates", lambda: self.checkRequested.emit(e.id))
            if info.get("tag"):
                m.addAction("Release notes…", lambda: self.releaseNotesRequested.emit(e.id))
            if info.get("release_url"):
                m.addAction("View release page", lambda: self.releasePageRequested.emit(e.id))
            if info.get("assets"):
                m.addAction("Choose release asset…", lambda: self.chooseAssetRequested.emit(e.id))
        m.addSeparator()
        m.addAction("Backups && rollback…", lambda: self.backupsRequested.emit(e.id))
        on_menu = bool(e.metadata.get(DESKTOP_FLAG))
        menu_act = m.addAction("Remove from application menu" if on_menu else "Add to application menu",
                               lambda: self.desktopToggleRequested.emit(e.id))
        # a launcher for a missing / non-executable file would be hidden by the desktop anyway
        menu_act.setEnabled(on_menu or self.state is FileState.OK)
        menu_act.setToolTip("Creates a launcher in your desktop's application menu (a .desktop file in "
                            "~/.local/share/applications). The AppImage itself is not touched.")
        m.addSeparator()
        m.addAction("Show in file manager", lambda: self.openFolderRequested.emit(e.id))
        m.addAction("Copy file path", lambda: self.copyPathRequested.emit(e.id))
        if self.state in (FileState.MISSING, FileState.NOT_A_FILE):
            m.addAction("Locate file…", lambda: self.relinkRequested.emit(e.id))
        elif self.state is FileState.NOT_EXECUTABLE:
            m.addAction("Make executable", lambda: self.makeExecutableRequested.emit(e.id))
        m.addSeparator()
        m.addAction("Remove from library…", lambda: self.removeRequested.emit(e.id))
        m.aboutToShow.connect(lambda: self._set_menu_open(True))
        m.aboutToHide.connect(lambda: self._set_menu_open(False))
        return m

    # -- busy state (checking / downloading) --------------------------------------------
    def set_busy(self, text: str | None, fraction: float | None = None):
        """Show a progress row instead of the status chips. ``text=None`` restores the chips."""
        busy = text is not None
        self._chips_w.setVisible(not busy)
        self._busy_w.setVisible(busy)
        if self._update_btn:
            self._update_btn.setVisible(not busy)
        if busy:
            self._busy_lbl.setText(text)
            if fraction is None:
                self._busy_bar.setRange(0, 0)
            else:
                self._busy_bar.setRange(0, 1000)
                self._busy_bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))

    # -- hover / focus reveal -----------------------------------------------------------
    def _set_menu_open(self, open_: bool):
        self._menu_open = open_
        self._reveal(open_ or self.underMouse())

    def _reveal(self, show: bool):
        self.setProperty("hot", show)
        self.style().unpolish(self)
        self.style().polish(self)
        self._anim.stop()
        self._anim.setEndValue(1.0 if show else 0.0)
        self._anim.setStartValue(self._fx.opacity())
        self._anim.start()

    def enterEvent(self, ev):
        self._reveal(True)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        if not self._menu_open:
            self._reveal(False)
        super().leaveEvent(ev)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.FocusIn:
            self._reveal(True)
        elif ev.type() == QEvent.FocusOut and not self._menu_open and not self.underMouse():
            self._reveal(False)
        return super().eventFilter(obj, ev)

    def mouseDoubleClickEvent(self, ev):
        if self.state is FileState.OK:
            self.launchRequested.emit(self.entry.id)
        super().mouseDoubleClickEvent(ev)
