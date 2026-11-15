"""Library columns, balanced gutters and scrolling without a visible scrollbar."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from appforge.core.models import AppEntry
from appforge.ui.main_window import MainWindow, CARD_GAP
from appforge.ui.app_card import CARD_W
from test_gui import qapp  # noqa: F401


@pytest.fixture
def window_factory(qapp, service, tmp_path, monkeypatch):
    import appforge.ui.main_window as module
    settings = QSettings(str(tmp_path / 'window.ini'), QSettings.IniFormat)
    monkeypatch.setattr(module, 'QSettings', lambda: settings)
    windows = []

    def create(screen_width=1920, count=17):
        monkeypatch.setattr(MainWindow, 'screen', lambda self: SimpleNamespace(
            availableGeometry=lambda: QRect(0, 0, screen_width, 1080)))
        for index in range(count):
            service.db.add(AppEntry(name=f'App {index:02}', path=f'/opt/example-{index}.sh', format='executable'))
        window = MainWindow(service)
        windows.append(window)
        window.show()
        qapp.processEvents()
        return window

    yield create, settings
    for window in windows:
        window.close()
        window.deleteLater()
    qapp.processEvents()


def test_open_four_columns_centered_and_wheel_scrolls(window_factory, qapp):
    create, _ = window_factory
    window = create()
    cards = window._cards
    assert len({c.y() for c in cards[:4]}) == 1
    assert cards[4].y() > cards[0].y()
    assert cards[-1].x() == cards[0].x()
    right = window.scroll.viewport().width() - (cards[3].x() + CARD_W)
    assert abs(cards[0].x() - right) <= 1
    bar = window.scroll.verticalScrollBar()
    assert window.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert not bar.isVisible() and bar.maximum() > 0
    assert not window.scroll.horizontalScrollBar().isVisible()
    viewport = window.scroll.viewport()
    local = viewport.rect().center()
    event = QWheelEvent(QPointF(local), QPointF(viewport.mapToGlobal(local)),
                        QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                        Qt.ScrollUpdate, False)
    QApplication.sendEvent(viewport, event)
    qapp.processEvents()
    assert bar.value() > 0
    assert cards[0].mapTo(viewport, QPoint()).y() < 0
    # Extra width is split evenly without centering the partial last row.
    window.resize(1600, window.height())
    window._fit_library_width()
    assert window.width() == 1600  # retain larger saved/user geometry
    qapp.processEvents()
    right = viewport.width() - (cards[3].x() + CARD_W)
    assert abs(cards[0].x() - right) <= 1
    assert cards[-1].x() == cards[0].x()


@pytest.mark.parametrize('saved_width,screen_width,expected', [
    (1040, 1920, 4 * CARD_W + 3 * CARD_GAP + 64),
    (1040, 1280, 1280),
])
def test_startup_width_respects_saved_height_and_screen(window_factory, qapp, saved_width, screen_width, expected):
    create, settings = window_factory
    # Use a plain QWidget to encode Qt geometry without initializing app workers.
    from PySide6.QtWidgets import QWidget
    previous = QWidget()
    previous.resize(saved_width, 640)
    settings.setValue('geometry', previous.saveGeometry())
    previous.close()
    window = create(screen_width=screen_width, count=5)
    assert abs(window.width() - expected) <= 4  # platform window-frame width
    assert window.height() == 640
    if screen_width < 4 * CARD_W:
        assert window._cards[3].y() > window._cards[0].y()
