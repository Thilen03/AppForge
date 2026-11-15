"""Offline embedded update hints, safe parsing and reviewable import suggestions."""
import struct
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from test_gui import qapp  # noqa: F401
from test_discovery import wait
from appforge.core.discovery import scan
from appforge.core.formats.appimage_update import (
    MAX_UPDATE_BYTES, SUGGESTED_SOURCE_KEY, read_update_information, suggest_source,
)
from appforge.core.library import inspect_file
from appforge.ui.dialogs import AddApplicationDialog
from appforge.ui.discovery_dialog import DiscoveryDialog

INFO = 'gh-releases-zsync|ExampleOrg|ExampleApp|latest|ExampleApp-*.AppImage.zsync'
SOURCE = 'https://github.com/ExampleOrg/ExampleApp'


def image(path, info=INFO, *, bits=64, endian='<', extended=False):
    """Tiny non-runnable ELF fixture with an actual .upd_info section."""
    is64 = bits == 64
    header = bytearray(64 if is64 else 52)
    header[:7] = b'\x7fELF' + bytes((2 if is64 else 1, 1 if endian == '<' else 2, 1))
    header[8:11] = b'AI\x02'
    stride = 64 if is64 else 40
    table = 128
    if is64:
        struct.pack_into(endian + 'Q', header, 40, table)
        struct.pack_into(endian + 'HHH', header, 58, stride, 0 if extended else 3,
                         0xFFFF if extended else 1)
    else:
        struct.pack_into(endian + 'I', header, 32, table)
        struct.pack_into(endian + 'HHH', header, 46, stride, 0 if extended else 3,
                         0xFFFF if extended else 1)
    names = b'\0.shstrtab\0.upd_info\0'
    names_at = table + 3 * stride
    data_at = names_at + len(names)
    payload = info.encode('ascii') if isinstance(info, str) else info
    payload = payload.ljust(512, b'\0')
    fmt = endian + ('IIQQQQIIQQ' if is64 else 'IIIIIIIIII')
    sections = [
        (0, 0, 0, 0, 0, 3 if extended else 0, 1 if extended else 0, 0, 0, 0),
        (1, 3, 0, 0, names_at, len(names), 0, 0, 1, 0),
        (11, 1, 0, 0, data_at, len(payload), 0, 0, 1, 0),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header).ljust(table, b'\0') + b''.join(
        struct.pack(fmt, *section) for section in sections) + names + payload)
    return path


@pytest.mark.parametrize('bits', [32, 64])
@pytest.mark.parametrize('endian', ['<', '>'])
@pytest.mark.parametrize('extended', [False, True])
def test_elf_update_field_and_metadata_without_squashfs(tmp_path, bits, endian, extended):
    path = image(tmp_path / 'Example-1.0.AppImage', bits=bits, endian=endian, extended=extended)
    assert read_update_information(path, 2) == INFO
    md = inspect_file(path)
    assert md.extra[SUGGESTED_SOURCE_KEY] == SOURCE
    assert md.version == '1.0'
    assert md.warnings  # Suggestion survives the normal filesystem metadata fallback.


def test_type_one_field(tmp_path):
    path = tmp_path / 'Old.AppImage'
    data = bytearray(33651 + 512)
    data[:4] = b'\x7fELF'
    data[8:11] = b'AI\x01'
    data[33651:33651 + len(INFO)] = INFO.encode()
    path.write_bytes(data)
    assert read_update_information(path, 1) == INFO
    assert inspect_file(path).extra[SUGGESTED_SOURCE_KEY] == SOURCE


@pytest.mark.parametrize('info,expected', [
    (INFO, SOURCE),
    (INFO.replace('|latest|', '|latest-pre|'), SOURCE),
    (INFO.replace('|latest|', '|latest-all|'), SOURCE),
    (INFO.replace('|latest|', '|continuous|'), SOURCE),
    ('zsync|https://github.com/o/r/releases/download/v1/App.AppImage.zsync', 'https://github.com/o/r'),
    ('zsync|https://github.com/o/r/releases/latest/download/App.AppImage.zsync', 'https://github.com/o/r'),
    ('zsync|https://gitlab.com/group/sub/project/-/releases/v1/downloads/App.zsync',
     'https://gitlab.com/group/sub/project'),
    ('zsync|https://codeberg.org/o/r/releases/download/v1/App.zsync', 'https://codeberg.org/o/r'),
    ('zsync|https://git.example.dev:8443/o/r/releases/download/v1/App.zsync',
     'https://git.example.dev:8443/o/r'),
    ('zsync|https://git.example.dev/group/sub/project/-/releases/v1/downloads/linux/App.zsync',
     'https://git.example.dev/group/sub/project'),
])
def test_supported_transports(info, expected):
    assert suggest_source(info) == expected


