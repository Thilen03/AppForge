"""Pixmap helpers: stored icons, generated placeholders and the app logo."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

_HUES = (212, 172, 262, 28, 330, 142, 48, 196)


def _render_svg(path: str, px: int) -> QPixmap:
    renderer = QSvgRenderer(path)
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    if renderer.isValid():
        p = QPainter(img)
        size = renderer.defaultSize()
        side = max(size.width(), size.height(), 1)
        w, h = px * size.width() / side, px * size.height() / side
        renderer.render(p, QRectF((px - w) / 2, (px - h) / 2, w, h))
        p.end()
    return QPixmap.fromImage(img)


def placeholder_pixmap(name: str, size: int, dpr: float = 1.0) -> QPixmap:
    """Rounded colour tile with the app's initial; colour is stable per name."""
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    hue = _HUES[int(hashlib.md5(name.lower().encode()).hexdigest(), 16) % len(_HUES)]
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), px * 0.22, px * 0.22)
    p.fillPath(path, QColor.fromHsl(hue, 120, 110))
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(int(px * 0.46))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    initial = next((c for c in name if c.isalnum()), "?").upper()
    p.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, initial)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def app_pixmap(icon_path: str | None, name: str, size: int, dpr: float = 1.0) -> QPixmap:
    """Load the stored icon scaled to ``size`` logical px, or a placeholder."""
    px = int(size * dpr)
    if icon_path and Path(icon_path).is_file():
        if icon_path.lower().endswith(".svg"):
            pm = _render_svg(icon_path, px)
        else:
            pm = QPixmap(icon_path)
            if not pm.isNull():
                pm = pm.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not pm.isNull():
            pm.setDevicePixelRatio(dpr)
            return pm
    return placeholder_pixmap(name, size, dpr)
