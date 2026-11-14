"""Plasma compositor minimize callbacks, script behavior and async lifecycle."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtQml import QJSEngine

from test_gui import qapp  # noqa: F401
from test_tray import window  # noqa: F401
from appforge.ui.kwin_tray import KWinTrayBridge, plasma_wayland, render_observer


class FakeBus(QObject):
    ownerChanged = Signal(bool)
    destination = ':1.123'

    def __init__(self):
        super().__init__()
        self.calls, self.receivers = [], {}
        self.allow_register = True

    def register(self, path, receiver):
        if self.allow_register:
            self.receivers[path] = receiver
        return self.allow_register

    def unregister(self, path):
        self.receivers.pop(path, None)

    def request(self, path, interface, method, args, callback):
        self.calls.append(SimpleNamespace(path=path, interface=interface, method=method,
                                          args=args, callback=callback))


def bridge_with_bus():
    bus = FakeBus()
    return KWinTrayBridge(transport=bus), bus


def test_load_run_disable_cleanup(qapp):
    bridge, bus = bridge_with_bus()
    bridge.set_enabled(True)
    call = bus.calls[-1]
    script, name = call.args
    assert call.method == 'loadScript' and call.path == '/Scripting'
    assert Path(script).is_file() and name.startswith('appforge-tray-')
    assert ':1.123' in Path(script).read_text()
    call.callback([7], None)
    assert bus.calls[-1].path == '/Scripting/Script7'
    assert bus.calls[-1].method == 'run'
    bus.calls[-1].callback([], None)
    bridge.set_enabled(True)
    assert len(bus.calls) == 2
    bridge.set_enabled(False)
    assert bus.calls[-1].method == 'unloadScript' and bus.calls[-1].args == [name]
    assert not Path(script).exists() and not bus.receivers
    bridge.set_enabled(False)
    assert len(bus.calls) == 3


def test_callback_accepts_only_active_token_and_minimize(qapp):
    bridge, bus = bridge_with_bus()
    requests = []
    bridge.minimized.connect(lambda: requests.append(True))
    bridge.set_enabled(True)
    token = bridge._session.token
    bridge.stateChanged('incorrect', True)
    bridge.stateChanged(token, False)
    assert not requests
    bridge.stateChanged(token, True)
    assert requests == [True]
    bridge.set_enabled(False)
    bridge.stateChanged(token, True)
    assert requests == [True]


@pytest.mark.parametrize('response,error', [([-1],None),([],None),(['bad'],None),([], 'Access denied')])
def test_load_errors_clean_and_report(qapp, response, error):
    bridge, bus = bridge_with_bus()
    errors = []
    bridge.failed.connect(errors.append)
    bridge.set_enabled(True)
    script = bus.calls[-1].args[0]
    bus.calls[-1].callback(response, error)
    assert errors and bridge._session is None
    assert not Path(script).exists() and not bus.receivers
    assert bus.calls[-1].method == 'unloadScript'


def test_run_error_cleans(qapp):
    bridge, bus = bridge_with_bus()
    errors = []
    bridge.failed.connect(errors.append)
    bridge.set_enabled(True)
    bus.calls[-1].callback([3],None)
    bus.calls[-1].callback([], 'Script failed')
    assert errors == ['Script failed'] and bridge._session is None


def test_disabled_while_loading_never_runs_stale_script(qapp):
    bridge, bus = bridge_with_bus()
    bridge.set_enabled(True)
    old_load = bus.calls[-1]
    old_path = bridge._session.path
    bridge.set_enabled(False)
    bridge.set_enabled(True)
    new_path = bridge._session.path
    old_load.callback([4],None)
    assert not any(c.method == 'run' for c in bus.calls)
    assert new_path in bus.receivers and old_path not in bus.receivers
    bridge.set_enabled(False)


def test_kwin_restart_reconnects_only_while_enabled(qapp):
    bridge, bus = bridge_with_bus()
    bridge.set_enabled(True)
    old_token = bridge._session.token
    bus.ownerChanged.emit(False)
    assert bridge._session is None
    bus.ownerChanged.emit(True)
    assert bridge._session.token != old_token
    bridge.set_enabled(False)
    bus.ownerChanged.emit(True)
    assert bridge._session is None


@pytest.mark.parametrize('failure', ['no_bus', 'registration'])
def test_unavailable_bus_is_optional(qapp, failure):
    bridge, bus = bridge_with_bus()
    if failure == 'no_bus':
        bus.destination = ''
    else:
        bus.allow_register = False
    errors = []
    bridge.failed.connect(errors.append)
    bridge.set_enabled(True)
    assert errors and not bus.receivers and bridge._session is None


@pytest.mark.parametrize('platform,desktop,expected', [
    ('wayland', 'KDE', True), ('wayland-egl', 'plasma', True),
    ('xcb','KDE',False), ('wayland','GNOME',False), ('offscreen','KDE',False),
])
def test_detection(monkeypatch, platform, desktop, expected):
    for key in ['XDG_SESSION_DESKTOP','DESKTOP_SESSION']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('XDG_CURRENT_DESKTOP',desktop)
    assert plasma_wayland(platform) is expected


def test_generated_script_reads_only_own_normal_windows(qapp):
    engine = QJSEngine()
    setup = engine.evaluate('''
    var calls = [];
    function signal() { return {slots: [], connect: function(fn) {this.slots.push(fn);},
                                emit: function() {this.slots.forEach(function(fn){fn();});}}; }
    function win(pid, normal, dialog) {
        return {pid:pid, normalWindow:normal, dialog:dialog, minimized:false,
                minimizedChanged:signal()};
    }
    var own = win(123,true,false), other = win(456,true,false), dialog = win(123,false,true);
    var workspace = {windowAdded:signal(), windowList:function(){return [own,other,dialog];}};
    function callDBus() { calls.push(Array.prototype.slice.call(arguments)); }
    ''')
    assert not setup.isError()
    result = engine.evaluate(render_observer(123, ':1.123', '/test', 'token'))
    assert not result.isError(), result.toString()
    engine.evaluate('own.minimized=true; own.minimizedChanged.emit(); other.minimizedChanged.emit(); dialog.minimizedChanged.emit();')
    calls = engine.evaluate('calls').toVariant()
    assert len(calls) == 2
    assert calls[-1] == [':1.123','/test','org.appforge.TrayObserver','stateChanged','token',True]
    engine.evaluate('var added=win(123,true,false); workspace.windowAdded.emit = function(){this.slots.forEach(function(fn){fn(added);});}; workspace.windowAdded.emit(); added.minimized=true; added.minimizedChanged.emit();')
    assert engine.evaluate('calls.length').toInt() == 4
    assert engine.evaluate('own.minimized').toBool()  # script never changes window state


def test_compositor_callback_hides_without_any_qt_minimized_state(window, qapp, monkeypatch):
    import appforge.ui.main_window as mw
    bus = FakeBus()
    monkeypatch.setattr(mw, 'plasma_wayland', lambda platform: True)
    monkeypatch.setattr(mw, 'KWinTrayBridge', lambda parent: KWinTrayBridge(parent, transport=bus))
    window.settings.notifications = False
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    qapp.processEvents()
    bridge = window._kwin_bridge
    assert window.isVisible() and not window.isMinimized()
    bridge.stateChanged(bridge._session.token, True)
    assert not window.isVisible() and not window.windowHandle().isVisible()
    window.bring_to_front()
    assert window.isVisible()
    window.settings.run_in_background = False
    window.apply_settings()
    assert bridge._session is None and not bus.receivers


def test_foreign_or_unminimize_callback_never_hides_window(window, qapp, monkeypatch):
    import appforge.ui.main_window as mw
    bus = FakeBus()
    monkeypatch.setattr(mw, 'plasma_wayland', lambda platform: True)
    monkeypatch.setattr(mw, 'KWinTrayBridge', lambda parent: KWinTrayBridge(parent, transport=bus))
    window.settings.run_in_background = True
    window.apply_settings()
    window.show()
    bridge = window._kwin_bridge
    bridge.stateChanged('foreign', True)
    bridge.stateChanged(bridge._session.token, False)
    assert window.isVisible()
    window._quitting = True
    window.close()
    assert bridge._session is None


def test_filesystem_failure_is_reported(qapp, monkeypatch):
    import appforge.ui.kwin_tray as module
    bridge, bus = bridge_with_bus()
    errors = []
    bridge.failed.connect(errors.append)
    monkeypatch.setattr(module.tempfile, 'TemporaryDirectory', lambda **kw: (_ for _ in ()).throw(PermissionError('No temporary directory')))
    bridge.set_enabled(True)
    assert errors == ['No temporary directory'] and bridge._session is None


@pytest.mark.parametrize('error', [None, 'Access denied'])
def test_real_qtdbus_pending_reply_handling(qapp, error):
    from PySide6.QtDBus import QDBusMessage, QDBusPendingCall
    from appforge.ui.kwin_tray import SessionBus
    from test_gui import wait_for
    transport = SessionBus.__new__(SessionBus)
    QObject.__init__(transport)
    request = QDBusMessage.createMethodCall('org.kde.KWin','/Scripting','org.kde.kwin.Scripting','loadScript')
    reply = request.createErrorReply('org.test.Error',error) if error else request.createReply(7)
    sent, results = [], []
    def async_call(message, timeout):
        sent.append((message, timeout))
        return QDBusPendingCall.fromCompletedCall(reply)
    transport.bus = SimpleNamespace(asyncCall=async_call)
    transport.request('/Scripting','org.kde.kwin.Scripting','loadScript',['/tmp/test.js','test'],
                      lambda values, failure: results.append((values,failure)))
    assert wait_for(qapp, lambda: bool(results))
    assert sent[0][0].arguments() == ['/tmp/test.js','test']
    assert not sent[0][0].autoStartService()
    expected = [([], error)] if error else [([7], None)]
    assert results == expected
