"""v0.5.3 GUI checks: rounded popups, bring-to-front, self-update popup."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from test_gui import qapp, wait_for  # noqa: F401  (shared fixture)


def test_combo_popup_is_opaque_and_masked_and_menu_is_translucent(qapp):
    from appforge.ui.popups import RoundedComboBox, RoundedMenu
    combo = RoundedComboBox()
    combo.addItems(["a", "b", "c"])
    combo.show()
    combo.showPopup()
    popup = combo.view().window()
    qapp.processEvents()
    # 0.5.4: a translucent combo popup produced a black box on some systems - keep it opaque, clip it
    assert not popup.testAttribute(Qt.WA_TranslucentBackground)
    assert not popup.mask().isEmpty()
    combo.hidePopup()
    menu = RoundedMenu()
    assert menu.testAttribute(Qt.WA_TranslucentBackground)
    assert menu.windowFlags() & Qt.FramelessWindowHint


def test_bring_to_front_restores_minimized_and_hidden(qapp, service):
    from appforge.ui.main_window import MainWindow
    win = MainWindow(service)
    win.show()
    win.showMinimized()
    qapp.processEvents()
    win.bring_to_front()
    qapp.processEvents()
    assert win.isVisible() and not win.isMinimized()
    win.hide()
    win.bring_to_front()
    assert win.isVisible()
    win._quitting = True
    win.close()


def test_self_update_later_does_nothing_and_can_be_offered_again(qapp, service, monkeypatch):
    from appforge.core.selfupdate import SelfUpdate
    from appforge.ui.main_window import MainWindow
    win = MainWindow(service)
    found = SelfUpdate("99.0.0", "https://github.com/Thilen03/AppForge/releases/tag/v99.0.0")
    seen = []

    def fake_exec(box):
        seen.append(box.text())
        box.done(0)                      # nothing clicked == "Later"

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    win._offer_self_update(found)
    win._offer_self_update(found)        # next start: asked again
    assert len(seen) == 2 and "99.0.0" in seen[0]
    assert win._self_install is None
    win._quitting = True
    win.close()


def test_settings_is_a_blue_gear_next_to_add_application(qapp, service):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QPushButton, QToolButton
    from appforge.ui import theme
    from appforge.ui.main_window import MainWindow
    win = MainWindow(service)
    win.show()
    qapp.processEvents()
    btn = win.settings_btn
    assert isinstance(btn, QToolButton) and btn.text() == "" and not btn.icon().isNull()
    assert btn.toolTip() == "Settings"
    # Shares the header row, immediately to the right of Add Application.
    assert btn.parent() is win.add_btn.parent()
    assert btn.geometry().left() > win.add_btn.geometry().right()
    assert btn.geometry().center().y() == win.add_btn.geometry().center().y()
    assert btn.height() == btn.width() == win.add_btn.height()
    assert not any(w.text() == "Settings" for w in win.findChildren(QPushButton))
    # Icon matches primary-button text against the blue button background.
    img = btn.icon().pixmap(20, 20).toImage()
    foreground = QColor(theme.tokens().accent_text)
    colours = {img.pixelColor(x, y).rgb() for x in range(20) for y in range(20)
               if img.pixelColor(x, y).alpha() == 255}
    assert foreground.rgb() in colours
    win._quitting = True
    win.close()
