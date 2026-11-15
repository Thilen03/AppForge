"""Advanced launch settings across real processes, desktop entries and persistence."""
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from appforge.core.database import Database
from appforge.core.desktop import DesktopError, render_entry
from appforge.core.launch_options import (
    ARGUMENTS, DIRECTORY, TERMINAL, LaunchOptionsError, options_of, parse_arguments,
    validate_launch_options,
)
from appforge.core.library import LibraryError, LibraryService
from appforge.core.library_transfer import export_library, read_export, preview_import, prepare_import, validate_record, TransferError
from appforge.core.models import AppEntry
from appforge.core.updates.installer import InstallResult, backup_dir_for
from appforge.core.updates.service import UpdateService
from appforge.core.backups import BackupService
from appforge.services import launcher
from appforge.ui.dialogs import AddApplicationDialog, EditApplicationDialog
from appforge.ui.launch_options_dialog import LaunchOptionsDialog
from test_desktop import parse_exec, read_entry_from_text
from test_gui import qapp, wait_for  # noqa: F401


def script(service, tmp_path, **kw):
    path = tmp_path / 'Example-1.0.sh'
    path.write_text('#!/bin/sh\n# launch options fixture\nexit 0\n')
    path.chmod(0o755)
    return service.add_application(str(path), **kw)


def test_arguments_are_literal_with_quoting_and_empty_values():
    assert parse_arguments(' --name "two words" "" \'$HOME\' \'*.txt\' \'%U\' \'a;b\' ') == [
        '--name', 'two words', '', '$HOME', '*.txt', '%U', 'a;b']
    assert validate_launch_options({}) == {}
    assert validate_launch_options({ARGUMENTS: ' ', DIRECTORY: '', TERMINAL: False}) == {}


@pytest.mark.parametrize('options', [
    {ARGUMENTS: '"unclosed'}, {ARGUMENTS: 'x\\'}, {ARGUMENTS: 'a\nb'},
    {ARGUMENTS: 'x' * 8193}, {ARGUMENTS: 'x ' * 257}, {ARGUMENTS: []},
    {DIRECTORY: 'relative/path'}, {DIRECTORY: '/tmp/\x00bad'}, {DIRECTORY: 3},
    {TERMINAL: 'yes'}, {'unexpected': True}, None,
])
def test_invalid_configuration_rejected(options):
    with pytest.raises(LaunchOptionsError):
        validate_launch_options(options)


def test_service_validates_before_registration_and_preserves_existing_on_failure(service, tmp_path):
    entry = script(service, tmp_path, launch_options={ARGUMENTS: '--test', TERMINAL: True})
    original = service.get(entry.id)
    with pytest.raises(LibraryError):
        service.update_application(entry.id, name='Should not persist', launch_options={ARGUMENTS: '"bad'})
    assert service.get(entry.id) == original
    second = tmp_path / 'invalid.sh'
    second.write_text('#!/bin/sh\nexit 0\n')
    with pytest.raises(LibraryError):
        service.add_application(str(second), launch_options={DIRECTORY: 'relative'})
    assert service.find_by_path(str(second)) is None
    service.update_application(entry.id, name='Renamed')
    assert options_of(service.get(entry.id)) == {ARGUMENTS: '--test', TERMINAL: True}
    assert options_of(service.update_application(entry.id, launch_options={})) == {}


def test_actual_process_receives_args_directory_and_environment_without_shell(service, tmp_path):
    folder = tmp_path / 'Working folder'
    folder.mkdir()
    program = tmp_path / 'program'
    program.write_text(f'#!{sys.executable}\nimport os,sys,json\n'
                       'print(json.dumps([sys.argv[1:],os.getcwd(),os.environ["TEST_LAUNCH"]]))\n')
    program.chmod(0o755)
    marker = tmp_path / 'must-not-exist'
    args = ['--profile', 'Two words', '', '$HOME', '*.txt', '%U', f'$(touch {marker})', ';']
    entry = service.add_application(str(program), env_vars={'TEST_LAUNCH': 'works'},
                                    launch_options={ARGUMENTS: shlex.join(args), DIRECTORY: str(folder)})
    handle = launcher.launch(entry)
    assert handle.process.wait(timeout=10) == 0
    assert json.loads(handle.log_path.read_text()) == [args, str(folder), 'works']
    assert not marker.exists()


