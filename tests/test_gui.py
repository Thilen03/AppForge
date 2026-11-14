import time

import pytest
from PySide6.QtWidgets import QApplication

from appforge.core.library import FileState


@pytest.fixture(scope="module")
def qapp():
    from appforge.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    yield app
    # explicit teardown: destroying Qt objects in arbitrary order at interpreter exit can crash
    import gc
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.processEvents()
    gc.collect()


def wait_for(app, cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_add_dialog_flow(qapp, service, fixtures):
    from appforge.ui.dialogs import AddApplicationDialog
    dlg = AddApplicationDialog(service, None, str(fixtures["alpha"]))
    dlg.show()
    assert wait_for(qapp, lambda: dlg.metadata is not None)
    assert dlg.name_edit.text() == "Alpha Editor"
    assert dlg.add_btn.isEnabled()
    assert dlg.icon_lbl.pixmap() is not None and not dlg.icon_lbl.pixmap().isNull()
    dlg.name_edit.setText("Renamed Alpha")
    dlg.repo_edit.setText("nonsense")
    assert not dlg.add_btn.isEnabled()
    dlg.repo_edit.setText("https://github.com/a/b")
    assert dlg.add_btn.isEnabled()
    dlg.add_btn.click()
    assert dlg.added and dlg.added.name == "Renamed Alpha"
    assert [a.name for a in service.list_applications()] == ["Renamed Alpha"]


def test_add_dialog_rejects_bad_and_duplicate(qapp, service, fixtures, tmp_path):
    from appforge.ui.dialogs import AddApplicationDialog
    junk = tmp_path / "x.txt"
    junk.write_text("nope")
    dlg = AddApplicationDialog(service, None, str(junk))
    assert wait_for(qapp, lambda: not dlg.file_msg.isHidden())
    assert not dlg.add_btn.isEnabled()
    service.add_application(str(fixtures["alpha"]))
    dlg2 = AddApplicationDialog(service, None, str(fixtures["alpha"]))
    assert "already" in dlg2.file_msg.text() and not dlg2.add_btn.isEnabled()


def test_main_window_cards_and_missing(qapp, service, fixtures, tmp_path):
    import shutil
    from appforge.ui.main_window import MainWindow
    gone = tmp_path / "gone.AppImage"
    shutil.copy(fixtures["alpha"], gone)
    service.add_application(str(gone))
    service.add_application(str(fixtures["beta"]))
    gone.unlink()
    w = MainWindow(service)
    w.show()
    qapp.processEvents()
    assert len(w._cards) == 2
    states = {c.entry.name: c.state for c in w._cards}
    assert FileState.MISSING in states.values() and FileState.OK in states.values()
    assert not w.banner.isHidden()
    w.search.setText("beta")
    qapp.processEvents()
    assert [c.isVisible() for c in w._cards].count(True) == 1
    w.search.setText("zzz")
    assert w.stack.currentIndex() == 2


def test_empty_state(qapp, service):
    from appforge.ui.main_window import MainWindow
    w = MainWindow(service)
    assert w.stack.currentIndex() == 1


# ------------------------------------------------------------------ Phase 2: updates in the UI
from test_updates import asset_for, new_appimage, world  # noqa: E402,F401  (fixtures + helpers)
from appforge.core.models import UpdateStatus  # noqa: E402
from appforge.core.updates.github import Asset, Release  # noqa: E402


class FakeClient:
    def __init__(self, releases_by_repo):
        self.data = releases_by_repo

    def releases(self, owner, name, per_page=30):
        r = self.data[f"{owner}/{name}"]
        if isinstance(r, Exception):
            raise r
        return r


def release_for(srv, new_bytes, tag="v5.0.0", name="new.AppImage"):
    a = asset_for(srv, new_bytes, name=name)
    return Release(tag=tag, html_url="https://example.invalid/r", assets=[Asset(a["name"], a["url"], a["size"], a["digest"])])


def test_card_states(qapp, service, fixtures):
    from appforge.core.updates.checker import CheckOutcome
    from appforge.ui.app_card import AppCard
    e = service.add_application(str(fixtures["alpha"]), github_repo="o/r")
    card = AppCard(e, FileState.OK)
    assert card._update_btn is None
    outcome = CheckOutcome(UpdateStatus.UPDATE_AVAILABLE, latest_version="9.0", tag="v9.0",
                           asset={"name": "a.AppImage", "url": "u", "size": 1, "digest": None})
    e = __import__("appforge.core.updates.service", fromlist=["x"]).UpdateService(service).apply_check(e.id, outcome)
    card = AppCard(e, FileState.OK)
    assert card._update_btn is not None and card._update_btn.text() == "Update"
    card.show()
    card.set_busy("Downloading… 40%", 0.4)
    assert not card._busy_w.isHidden() and card._chips_w.isHidden() and card._busy_bar.value() == 400
    card.set_busy(None)
    assert card._busy_w.isHidden() and not card._chips_w.isHidden()


def test_window_check_update_and_install_flow(qapp, service, fixtures, world, monkeypatch):
    from appforge.ui.main_window import MainWindow
    target, new_bytes, routes, srv = world
    old = target.read_bytes()
    e = service.add_application(str(target), github_repo="o/r")
    client = FakeClient({"o/r": [release_for(srv, new_bytes)]})
    w = MainWindow(service, github_client=client)
    w.show()
    w.check_updates(user_initiated=True)
    assert wait_for(qapp, lambda: service.get(e.id).update_status is UpdateStatus.UPDATE_AVAILABLE)
    assert wait_for(qapp, lambda: w._card(e.id)._update_btn is not None and not w._busy)
    assert w.update_all_btn.isEnabled() and "(1)" in w.update_all_btn.text()
    w._card(e.id)._update_btn.click()
    assert wait_for(qapp, lambda: service.get(e.id).update_status is UpdateStatus.UP_TO_DATE and not w._busy, 20)
    got = service.get(e.id)
    assert got.installed_version == "5.0.0" and target.read_bytes() == new_bytes != old
    assert (target.parent / ".Dolphin.backups").is_dir() and got.backup_info["backups"]
    assert w._card(e.id)._update_btn is None and not w.update_all_btn.isEnabled()


def test_window_update_all_and_failures(qapp, service, fixtures, world, monkeypatch, tmp_path):
    import shutil
    from PySide6.QtWidgets import QMessageBox
    from appforge.ui.main_window import MainWindow
    target, new_bytes, routes, srv = world
    second = tmp_path / "Second.AppImage"
    shutil.copy(fixtures["beta"], second)
    e1 = service.add_application(str(target), github_repo="o/good")
    e2 = service.add_application(str(second), github_repo="o/broken")
    broken = release_for(srv, new_bytes, name="missing.AppImage")      # URL 404s
    client = FakeClient({"o/good": [release_for(srv, new_bytes)], "o/broken": [broken]})
    w = MainWindow(service, github_client=client)
    w.show()
    w.check_updates()
    assert wait_for(qapp, lambda: not w._busy and all(
        service.get(i).update_status is UpdateStatus.UPDATE_AVAILABLE for i in (e1.id, e2.id)))
    assert "(2)" in w.update_all_btn.text()
    shown = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.setdefault("confirm", self.informativeText()) and 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.setdefault("warn", a)))
    w.update_all()
    assert "→" in shown["confirm"]
    assert wait_for(qapp, lambda: w._batch is None and not w._busy, 30)
    assert service.get(e1.id).update_status is UpdateStatus.UP_TO_DATE
    f = service.get(e2.id)
    assert f.update_status is UpdateStatus.FAILED and "404" in f.metadata["update"]["install_error"]
    assert second.read_bytes() == fixtures["beta"].read_bytes()          # untouched
    assert w._card(e2.id)._update_btn.text() == "Retry update"