@pytest.mark.parametrize('info', [
    None, '', 'guess', 'pling-v1-zsync|123|*.AppImage', 'bintray-zsync|o|r|latest|*.zsync',
    'gh-releases-zsync|o|r|latest', 'gh-releases-zsync|../o|r|latest|*.zsync',
    'gh-releases-zsync|o|..|latest|*.zsync', 'gh-releases-zsync|o|r||*.zsync',
    'gh-releases-zsync|o|r|latest|../App.zsync', 'gh-releases-zsync|o|r|latest|App.AppImage',
    INFO + '\nother', 'zsync|http://github.com/o/r/releases/download/v1/App.zsync',
    'zsync|https://user:secret@github.com/o/r/releases/download/v1/App.zsync',
    'zsync|https://github.com:invalid/o/r/releases/download/v1/App.zsync',
    'zsync|https://github.com/o/r/releases/download/v1/App.zsync?token=secret',
    'zsync|https://github.com/o/r/releases/download/v1/App.zsync#x',
    'zsync|https://example.com/downloads/App.zsync',
    'zsync|https://example.com/owner/repo',
    'zsync|https://github.com/o/%2E%2E/releases/download/v1/App.zsync',
    'zsync|https://github.com/o/r/releases/download/v1/App.AppImage',
    'zsync|https://[badhost/o/r/releases/download/v1/App.zsync',
    'zsync|file:///tmp/App.zsync', 'x' * (MAX_UPDATE_BYTES + 1),
])
def test_unsupported_or_unsafe_sources_are_not_guessed(info):
    assert suggest_source(info) is None


@pytest.mark.parametrize('corruption', ['truncated', 'table', 'count', 'names', 'payload', 'nobits', 'encoding', 'two_values'])
def test_malformed_fields_fail_closed(tmp_path, corruption):
    path = image(tmp_path / 'Bad.AppImage')
    data = bytearray(path.read_bytes())
    if corruption == 'truncated':
        data = data[:40]
    elif corruption == 'table':
        struct.pack_into('<Q', data, 40, 2**63)
    elif corruption == 'count':
        struct.pack_into('<H', data, 60, 65534)
    elif corruption == 'names':
        struct.pack_into('<Q', data, 128 + 64 + 32, 2**40)
    elif corruption == 'payload':
        struct.pack_into('<Q', data, 128 + 128 + 32, MAX_UPDATE_BYTES + 1)
    elif corruption == 'nobits':
        struct.pack_into('<I', data, 128 + 128 + 4, 8)
    else:
        start = 128 + 192 + len(b'\0.shstrtab\0.upd_info\0')
        if corruption == 'encoding':
            data[start] = 255
        else:
            data[start:start + 5] = b'a\0b\0\0'
    path.write_bytes(data)
    assert read_update_information(path, 2) is None
    assert read_update_information(tmp_path / 'missing', 2) is None


def test_local_form_prefill_edit_clear_and_file_change(qapp, tmp_path, service):
    first = image(tmp_path / 'One.AppImage')
    second = image(tmp_path / 'Two.AppImage', INFO.replace('ExampleApp', 'OtherApp'))
    blank = image(tmp_path / 'Blank.AppImage', '')
    dialog = AddApplicationDialog(service, initial_path=str(first))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == SOURCE
    assert 'embedded update information' in dialog.repo_msg.text()
    dialog._set_path(str(second))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == 'https://github.com/ExampleOrg/OtherApp'
    dialog._set_path(str(blank))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == ''
    dialog._set_path(str(first))
    wait(qapp, lambda: dialog.metadata is not None)
    dialog.repo_edit.clear()
    dialog.repo_edit.textEdited.emit('')
    dialog._set_path(str(second))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == ''
    dialog._accept()
    assert dialog.added.github_repo is None
    dialog.close()


def test_user_or_download_source_is_never_overwritten(qapp, tmp_path, service):
    path = image(tmp_path / 'One.AppImage')
    dialog = AddApplicationDialog(service)
    dialog.repo_edit.setText('https://codeberg.org/manual/repo')
    dialog._set_path(str(path))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == 'https://codeberg.org/manual/repo'
    dialog._accept()
    assert dialog.added.github_repo == 'https://codeberg.org/manual/repo'
    dialog.close()