def test_default_directory_and_missing_directory_error(service, tmp_path, monkeypatch):
    entry = script(service, tmp_path)
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda cmd, **kw: calls.append((cmd, kw)))
    launcher.launch(entry)
    assert calls[0][0] == [entry.path]
    assert calls[0][1]['cwd'] == str(tmp_path)
    entry = service.update_application(entry.id, launch_options={DIRECTORY: str(tmp_path / 'missing')})
    with pytest.raises(launcher.LaunchError, match='working directory'):
        launcher.launch(entry)
    assert len(calls) == 1


def test_terminal_uses_desktop_helper_and_kde_fallback_with_argv(monkeypatch):
    seen = []
    def helper(name, path=None):
        seen.append(name)
        return '/bin/xdg-terminal-exec' if name == 'xdg-terminal-exec' else None
    monkeypatch.setattr(launcher.shutil, 'which', helper)
    argv = ['/tmp/Tool with spaces', '--profile', 'Work profile']
    assert launcher.terminal_command(argv, {}) == ['/bin/xdg-terminal-exec', *argv]
    monkeypatch.setattr(launcher.shutil, 'which', lambda name, path=None: '/bin/konsole' if name == 'konsole' else None)
    assert launcher.terminal_command(argv, {'XDG_CURRENT_DESKTOP': 'KDE'}) == ['/bin/konsole', '-e', *argv]
    monkeypatch.setattr(launcher.shutil, 'which', lambda *a, **kw: None)
    with pytest.raises(launcher.LaunchError, match='No supported terminal'):
        launcher.terminal_command(argv, {})


@pytest.mark.parametrize('program,flags', [
    ('gnome-terminal', ['--']), ('xfce4-terminal', ['-x']), ('kitty', ['--']),
    ('alacritty', ['-e']), ('foot', ['--']), ('xterm', ['-e']),
])
def test_terminal_fallback_argument_separators(monkeypatch, program, flags):
    monkeypatch.setattr(launcher.shutil, 'which', lambda name, path=None: '/bin/' + name if name == program else None)
    assert launcher.terminal_command(['/tmp/app', 'a b'], {}) == ['/bin/' + program, *flags, '/tmp/app', 'a b']


def test_terminal_launch_passes_environment_directory_and_detachment(service, tmp_path, monkeypatch):
    entry = script(service, tmp_path, env_vars={'CUSTOM': 'value'},
                   launch_options={ARGUMENTS: '"two words"', DIRECTORY: str(tmp_path), TERMINAL: True})
    monkeypatch.setattr(launcher.shutil, 'which', lambda name, path=None: '/bin/konsole' if name == 'konsole' else None)
    captured = []
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda cmd, **kw: captured.append((cmd, kw)))
    launcher.launch(entry)
    command, kwargs = captured[0]
    assert command == ['/bin/konsole', '-e', entry.path, 'two words']
    assert kwargs['cwd'] == str(tmp_path) and kwargs['env']['CUSTOM'] == 'value'
    assert kwargs['start_new_session'] and kwargs.get('shell', False) is False


def test_desktop_roundtrips_literal_arguments_percent_codes_and_terminal(service, tmp_path):
    args = ['--profile', 'two words', '', '$HOME', '%U', '`hi`', 'a\\b', 'a;b']
    entry = script(service, tmp_path, env_vars={'HELLO': 'two words'},
                   launch_options={ARGUMENTS: shlex.join(args), DIRECTORY: str(tmp_path / 'Work folder'), TERMINAL: True})
    entry.metadata['desktop_exec'] = '%F'
    fields = read_entry_from_text(render_entry(entry))
    assert parse_exec(fields['Exec']) == ['env', 'HELLO=two words', entry.path, *args, '%F']
    assert fields['Path'] == str(tmp_path / 'Work folder') and fields['Terminal'] == 'true'
    entry.metadata[ARGUMENTS] = '"bad'
    with pytest.raises(DesktopError, match='launch options'):
        render_entry(entry)


def test_preferences_persist_through_update_rollback_and_launcher_rewrite(service, tmp_path):
    options = {ARGUMENTS: '--verbose', DIRECTORY: str(tmp_path), TERMINAL: True}
    entry = script(service, tmp_path, launch_options=options, integrate_desktop=True)
    launcher_path = service.desktop.entry_path(entry.id)
    directory = backup_dir_for(Path(entry.path))
    directory.mkdir()
    backup = directory / 'Example-1.0.sh-1.0.bak'
    backup.write_bytes(Path(entry.path).read_bytes())
    Path(entry.path).write_text('#!/bin/sh\necho new\n')
    current = service.get(entry.id)
    current.latest_version = '2.0'
    service.db.update(current)
    UpdateService(service).apply_install(entry.id, InstallResult(entry.path, str(backup), 'not available', 19), 'v2.0')
    assert options_of(service.get(entry.id)) == options
    BackupService(service).rollback(entry.id, str(backup))
    assert options_of(service.get(entry.id)) == options
    assert launcher_path == service.desktop.entry_path(entry.id)
    assert 'Terminal=true' in launcher_path.read_text()
    other = Database(service.db.path)
    try:
        assert options_of(other.get(entry.id)) == options
    finally:
        other.close()


