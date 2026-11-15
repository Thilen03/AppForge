"""Named profile persistence, shell-free launches, transfer and real card/editor flows."""
from copy import deepcopy
import json
import sys

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from appforge.core.database import Database
from appforge.core.envvars import ENV_KEY
from appforge.core.launch_options import ARGUMENTS, DIRECTORY, TERMINAL, LaunchOptionsError
from appforge.core.launch_profiles import (
    DEFAULT_PROFILE, PROFILES_KEY, entry_for_profile, profile_choices, validate_profiles,
)
from appforge.core.library import LibraryError
from appforge.core.models import UpdateStatus
from appforge.core.library_transfer import export_library, read_export, prepare_import, preview_import, TransferError
from appforge.services import launcher
from appforge.ui.launch_profiles_dialog import LaunchProfilesDialog
from appforge.ui.main_window import MainWindow
from test_gui import qapp, wait_for  # noqa: F401
from test_tray import add


def debug_profile(**values):
    return {'id': 'debug-id', 'name': 'Debug', ENV_KEY: {'APPFORGE_PROFILE_MODE': 'debug'},
            ARGUMENTS: '--debug', **values}


@pytest.mark.parametrize('profiles', [None, {}, [None], [{}],
    [debug_profile(id='default')], [debug_profile(name='DEFAULT')],
    [debug_profile(name='')], [debug_profile(name='a' * 65)],
    [debug_profile(name='bad\nname')], [debug_profile(name='bad\ud800')],
    [debug_profile(id='../bad')], [debug_profile(), debug_profile(id='second', name='DEBUG')],
    [debug_profile(), debug_profile(name='Other')], [debug_profile(extra='unsupported')],
    [debug_profile(env_vars={'9BAD': 'x'})], [debug_profile(env_vars={'GOOD': 1})],
    [debug_profile(env_vars={' GOOD ': 'x'})], [debug_profile(launch_arguments='"broken')],
    [debug_profile(launch_directory='relative')], [debug_profile(run_in_terminal='yes')],
    [debug_profile(id=f'id{i}', name=f'Name{i}') for i in range(33)],
])
def test_invalid_profiles_rejected(profiles):
    with pytest.raises(LaunchOptionsError):
        validate_profiles(profiles)


def test_default_compatibility_independent_snapshots_and_atomic_validation(service, tmp_path):
    entry = add(service, tmp_path)
    service.update_application(entry.id, env_vars={'MODE': 'default'}, launch_options={ARGUMENTS: '--default'})
    before = service.get(entry.id)
    assert entry_for_profile(before) is before
    updated = service.update_application(entry.id, launch_profiles=[debug_profile()])
    resolved = entry_for_profile(updated, 'debug-id')
    assert resolved.metadata[ENV_KEY] == {'APPFORGE_PROFILE_MODE': 'debug'}
    assert resolved.metadata[ARGUMENTS] == '--debug'
    assert updated.metadata[ARGUMENTS] == '--default' and updated.metadata[ENV_KEY] == {'MODE': 'default'}
    with pytest.raises(LibraryError):
        service.update_application(entry.id, env_vars={'MODE': 'changed'},
                                   launch_profiles=[debug_profile(name='Default')])
    assert service.get(entry.id).metadata == updated.metadata
    service.update_application(entry.id, launch_options={ARGUMENTS: '--new-default'})
    assert entry_for_profile(service.get(entry.id), 'debug-id').metadata[ARGUMENTS] == '--debug'
    reopened = Database(service.db.path)
    try:
        assert reopened.get(entry.id).metadata[PROFILES_KEY] == [debug_profile()]
    finally:
        reopened.close()


def test_real_launch_uses_profile_environment_arguments_and_directory(service, tmp_path, monkeypatch):
    script = tmp_path / 'inspect.py'
    script.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                      'print(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(), '
                      '"mode": os.getenv("APPFORGE_PROFILE_MODE"), '
                      '"only_default": os.getenv("APPFORGE_PROFILE_DEFAULT_ONLY")}))\n')
    script.chmod(0o755)
    work = tmp_path / 'debug-work'
    work.mkdir()
    monkeypatch.delenv('APPFORGE_PROFILE_DEFAULT_ONLY', raising=False)
    entry = service.add_application(str(script), env_vars={
        'APPFORGE_PROFILE_MODE': 'default', 'APPFORGE_PROFILE_DEFAULT_ONLY': 'yes'},
        launch_options={ARGUMENTS: '--default'})
    entry = service.update_application(entry.id, launch_profiles=[debug_profile(
        launch_arguments='--debug "$HOME" "a;b" ""', launch_directory=str(work))])
    metadata = deepcopy(entry.metadata)
    handle = launcher.launch(entry, 'debug-id')
    assert handle.process.wait(timeout=5) == 0
    result = json.loads(handle.log_path.read_text())
    assert result == {'args': ['--debug', '$HOME', 'a;b', ''], 'cwd': str(work),
                      'mode': 'debug', 'only_default': None}
    handle = launcher.launch(entry)
    assert handle.process.wait(timeout=5) == 0
    result = json.loads(handle.log_path.read_text())
    assert result == {'args': ['--default'], 'cwd': str(tmp_path), 'mode': 'default', 'only_default': 'yes'}
    assert entry.metadata == metadata and service.get(entry.id).metadata == metadata


