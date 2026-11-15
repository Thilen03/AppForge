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
        rows = []
        row, row_w, row_h = [], 0, 0
        for item in self._items:
            sz = item.sizeHint()
            gap = self._h if row else 0
            if row and row_w + gap + sz.width() > area.width():
                rows.append((row, row_w, row_h))
                row, row_w, row_h, gap = [], 0, 0, 0
            row.append((item, sz))
            row_w += gap + sz.width()
            row_h = max(row_h, sz.height())
        if row:
            rows.append((row, row_w, row_h))
        # Center the whole grid; partial final rows share its first column.
        grid_w = max((width for _, width, _ in rows), default=0)
        left = area.x() + max(0, (area.width() - grid_w) // 2)
        y = area.y()
        for index, (row, _, height) in enumerate(rows):
            x = left
            for item, sz in row:
                if not dry:
                    item.setGeometry(QRect(QPoint(x, y), sz))
                x += sz.width() + self._h
            y += height
            if index < len(rows) - 1:
                y += self._v
        return y - rect.y() + m.bottom()
