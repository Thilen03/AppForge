"""Wrapping grid layout (adapted from the classic Qt FlowLayout example)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidgetItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing: int = 16, v_spacing: int = 16):
        super().__init__(parent)
        self._items = []
        self._h, self._v = h_spacing, v_spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def replace_widget(self, old, new) -> bool:
        """Swap ``old`` for ``new`` keeping its position (used to refresh a single card)."""
        for i, item in enumerate(self._items):
            if item.widget() is old:
                self.addChildWidget(new)
                self._items[i] = QWidgetItem(new)
                old.hide()
                old.deleteLater()
                self.invalidate()
                return True
        return False

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, dry):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_h = area.x(), area.y(), 0
        for item in self._items:
            sz = item.sizeHint()
            if x + sz.width() > area.right() + 1 and row_h > 0:
                x = area.x()
                y += row_h + self._v
                row_h = 0
            if not dry:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._h
            row_h = max(row_h, sz.height())
        return y + row_h - rect.y() + m.bottom()
