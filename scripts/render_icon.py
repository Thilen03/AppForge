"""Render resources/tuxshelf.svg to PNG (run once when the logo changes)."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

res = os.path.join(os.path.dirname(__file__), "..", "src", "tuxshelf", "resources")
app = QGuiApplication(sys.argv)
r = QSvgRenderer(os.path.join(res, "tuxshelf.svg"))
for px in (256, 512):
    img = QImage(px, px, QImage.Format_ARGB32); img.fill(Qt.transparent)
    p = QPainter(img); r.render(p); p.end()
    img.save(os.path.join(res, "tuxshelf.png" if px == 256 else "tuxshelf-512.png"))