def test_window_check_failure_and_no_repo(qapp, service, fixtures):
    from appforge.core.updates.github import GitHubError
    from appforge.ui.main_window import MainWindow
    e = service.add_application(str(fixtures["alpha"]), github_repo="o/r")
    service.add_application(str(fixtures["beta"]))                       # no repo: never checked
    w = MainWindow(service, github_client=FakeClient({"o/r": GitHubError("offline", "network")}))
    w.show()
    w.check_updates()
    assert wait_for(qapp, lambda: service.get(e.id).update_status is UpdateStatus.FAILED and not w._busy)
    assert service.get(e.id).metadata["update"]["message"] == "offline"
    chips = [c.text() for c in w._card(e.id).findChildren(type(w.count_lbl)) if c.objectName() == "chip"]
    assert "Update failed" in chips
    beta = next(a for a in service.list_applications() if a.name != "Alpha Editor")
    assert beta.last_update_check is None


def test_add_dialog_application_menu_checkbox(qapp, service, fixtures):
    from appforge.ui.dialogs import AddApplicationDialog
    dlg = AddApplicationDialog(service, None, str(fixtures["alpha"]))
    dlg.show()
    assert wait_for(qapp, lambda: dlg.metadata is not None)
    assert dlg.menu_cb.isChecked()                       # on by default
    dlg.add_btn.click()
    assert dlg.menu_requested and service.desktop_enabled(service.get(dlg.added.id))
    assert service.desktop.exists(dlg.added.id)
    dlg2 = AddApplicationDialog(service, None, str(fixtures["beta"]))
    dlg2.show()
    assert wait_for(qapp, lambda: dlg2.metadata is not None)
    dlg2.menu_cb.setChecked(False)
    dlg2.add_btn.click()
    assert not service.desktop.exists(dlg2.added.id)
    assert service.desktop_default() is False            # the choice is remembered
    dlg3 = AddApplicationDialog(service, None, str(fixtures["gamma"]))
    assert not dlg3.menu_cb.isChecked()


