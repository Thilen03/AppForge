"""Pixmap helpers: stored icons, generated placeholders and the app logo."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
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


def _gear_path(size: float) -> QPainterPath:
    """An eight-toothed cog with a round hole, centred in a ``size`` x ``size`` square."""
    c = size / 2
    outer, root, hole, teeth = size * 0.47, size * 0.35, size * 0.15, 8
    pitch = 360 / teeth

    def pt(radius: float, deg: float) -> QPointF:
        a = math.radians(deg - 90)
        return QPointF(c + radius * math.cos(a), c + radius * math.sin(a))

    path = QPainterPath()
    for i in range(teeth):
        a = i * pitch
        pts = [pt(root, a - 12), pt(outer, a - 7.5), pt(outer, a + 7.5), pt(root, a + 12),
               pt(root, a + pitch / 2)]            # last point keeps the gap between teeth round-ish
        for j, p in enumerate(pts):
            if i == 0 and j == 0:
                path.moveTo(p)
            else:
                path.lineTo(p)
    path.closeSubpath()
    path.addEllipse(QPointF(c, c), hole, hole)
    path.setFillRule(Qt.OddEvenFill)               # the ellipse punches the hole
    return path


def gear_pixmap(color: str, size: int, dpr: float = 1.0) -> QPixmap:
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillPath(_gear_path(px), QColor(color))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def gear_icon(color: str, size: int = 20) -> QIcon:
    """Settings cog in ``color``; rendered at 1x/2x/3x so it stays sharp on HiDPI screens."""
    icon = QIcon()
    for dpr in (1.0, 2.0, 3.0):
        icon.addPixmap(gear_pixmap(color, size, dpr))
    return icon


def theme_icon(dark: bool, color: str, size: int = 24) -> QIcon:
    """Sun in dark mode, crescent moon in light mode: the next appearance."""
    icon = QIcon()
    for dpr in (1.0, 2.0, 3.0):
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size * dpr / 24, size * dpr / 24)
        painter.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        if dark:
            painter.drawEllipse(QPointF(12, 12), 4, 4)
            for i in range(8):
                angle = i * math.pi / 4
                painter.drawLine(QPointF(12 + 7 * math.cos(angle), 12 + 7 * math.sin(angle)),
                                 QPointF(12 + 9.5 * math.cos(angle), 12 + 9.5 * math.sin(angle)))
        else:
            moon = QPainterPath()
            moon.addEllipse(QRectF(3, 3, 18, 18))
            cutout = QPainterPath()
            cutout.addEllipse(QRectF(9, -1, 18, 18))
            painter.drawPath(moon.subtracted(cutout))
        painter.end()
        pm.setDevicePixelRatio(dpr)
        icon.addPixmap(pm)
    return icon