def test_missing_profile_bad_directory_and_terminal_route(service, tmp_path, monkeypatch):
    entry = add(service, tmp_path)
    entry = service.update_application(entry.id, launch_profiles=[debug_profile(launch_directory=str(tmp_path / 'gone'))])
    with pytest.raises(launcher.LaunchError, match='no longer exists'):
        launcher.launch(entry, 'deleted')
    with pytest.raises(launcher.LaunchError, match='working directory'):
        launcher.launch(entry, 'debug-id')
    entry = service.update_application(entry.id, launch_profiles=[debug_profile(run_in_terminal=True)])
    called = []
    def terminal(argv, env):
        called.append((argv, env['APPFORGE_PROFILE_MODE']))
        return argv  # real fixture script, without requiring an installed desktop terminal
    monkeypatch.setattr(launcher, 'terminal_command', terminal)
    handle = launcher.launch(entry, 'debug-id')
    assert handle.process.wait(timeout=5) == 0
    assert called == [([entry.path, '--debug'], 'debug')]


def test_corrupt_optional_profiles_do_not_hide_default(service, tmp_path):
    entry = add(service, tmp_path)
    entry.metadata[PROFILES_KEY] = 'broken'
    assert profile_choices(entry) == [('default', 'Default')]
    assert entry_for_profile(entry) is entry
    with pytest.raises(LaunchOptionsError):
        entry_for_profile(entry, 'debug-id')


@pytest.mark.parametrize('export_env', [False, True])
@pytest.mark.parametrize('import_env', [False, True])
def test_transfer_profiles_honors_nested_environment_opt_out(service, tmp_path, export_env, import_env):
    entry = add(service, tmp_path)
    entry = service.update_application(entry.id, launch_profiles=[debug_profile()], env_vars={'DEFAULT_SECRET': 'private'})
    path = tmp_path / 'export.json'
    export_library([entry], path, include_environment=export_env)
    records = read_export(path)
    candidate = preview_import(records, [])[0]
    prepared = prepare_import(candidate, [], service.icons_dir, environment=import_env)
    profile = prepared.record['metadata'][PROFILES_KEY][0]
    assert profile['id'] == 'debug-id' and profile[ARGUMENTS] == '--debug'
    assert bool(profile.get(ENV_KEY)) == (export_env and import_env)
    assert bool(prepared.record['metadata'].get(ENV_KEY)) == (export_env and import_env)
    if not export_env:
        assert 'private' not in path.read_text() and 'APPFORGE_PROFILE_MODE' not in path.read_text()
    service.remove_application(entry.id)
    restored = service.import_configuration(prepared)
    assert restored.metadata[PROFILES_KEY] == validate_profiles(prepared.record['metadata'][PROFILES_KEY])


@pytest.fixture
def editor(qapp, service, tmp_path):
    entry = add(service, tmp_path)
    service.update_application(entry.id, env_vars={'MODE': 'default'}, launch_options={ARGUMENTS: '--base'})
    dialog = LaunchProfilesDialog(service, service.get(entry.id))
    dialog.show()
    qapp.processEvents()
    yield dialog, entry
    dialog.close()
    dialog.deleteLater()
    qapp.processEvents()


def test_editor_create_edit_default_save_and_reopen(editor, service, qapp):
    dialog, entry = editor
    assert not dialog.name_edit.isEnabled() and not dialog.delete_btn.isEnabled()
    dialog.arguments_edit.setText('--new-default')
    dialog.new_btn.click()
    assert dialog.arguments_edit.text() == '--new-default'
    assert dialog.env_edit.toPlainText() == 'MODE=default'
    dialog.name_edit.setText('Debug')
    dialog.arguments_edit.setText('--debug')
    dialog.env_edit.setPlainText('MODE=debug\nDEBUG=1')
    dialog.terminal_cb.setChecked(True)
    dialog.save_btn.click()
    assert dialog.result() == dialog.DialogCode.Accepted
    saved = service.get(entry.id)
    assert saved.metadata[ARGUMENTS] == '--new-default'
    assert saved.metadata[ENV_KEY] == {'MODE': 'default'}
    profile = saved.metadata[PROFILES_KEY][0]
    assert profile['name'] == 'Debug' and profile[TERMINAL]
    reopened = LaunchProfilesDialog(service, saved)
    reopened.profile_list.setCurrentRow(1)
    assert reopened.arguments_edit.text() == '--debug'
    assert reopened.env_edit.toPlainText() == 'MODE=debug\nDEBUG=1'
    reopened.name_edit.setText('Diagnostics')
    reopened.save_btn.click()
    assert service.get(entry.id).metadata[PROFILES_KEY][0]['id'] == profile['id']
    reopened.deleteLater()
    qapp.processEvents()


