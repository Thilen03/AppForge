"""Phase 6 tray integration without native tray hosts or network access."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QIcon

from test_gui import qapp  # noqa: F401
from appforge.core.models import AppEntry, UpdateStatus
from appforge.core.tray import TrayShortcuts, FAVORITES_KEY, RECENT_KEY
from appforge.core.updates.installer import InstallCancelled, InstallResult
from appforge.ui.tray import TrayController
from appforge.ui.main_window import MainWindow


def add(service, tmp_path, name="Tool"):
    p = tmp_path / name
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    return service.add_application(str(p))


def available(service, e):
    e.github_repo = "https://github.com/o/r"
    e.latest_version = "2"
    e.update_status = UpdateStatus.UPDATE_AVAILABLE
    e.metadata["update"] = {"tag": "v2", "asset": {"name": "tool", "url": "https://example.org/tool"}}
    service.db.update(e)


@pytest.fixture
def window(qapp, service, monkeypatch):
    import appforge.ui.main_window as mw
    monkeypatch.setattr(mw, "tray_available", lambda: True)
    w = MainWindow(service, tray_icon=QIcon())
    yield w
    w._quitting = True
    w.close()
    w.check_pool.waitForDone()
    w.install_pool.waitForDone()
    w.deleteLater()
    qapp.processEvents()


def test_shortcut_preferences_roundtrip_and_bound(service):
    s = TrayShortcuts(service.db)
    s.set_favorite("one", True)
    s.set_favorite("two", True)
    s.set_favorite("one", True)
    s.set_favorite("two", False)
    for i in range(12):
        s.launched(str(i))
    s.launched("10")
    restored = TrayShortcuts(service.db)
    assert restored.favorites == ["one"]
    assert restored.recent == ["10", "11", "9", "8", "7", "6", "5", "4"]


@pytest.mark.parametrize("raw", ['null', '{}', 'bad json', '[null, {}, 3]', '"text"'])
def test_corrupt_preferences(service, raw):
    service.db.set_setting(FAVORITES_KEY, raw)
    service.db.set_setting(RECENT_KEY, raw)
    s = TrayShortcuts(service.db)
    assert s.favorites == [] and s.recent == []


def test_menu_shortcuts_missing_removed_and_ids(qapp, service, tmp_path):
    one = add(service, tmp_path, "A&B")
    two = AppEntry(name=one.name, path="/missing/tool", format="executable")
    tray = TrayController(QIcon())
    tray.set_applications([one, two], [two.id, "removed"], [one.id, "removed"])
    assert len(tray.favorites_menu.actions()) == 1
    assert not tray.favorites_menu.actions()[0].isEnabled()
    assert tray.recent_menu.actions()[0].text() == "A&&B"
    launches, favorites = [], []
    tray.launchRequested.connect(launches.append)
    tray.favoriteRequested.connect(lambda i, on: favorites.append((i, on)))
    tray.recent_menu.actions()[0].trigger()
    assert launches == [one.id]
    next(a for a in tray.manage_menu.actions() if a.toolTip() == one.path).trigger()
    assert favorites[0][1] is True
    tray.set_applications([], [], [])
    assert not tray.apps_menu.actions()[0].isEnabled()


def test_status_progress_and_busy_shortcuts(window, service, tmp_path):
    e = add(service, tmp_path)
    available(service, e)
    window.reload()
    assert "1 application update" in window.tray.status_action.text()
    assert window.tray.update_action.isEnabled()
    window._set_busy(e.id, "Downloading… 50%", .5)
    assert "50%" in window.tray.activity_action.text()
    assert "50%" in window.tray.tray.toolTip()
    assert not window.tray.update_action.isEnabled()
    assert not window.tray.check_action.isEnabled()
    window._refresh_tray_shortcuts()
    assert not window.tray.apps_menu.actions()[0].isEnabled()
    window._set_busy(e.id, None)
    service.remove_application(e.id)
    window.reload()
    window._refresh_tray_shortcuts()
    assert "0 application updates" in window.tray.status_action.text()
    assert not window.tray.update_action.isEnabled()
    assert window.tray.apps_menu.actions()[0].text() == "None yet"


def test_launch_reuses_environment_and_records_only_success(window, service, tmp_path, monkeypatch):
    import appforge.ui.main_window as mw
    e = add(service, tmp_path)
    e.metadata["env_vars"] = {"CUSTOM": "hello"}
    service.db.update(e)
    seen = []
    monkeypatch.setattr(mw.launcher, "launch", lambda entry: seen.append(entry) or SimpleNamespace(early_exit_code=lambda: None))
    monkeypatch.setattr(mw.QTimer, "singleShot", lambda *args: None)
    window._refresh_tray_shortcuts()
    window.tray.apps_menu.actions()[0].trigger()
    assert seen[0].metadata["env_vars"] == {"CUSTOM": "hello"}
    assert window.shortcuts.recent == [e.id]
    window._favorite_from_tray(e.id, True)
    window._refresh_tray_shortcuts()
    assert window.tray.favorites_menu.actions()[0].text() == e.name
    window._busy[e.id] = ("Waiting…", None)
    window._launch_from_tray(e.id)
    assert len(seen) == 1


def test_navigation_and_update_all_route(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "bring_to_front", lambda: calls.append("open"))
    monkeypatch.setattr(window, "update_all", lambda: calls.append("update"))
    monkeypatch.setattr(window, "open_settings", lambda: calls.append("settings"))
    window.tray.updateAllRequested.emit()
    window.tray.settingsRequested.emit()
    assert calls == ["open", "update", "open", "settings"]
    labels = [action.text() for action in window.tray._menu.actions()]
    assert labels.count("Open AppForge") == 1
    assert "Open application library" not in labels


def test_notifications_once_and_no_false_up_to_date(window, service, tmp_path, monkeypatch):
    e = add(service, tmp_path)
    available(service, e)
    window._live = True
    sent = []
    monkeypatch.setattr(window, "_notify", lambda *args: sent.append(args))
    window._after_checks(False)
    assert len(sent) == 1
    window._tray_check = True
    window._after_checks(False)
    assert len(sent) == 1
    e = service.get(e.id)
    e.update_status = UpdateStatus.FAILED
    e.metadata["update"]["message"] = "Offline"
    service.db.update(e)
    window._tray_check = True
    window._after_checks(False)
    assert "Could not check" in sent[-1][1]
    window._after_checks(False)
    assert len(sent) == 2


def test_notification_preference_includes_close_hint(window, monkeypatch):
    sent = []
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    monkeypatch.setattr(window.tray, "message", lambda *a: sent.append(a))
    window._notify("Title", "Body")
    assert not window.close()
    assert not sent
    assert not window.isVisible()


def test_hidden_batch_summary_once_and_failures_no_modal(window, service, tmp_path, monkeypatch):
    e = add(service, tmp_path)
    available(service, e)
    window.reload()
    sent = []
    monkeypatch.setattr(window, "_notify", lambda *args: sent.append(args))
    window._batch = {"total": 1, "done": 0, "ok": [], "failed": [], "ids": {e.id}}
    window._on_install_done(e.id, RuntimeError("Offline"))
    assert window._batch is None
    assert len(sent) == 1 and "1 failed" in sent[0][1]
    assert service.get(e.id).update_status is UpdateStatus.FAILED
    window._on_install_done(e.id, InstallCancelled())
    assert len(sent) == 1


def test_tray_failure_restores_window(window, monkeypatch):
    monkeypatch.setattr(window.tray, "set_status", lambda *a: (_ for _ in ()).throw(RuntimeError("No host")))
    window._refresh_tray()
    assert window.tray is None
    assert window.isVisible()


def test_initial_tray_failure_is_optional(qapp, service, monkeypatch):
    import appforge.ui.main_window as mw
    monkeypatch.setattr(mw, "tray_available", lambda: (_ for _ in ()).throw(RuntimeError("No host")))
    w = MainWindow(service, tray_icon=QIcon())
    assert w.tray is None
    w.close()


def test_quit_bypasses_close_to_tray(window, qapp, monkeypatch):
    window.settings.run_in_background = True
    window.apply_settings()
    calls = []
    monkeypatch.setattr(type(qapp), "quit", lambda: calls.append("quit"))
    window.tray.quitRequested.emit()
    assert window._quitting and calls == ["quit"]


def test_actual_update_all_confirmation_queues_existing_workflow(window, service, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    e = add(service, tmp_path)
    available(service, e)
    window.reload()
    # Approve the existing confirmation; do not create a second tray installer.
    def approve(box):
        box._test_clicked = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.AcceptRole)
    monkeypatch.setattr(QMessageBox, "exec", approve)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._test_clicked)
    queued = []
    monkeypatch.setattr(window, "start_update", lambda i, from_batch=False: queued.append((i, from_batch)))
    window._update_from_tray()
    assert queued == [(e.id, True)]
    assert window._batch["ids"] == {e.id}
    window.update_all()
    assert len(queued) == 1


def test_successful_hidden_install_notifies_and_refreshes_count(window, service, tmp_path, monkeypatch):
    e = add(service, tmp_path)
    available(service, e)
    window.reload()
    sent = []
    monkeypatch.setattr(window, "_notify", lambda *args: sent.append(args))
    window._on_install_done(e.id, InstallResult(e.path, None, "not available", 20))
    assert len(sent) == 1 and sent[0][0] == "Application updated"
    assert service.get(e.id).installed_version == "2"
    assert "0 application updates" in window.tray.status_action.text()


def test_failed_launch_not_recorded_and_error_visible(window, service, tmp_path, monkeypatch):
    from appforge.services import launcher
    from appforge.core.library import FileState
    e = add(service, tmp_path)
    errors = []
    monkeypatch.setattr(launcher, "launch", lambda entry: (_ for _ in ()).throw(launcher.LaunchError("Missing", FileState.MISSING)))
    monkeypatch.setattr(window, "_launch_failed", lambda *a: errors.append(a))
    window._launch_from_tray(e.id)
    assert errors and not window.shortcuts.recent