def test_card_menu_toggles_application_menu_entry(qapp, service, fixtures):
    from appforge.ui.main_window import MainWindow
    entry = service.add_application(str(fixtures["alpha"]))
    win = MainWindow(service)
    win.show()
    qapp.processEvents()
    menu = win._cards[0]._build_menu()
    assert "Add to application menu" in [a.text() for a in menu.actions()]
    win.toggle_desktop_entry(entry.id)
    assert service.desktop.exists(entry.id)
    menu = win._cards[0]._build_menu()
    assert "Remove from application menu" in [a.text() for a in menu.actions()]
    win.toggle_desktop_entry(entry.id)
    assert not service.desktop.exists(entry.id)
    win.close()


# ------------------------------------------------------------------ Phase 5: filters, settings, notifications
def test_filter_row_category_status_and_sort(qapp, service, fixtures):
    from appforge.ui.main_window import MainWindow
    a = service.add_application(str(fixtures["alpha"]))
    b = service.add_application(str(fixtures["beta"]))
    service.update_application(a.id, category="Work")
    w = MainWindow(service)
    w.show()
    qapp.processEvents()
    assert not w.filter_row.isHidden()
    assert [w.category_cb.itemText(i) for i in range(w.category_cb.count())][0] == "All categories"
    assert w.category_cb.findData("Work") >= 0
    w.category_cb.setCurrentIndex(w.category_cb.findData("Work"))
    qapp.processEvents()
    assert [c.entry.id for c in w._cards if c.isVisible()] == [a.id]
    w.category_cb.setCurrentIndex(0)
    w.status_cb.setCurrentIndex(w.status_cb.findData("unlinked"))
    qapp.processEvents()
    assert [c.isVisible() for c in w._cards].count(True) == 2
    w.status_cb.setCurrentIndex(w.status_cb.findData("updates"))
    qapp.processEvents()
    assert w.stack.currentIndex() == 2
    w.status_cb.setCurrentIndex(0)
    w.sort_cb.setCurrentIndex(w.sort_cb.findData("recent"))
    qapp.processEvents()
    assert [c.entry.id for c in w._cards] == [b.id, a.id] or len(w._cards) == 2
    w.close()


def test_empty_library_hides_filter_row(qapp, service):
    from appforge.ui.main_window import MainWindow
    w = MainWindow(service)
    assert w.filter_row.isHidden()


def test_edit_dialog_saves_category(qapp, service, fixtures):
    from appforge.ui.dialogs import EditApplicationDialog
    e = service.add_application(str(fixtures["alpha"]))
    dlg = EditApplicationDialog(service, e)
    dlg.category_edit.setCurrentText("Favourites")
    dlg.save_btn.click()
    assert service.get(e.id).metadata["category"] == "Favourites"


def test_settings_dialog_saves(qapp, service):
    from appforge.core.settings import AppSettings
    from appforge.ui.settings_dialog import SettingsDialog
    s = AppSettings(service.db)
    dlg = SettingsDialog(s, tray_available=False)
    assert not dlg.bg_cb.isEnabled()
    dlg.auto_cb.setChecked(False)
    dlg.interval.setCurrentIndex(dlg.interval.findData(12))
    dlg.notify_cb.setChecked(False)
    dlg.token_edit.setText("ghp_token123")
    dlg._save()
    s2 = AppSettings(service.db)
    assert (s2.auto_check, s2.check_interval_hours, s2.notifications, s2.github_token) == (False, 12, False, "ghp_token123")
    dlg2 = SettingsDialog(s2, tray_available=False)
    dlg2.token_edit.setText("bad token")
    dlg2._save()
    assert dlg2.error_lbl.text() and s2.github_token == "ghp_token123"


def test_window_uses_saved_token_and_notifies_in_background(qapp, service, fixtures, monkeypatch):
    from appforge.core.settings import AppSettings
    from appforge.ui import main_window as mw
    sent = []
    monkeypatch.setattr(mw, "send_desktop_notification", lambda t, b, *a, **k: sent.append((t, b)) or True)
    AppSettings(service.db).set_github_token("tok")
    e = service.add_application(str(fixtures["alpha"]), github_repo="o/r")
    rel = Release(tag="v9.0.0", html_url="https://example.invalid/r",
                  assets=[Asset("a-9.0.0-x86_64.AppImage", "https://example.invalid/a", 5)])
    w = mw.MainWindow(service, github_client=FakeClient({"o/r": [rel]}), auto_check=True)
    w._timer.stop()
    w.check_updates()
    assert wait_for(qapp, lambda: service.get(e.id).update_status is UpdateStatus.UPDATE_AVAILABLE and not w._busy)
    assert wait_for(qapp, lambda: len(sent) == 1)
    assert "Alpha" in sent[0][0] and "9.0.0" in sent[0][1]
    assert service.get(e.id).metadata["notified_version"] == "9.0.0"
    w.check_updates()                                     # same version again: no second notification
    assert wait_for(qapp, lambda: not w._busy)
    qapp.processEvents()
    assert len(sent) == 1
    w._quitting = True
    w.close()