def test_discovery_sources_can_be_accepted_changed_cleared_and_validated(qapp, tmp_path, service, monkeypatch):
    for name in ('one', 'two', 'three'):
        image(tmp_path / f'{name}.AppImage')
    dialog = DiscoveryDialog(service, preview=scan([str(tmp_path)]))
    assert all(dialog.table.cellWidget(i, 5).text() == SOURCE for i in range(3))
    assert not dialog._selected()
    dialog.table.cellWidget(1, 5).setText('https://codeberg.org/manual/repo')
    dialog.table.cellWidget(2, 5).clear()
    paths = [c.path for c in dialog.candidates]
    dialog._select(True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    dialog.table.cellWidget(0, 5).setText('not a source')
    dialog._import(False)
    assert not service.list_applications() and 'Check the update sources' in dialog.status.text()
    dialog.table.cellWidget(0, 5).setText(SOURCE)
    dialog._import(False)
    wait(qapp, lambda: not dialog._importing)
    entries = {e.path: e for e in service.list_applications()}
    assert [entries[p].github_repo for p in paths] == [SOURCE, 'https://codeberg.org/manual/repo', None]
    assert all(not entries[p].metadata.get('include_prereleases') for p in paths)
    dialog.close()


def test_real_packaged_appimage_info_and_nonexecuting_inspection(fixtures, tmp_path, monkeypatch):
    import make_fixtures
    import subprocess
    import urllib.request
    path = make_fixtures.build(tmp_path, 'source', 'Source App', '1.2', '#123456', update_info=INFO)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Executed a process'))
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Used the network'))
    before = path.read_bytes()
    metadata = inspect_file(path)
    assert metadata.extra[SUGGESTED_SOURCE_KEY] == SOURCE
    assert metadata.name_suggestion == 'Source App' and metadata.version == '1.2'
    assert metadata.icon_data and path.read_bytes() == before


def test_download_source_takes_precedence_over_embedded_hint(qapp, tmp_path, service):
    from appforge.core.downloads import DownloadChoice, DownloadResult, file_signature
    from appforge.core.updates.github import Asset, Release
    path = image(tmp_path / 'Downloaded.AppImage')
    chosen_source = 'https://codeberg.org/chosen/repository'
    asset = Asset('Downloaded.AppImage', 'https://codeberg.org/chosen/repository/releases/download/v5/Downloaded.AppImage')
    choice = DownloadChoice(chosen_source, Release('v5.0'), asset, 'appimage')
    result = DownloadResult(str(path), choice, 'sha256:test', file_signature(path))
    dialog = AddApplicationDialog(service, initial_path=str(path), downloaded=result)
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == chosen_source
    assert 'Suggested from' not in dialog.repo_msg.text()
    dialog._accept()
    assert dialog.added.github_repo == chosen_source and dialog.added.installed_version == '5.0'
    dialog.close()


@pytest.mark.parametrize('chosen', ['', 'https://codeberg.org/my/project'])
def test_typing_before_inspection_finishes_is_preserved(qapp, tmp_path, service, monkeypatch, chosen):
    import appforge.ui.dialogs as module
    class Pool:
        def start(self, job):
            pass
    monkeypatch.setattr(module.QThreadPool, 'globalInstance', lambda: Pool())
    path = image(tmp_path / 'One.AppImage')
    dialog = AddApplicationDialog(service, initial_path=str(path))
    dialog.repo_edit.setText(chosen)
    dialog.repo_edit.textEdited.emit(chosen)
    dialog._on_inspected(dialog._token, inspect_file(path))
    assert dialog.repo_edit.text() == chosen
    dialog.close()


def test_old_inspection_cannot_fill_source_after_duplicate_file_selection(qapp, tmp_path, service, monkeypatch):
    import appforge.ui.dialogs as module
    class Pool:
        def start(self, job):
            pass
    monkeypatch.setattr(module.QThreadPool, 'globalInstance', lambda: Pool())
    first = image(tmp_path / 'One.AppImage')
    known = image(tmp_path / 'Known.AppImage')
    service.add_application(str(known))
    dialog = AddApplicationDialog(service, initial_path=str(first))
    old_token = dialog._token
    dialog._set_path(str(known))
    dialog._on_inspected(old_token, inspect_file(first))
    assert dialog.metadata is None and dialog.repo_edit.text() == ''
    assert not dialog.add_btn.isEnabled()
    dialog.close()


def test_arbitrary_strings_outside_named_section_are_not_sources(tmp_path):
    path = image(tmp_path / 'Decoy.AppImage')
    path.write_bytes(path.read_bytes().replace(b'.upd_info\0', b'.not_info\0'))
    assert read_update_information(path, 2) is None
    assert SUGGESTED_SOURCE_KEY not in inspect_file(path).extra
