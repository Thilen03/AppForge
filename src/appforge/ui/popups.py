"""Popups with truly rounded corners.

The stylesheet gives menus and combo-box lists a ``border-radius``, but Qt draws those popups in a
square, opaque top-level window - so the corners showed the square window behind the rounded
border.  Making the popup window frameless + translucent lets the rounded shape be the only thing
that is painted.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QMenu, QWidget

_COMBO_CONTAINER = "QComboBoxPrivateContainer"


def round_popup(widget: QWidget) -> None:
    """Make a popup window frameless and translucent (idempotent)."""
    flags = Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    if (widget.windowFlags() & flags) != flags:
        widget.setWindowFlags(widget.windowFlags() | flags)
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    if isinstance(widget, QFrame) and widget.metaObject().className() == _COMBO_CONTAINER:
        widget.setFrameShape(QFrame.NoFrame)          # the style's own square frame would show at the corners


class RoundedMenu(QMenu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        round_popup(self)


class RoundedComboBox(QComboBox):
    def showPopup(self):
        round_popup(self.view().window())
        super().showPopup()


class _PopupFilter(QObject):
    """Rounds every other popup the app creates (context menus, ``QInputDialog`` lists, …)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Polish and isinstance(obj, QWidget) and not obj.isVisible():
            if isinstance(obj, QMenu) or obj.metaObject().className() == _COMBO_CONTAINER:
                round_popup(obj)
        return False


_filter: _PopupFilter | None = None


def install_popup_rounding(app: QApplication) -> None:
    global _filter
    if _filter is None:
        _filter = _PopupFilter(app)
        app.installEventFilter(_filter)
