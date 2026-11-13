"""Popups with truly rounded corners, and the drop-down arrow of combo boxes.

The stylesheet gives menus and combo-box lists a ``border-radius``, but Qt draws those popups in a
square, opaque top-level window - so the corners showed the square window behind the rounded
border.

* Menus: the popup window is made frameless + translucent, so the rounded shape is all that is
  painted.
* Combo boxes (0.5.4): the same translucent trick left a glitchy black box on some systems (no
  compositing / Fusion + stylesheet), both in the popup and over the arrow button.  The combo popup
  therefore stays an ordinary opaque window and is clipped to a rounded shape with a mask, and the
  arrow is drawn by the widget itself instead of by the style's drop-down sub-control.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QBitmap, QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QMenu, QWidget

POPUP_RADIUS = 10

_COMBO_CONTAINER = "QComboBoxPrivateContainer"


def _is_combo_container(widget: QWidget) -> bool:
    return widget.metaObject().className() == _COMBO_CONTAINER


def _rounded_mask(width: int, height: int, radius: int) -> QRegion:
    bm = QBitmap(max(width, 1), max(height, 1))
    bm.fill(Qt.color0)
    p = QPainter(bm)
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setPen(Qt.NoPen)
    p.setBrush(Qt.color1)
    p.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)
    p.end()
    return QRegion(bm)


class _MaskKeeper(QObject):
    """Keeps a combo popup clipped to a rounded rectangle whenever it is shown or resized."""

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Show, QEvent.Resize) and isinstance(obj, QWidget):
            obj.setMask(_rounded_mask(obj.width(), obj.height(), POPUP_RADIUS))
        return False


def round_combo_popup(container: QWidget) -> None:
    """Round a combo-box list without making its window translucent (idempotent)."""
    if container.property("_rounded") or not isinstance(container, QFrame):
        return
    container.setProperty("_rounded", True)
    container.setFrameShape(QFrame.NoFrame)      # the style's own square frame would show at the corners
    container.setAutoFillBackground(True)        # opaque: no translucent window, hence no black box
    keeper = _MaskKeeper(container)
    container.installEventFilter(keeper)
    if container.isVisible():
        container.setMask(_rounded_mask(container.width(), container.height(), POPUP_RADIUS))


def round_popup(widget: QWidget) -> None:
    """Round a popup: menus become frameless + translucent, combo lists get a mask (idempotent)."""
    if _is_combo_container(widget):
        round_combo_popup(widget)
        return
    flags = Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    if (widget.windowFlags() & flags) != flags:
        widget.setWindowFlags(widget.windowFlags() | flags)
    widget.setAttribute(Qt.WA_TranslucentBackground, True)


class RoundedMenu(QMenu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        round_popup(self)


class RoundedComboBox(QComboBox):
    """Combo box with a rounded, artefact-free list and a self-drawn chevron."""

    ARROW_AREA = 26

    def showPopup(self):
        round_popup(self.view().window())
        super().showPopup()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        from . import theme
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(t.muted if not self.isEnabled() else t.text)
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy = self.width() - self.ARROW_AREA / 2 - 1, self.height() / 2
        chevron = QPainterPath()
        chevron.moveTo(QPointF(cx - 4, cy - 2))
        chevron.lineTo(QPointF(cx, cy + 2))
        chevron.lineTo(QPointF(cx + 4, cy - 2))
        p.drawPath(chevron)
        p.end()


class _PopupFilter(QObject):
    """Rounds every other popup the app creates (context menus, ``QInputDialog`` lists, …)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Polish and isinstance(obj, QWidget) and not obj.isVisible():
            if isinstance(obj, QMenu) or _is_combo_container(obj):
                round_popup(obj)
        return False


_filter: _PopupFilter | None = None


def install_popup_rounding(app: QApplication) -> None:
    global _filter
    if _filter is None:
        _filter = _PopupFilter(app)
        app.installEventFilter(_filter)