def test_export_import_launch_options_and_invalid_record_rejection(service, tmp_path):
    options = {ARGUMENTS: '--profile "Work profile"', DIRECTORY: str(tmp_path / 'missing'), TERMINAL: True}
    entry = script(service, tmp_path, launch_options=options)
    destination = tmp_path / 'library.json'
    export_library([entry], destination)
    records = read_export(destination)
    assert {k: records[0]['metadata'][k] for k in options} == options
    target_db = Database(tmp_path / 'target.db')
    target = LibraryService(target_db, tmp_path / 'icons')
    try:
        candidate = preview_import(records, [])[0]
        imported = target.import_configuration(prepare_import(candidate, [], target.icons_dir))
        assert options_of(imported) == options
        records[0]['metadata'][ARGUMENTS] = '"invalid'
        with pytest.raises(TransferError, match='Invalid arguments'):
            validate_record(records[0])
    finally:
        target_db.close()


def test_launch_editor_validation_picker_and_defaults(qapp, tmp_path, monkeypatch):
    dialog = LaunchOptionsDialog({})
    dialog.arguments_edit.setText('"bad')
    assert not dialog.use_btn.isEnabled() and dialog.error_lbl.text()
    dialog.arguments_edit.setText('--verbose')
    dialog.directory_edit.setText('relative')
    assert not dialog.use_btn.isEnabled()
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: str(tmp_path))
    dialog.browse_btn.click()
    dialog.terminal_cb.setChecked(True)
    dialog.use_btn.click()
    assert dialog.options == {ARGUMENTS: '--verbose', DIRECTORY: str(tmp_path), TERMINAL: True}
    dialog._defaults()
    assert dialog._values() == {}
    dialog.close()


def test_edit_options_are_only_committed_when_parent_saved(qapp, service, tmp_path, monkeypatch):
    entry = script(service, tmp_path)
    def edit(child):
        child.arguments_edit.setText('--profile "Work profile"')
        child.terminal_cb.setChecked(True)
        child._accept()
        return child.result()
    monkeypatch.setattr(LaunchOptionsDialog, 'exec', edit)
    dialog = EditApplicationDialog(service, entry)
    dialog.launch_options_btn.click()
    assert options_of(service.get(entry.id)) == {}
    dialog.reject()
    assert options_of(service.get(entry.id)) == {}
    saved = EditApplicationDialog(service, service.get(entry.id))
    saved.launch_options_btn.click()
    saved._save()
    assert options_of(service.get(entry.id)) == {ARGUMENTS: '--profile "Work profile"', TERMINAL: True}
    reopened = EditApplicationDialog(service, service.get(entry.id))
    assert reopened._launch_options == options_of(service.get(entry.id))
    reopened.close()


def test_add_options_and_scrollable_footer(qapp, service, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QScrollArea
    path = tmp_path / 'Tool.sh'
    path.write_text('#!/bin/sh\n# launch options fixture\nexit 0\n')
    path.chmod(0o755)
    dialog = AddApplicationDialog(service, initial_path=str(path))
    assert wait_for(qapp, lambda: dialog.metadata is not None)
    def edit(child):
        child.arguments_edit.setText('--test')
        child._accept()
        return child.result()
    monkeypatch.setattr(LaunchOptionsDialog, 'exec', edit)
    dialog.launch_options_btn.click()
    dialog.resize(540, 440)
    dialog.show()
    qapp.processEvents()
    scroll = dialog.findChild(QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.widget().width() <= scroll.viewport().width()
    assert not scroll.isAncestorOf(dialog.add_btn)
    assert dialog.add_btn.isVisible()
    dialog._accept()
    assert dialog.added and options_of(service.get(dialog.added.id)) == {ARGUMENTS: '--test'}


def test_inaccessible_working_directory_is_reported_without_crashing(service, tmp_path, monkeypatch):
    entry = script(service, tmp_path)
    def denied(path):
        raise PermissionError('folder access denied')
    monkeypatch.setattr(Path, 'is_dir', denied)
    with pytest.raises(launcher.LaunchError, match='working directory'):
        launcher.launch(entry)
