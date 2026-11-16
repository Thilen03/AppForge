"""Shared library/tray favorites, ordering and card indicators."""
import pytest

from test_gui import qapp  # noqa: F401
from test_tray import window, add  # noqa: F401
from tuxshelf.core.organize import SORT_NAME, SORT_RECENT, SORT_STATUS
from tuxshelf.core.models import UpdateStatus
from tuxshelf.core.tray import TrayShortcuts
from tuxshelf.ui.main_window import MainWindow
from tuxshelf.ui.popups import RoundedMenu


def favorite_action(card):
    menu = card.findChild(RoundedMenu)
    return next(a for a in menu.actions() if "favorites" in a.text())


@pytest.mark.parametrize('sort', [SORT_NAME, SORT_RECENT, SORT_STATUS])
def test_favorites_first_preserve_selected_sort(window, service, tmp_path, sort):
    from tuxshelf.core.organize import sort_entries
    entries = [add(service, tmp_path, name) for name in ['Alpha', 'Beta', 'Gamma', 'Delta']]
    for i, e in enumerate(entries):
        e.added_at = 100 + i
        e.update_status = UpdateStatus.UP_TO_DATE if i % 2 else UpdateStatus.FAILED
        service.db.update(e)
    window.shortcuts.set_favorite(entries[1].id, True)
    window.shortcuts.set_favorite(entries[3].id, True)
    window.sort_cb.setCurrentIndex(window.sort_cb.findData(sort))
    window.reload()
    ordered = sort_entries(service.list_applications(), sort)
    favorites = set(window.shortcuts.favorites)
    expected = [e.id for e in ordered if e.id in favorites] + [e.id for e in ordered if e.id not in favorites]
    assert [c.entry.id for c in window._cards] == expected


def test_card_toggle_star_order_tray_and_persistence(window, service, tmp_path):
    a, z = [add(service, tmp_path, name) for name in ['Alpha', 'Zulu']]
    window.reload()
    assert favorite_action(window._card(z.id)).text() == 'Add to favorites'
    assert window._card(z.id).favorite_star.isHidden()
    favorite_action(window._card(z.id)).trigger()
    assert [c.entry.id for c in window._cards] == [z.id, a.id]
    assert not window._card(z.id).favorite_star.isHidden()
    assert favorite_action(window._card(z.id)).text() == 'Remove from favorites'
    assert TrayShortcuts(service.db).favorites == [z.id]
    window._refresh_tray_shortcuts()
    assert [a.text() for a in window.tray.favorites_menu.actions()] == ['Zulu']
    assert next(a for a in window.tray.manage_menu.actions() if a.text() == 'Zulu').isChecked()
    favorite_action(window._card(z.id)).trigger()
    assert [c.entry.id for c in window._cards] == [a.id, z.id]
    assert window._card(z.id).favorite_star.isHidden()
    window._refresh_tray_shortcuts()
    assert window.tray.favorites_menu.actions()[0].text() == 'None yet'


def test_tray_toggle_refreshes_library_and_retains_filter_and_busy(window, service, tmp_path):
    e = add(service, tmp_path)
    window.reload()
    window.search.setText('Tool')
    window._set_busy(e.id, 'Downloading… 50%', .5)
    window._refresh_tray_shortcuts()
    window.tray.manage_menu.actions()[0].trigger()
    card = window._card(e.id)
    assert card.favorite and not card.favorite_star.isHidden()
    assert window.search.text() == 'Tool'
    assert card._busy_lbl.text() == 'Downloading… 50%'
    assert card._busy_bar.value() == 500
    window._refresh_card(e.id)
    assert window._card(e.id).favorite


def test_favorites_without_tray_and_after_window_recreation(qapp, service, tmp_path):
    e = add(service, tmp_path)
    w = MainWindow(service)
    assert w.tray is None
    favorite_action(w._card(e.id)).trigger()
    w.close()
    restored = MainWindow(service)
    assert restored._card(e.id).favorite
    assert not restored._card(e.id).favorite_star.isHidden()
    restored.close()


def test_hover_star_click_synchronizes_favorites(window, service, tmp_path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    e = add(service, tmp_path)
    window.reload()
    window.show()
    qapp.processEvents()
    card = window._card(e.id)
    card._reveal(False)
    assert card.favorite_star.isHidden()
    card._reveal(True)
    star = card.favorite_star
    assert star.isVisible() and not star.favorite
    assert star.accessibleName() == 'Add to favorites'
    before = star.geometry()
    QTest.mouseClick(star, Qt.LeftButton)
    card = window._card(e.id)
    assert card.favorite and card.favorite_star.favorite
    assert card.favorite_star.geometry() == before
    card._reveal(False)
    assert not card.favorite_star.isHidden()
    assert card.favorite_star.accessibleName() == 'Remove from favorites'
    window._refresh_tray_shortcuts()
    assert window.tray.favorites_menu.actions()[0].text() == e.name
    QTest.mouseClick(card.favorite_star, Qt.LeftButton)
    assert not window._card(e.id).favorite
    assert not window.shortcuts.favorites


def test_hover_star_reserves_space_and_hides_on_leave(qapp):
    from tuxshelf.ui.app_card import AppCard
    from tuxshelf.core.models import AppEntry
    from tuxshelf.core.library import FileState
    card = AppCard(AppEntry(name='Long application name that needs eliding', path='/bin/sh'), FileState.OK)
    card.show()
    qapp.processEvents()
    card._reveal(False)
    before = card.layout().itemAt(0).layout().itemAt(1).layout().geometry()
    card._reveal(True)
    qapp.processEvents()
    assert not card.favorite_star.isHidden()
    assert card.layout().itemAt(0).layout().itemAt(1).layout().geometry() == before
    card._reveal(False)
    assert card.favorite_star.isHidden()
    card.close()


def test_star_keyboard_and_double_click_do_not_launch(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from tuxshelf.ui.app_card import AppCard
    from tuxshelf.core.models import AppEntry
    from tuxshelf.core.library import FileState
    e = AppEntry(name='Tool', path='/bin/sh')
    card = AppCard(e, FileState.OK)
    changed, launched = [], []
    card.favoriteRequested.connect(lambda *args: changed.append(args))
    card.launchRequested.connect(launched.append)
    card.show()
    card._reveal(True)
    card.favorite_star.setFocus()
    qapp.processEvents()
    QTest.keyClick(card.favorite_star, Qt.Key_Space)
    assert changed == [(e.id, True)]
    QTest.mouseDClick(card.favorite_star, Qt.LeftButton)
    assert not launched
    card.close()