def test_editor_cancel_invalid_names_options_and_deletion(editor, service):
    dialog, entry = editor
    before = service.get(entry.id).metadata
    dialog.new_btn.click()
    dialog.name_edit.setText('Default')
    dialog.save_btn.click()
    assert 'unique' in dialog.error_lbl.text()
    assert service.get(entry.id).metadata == before
    dialog.name_edit.setText('Debug')
    dialog.arguments_edit.setText('"invalid')
    dialog.profile_list.setCurrentRow(0)
    assert dialog.profile_list.currentRow() == 1 and dialog.error_lbl.text()
    dialog.delete_btn.click()  # an invalid draft can still be discarded
    assert len(dialog.drafts) == 1
    dialog.arguments_edit.setText('--unsaved')
    dialog.new_btn.click()
    dialog.reject()
    assert service.get(entry.id).metadata == before


@pytest.fixture
def window(qapp, service, tmp_path):
    entry = add(service, tmp_path)
    service.update_application(entry.id, launch_profiles=[debug_profile()])
    win = MainWindow(service)
    win.show()
    qapp.processEvents()
    yield win, entry
    win._quitting = True
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_dropdown_select_launch_refresh_and_default_shortcut(window, service, monkeypatch):
    win, entry = window
    card = win._card(entry.id)
    calls = []
    class Handle:
        def early_exit_code(self):
            return None
    monkeypatch.setattr(launcher, 'launch', lambda e, profile_id=DEFAULT_PROFILE: calls.append(profile_id) or Handle())
    actions = card.profile_btn.menu().actions()
    assert [a.text() for a in actions if not a.isSeparator()] == ['Default', 'Debug', 'Edit profiles…']
    assert actions[0].isChecked()
    actions[1].trigger()
    assert actions[1].isChecked() and not actions[0].isChecked()
    assert not calls
    card._primary.click()
    assert calls == ['debug-id']
    win._refresh_card(entry.id)
    assert win._card(entry.id).launch_profile == 'debug-id'
    win._card(entry.id)._primary.click()
    win.launch(entry.id)  # details/tray path remains Default
    assert calls == ['debug-id', 'debug-id', DEFAULT_PROFILE]
    service.update_application(entry.id, launch_profiles=[])
    win._refresh_card(entry.id)
    assert win._card(entry.id).launch_profile == DEFAULT_PROFILE


def test_profile_arrow_is_button_in_selection_mode(window, qapp):
    win, entry = window
    win.select_btn.click()
    card = win._card(entry.id)
    def choose():
        menu = card.profile_btn.menu()
        assert menu.isVisible()
        menu.actions()[1].trigger()
        menu.close()
    QTimer.singleShot(0, choose)
    QTest.mouseClick(card.profile_btn, Qt.LeftButton)
    assert wait_for(qapp, lambda: card.launch_profile == 'debug-id')
    assert card.launch_profile == 'debug-id' and not win._selected


def test_real_edit_profiles_menu_flow(window, service, qapp):
    win, entry = window
    def edit():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, LaunchProfilesDialog)
        dialog.new_btn.click()
        dialog.name_edit.setText('Safe mode')
        dialog.arguments_edit.setText('--safe-mode')
        dialog.save_btn.click()
    QTimer.singleShot(0, edit)
    win._card(entry.id).profile_btn.menu().actions()[-1].trigger()
    assert len(service.get(entry.id).metadata[PROFILES_KEY]) == 2
    assert 'Safe mode' in [a.text() for a in win._card(entry.id).profile_btn.menu().actions()]


@pytest.mark.parametrize('mode', ['light', 'dark'])
@pytest.mark.parametrize('retry', [False, True])
def test_split_launch_button_geometry_with_update_and_actions(window, service, qapp, mode, retry):
    from appforge.ui import theme
    win, entry = window
    entry = service.get(entry.id)
    entry.github_repo = 'https://github.com/example/app'
    entry.latest_version = '2'
    entry.update_status = UpdateStatus.FAILED if retry else UpdateStatus.UPDATE_AVAILABLE
    entry.metadata['update'] = {'asset': {'url': 'https://example.org/app'}, 'install_error': 'failure'}
    service.db.update(entry)
    win._refresh_card(entry.id)
    theme.apply_theme(qapp, mode)
    qapp.processEvents()
    card = win._card(entry.id)
    main, arrow = card._primary, card.profile_btn
    assert main.height() == arrow.height()
    assert main.mapTo(card, main.rect().topRight()).x() + 1 == arrow.mapTo(card, arrow.rect().topLeft()).x()
    assert main.mapTo(card, main.rect().topLeft()).y() == arrow.mapTo(card, arrow.rect().topLeft()).y()
    assert arrow.mapTo(card, arrow.rect().bottomRight()).x() < card._update_btn.x()
    assert card._update_btn.geometry().right() < card._actions.x()
    assert card._actions.geometry().right() < card.width()
