"""Honest source-detection outcomes and conservative AppStream fallbacks."""
import pytest

from test_gui import qapp  # noqa: F401
from test_discovery import wait
from test_appimage_sources import INFO, SOURCE, image
from appforge.core.formats import AppMetadata
from appforge.core.formats.appimage import AppImageFormat, _parse_metainfo
from appforge.core.formats.appimage_update import (
    SOURCE_ORIGIN_KEY, SUGGESTED_SOURCE_KEY, repository_metadata_url, source_detection_message,
)
from appforge.core.discovery import scan
from appforge.ui.dialogs import AddApplicationDialog
from appforge.ui.discovery_dialog import DiscoveryDialog


@pytest.mark.parametrize('value,explicit,expected', [
    ('https://github.com/patchzyy/Wiicompiled', False, 'https://github.com/patchzyy/Wiicompiled'),
    ('https://github.com/patchzyy/Wiicompiled.git/', True, 'https://github.com/patchzyy/Wiicompiled'),
    ('https://gitlab.com/group/sub/project', True, 'https://gitlab.com/group/sub/project'),
    ('https://git.example.org/group/sub/project', True, 'https://git.example.org/group/sub/project'),
    ('https://git.example.org/group/sub/project', False, None),
    ('https://example.org/my-app', False, None),
    ('https://github.com/o/r/issues', False, None),
    ('https://github.com/o/r/blob/main/README.md', True, None),
    ('https://github.com/o', False, None),
    ('http://github.com/o/r', True, None),
    ('https://user:password@github.com/o/r', True, None),
    ('https://github.com/o/r?token=private', True, None),
    ('https://github.com:bad/o/r', True, None),
    ('https://[malformed/o/r', True, None),
])
def test_metadata_url_roots_only(value, explicit, expected):
    assert repository_metadata_url(value, explicit_vcs=explicit) == expected


def test_namespaced_appstream_vcs_and_precedence():
    parsed = _parse_metainfo(b'''<component xmlns="https://specifications.freedesktop.org/metainfo/1.0">
      <id>org.example.App</id><name>Example</name><summary>Summary</summary>
      <url type="homepage">https://github.com/other/homepage</url>
      <url type="vcs-browser">https://github.com/ExampleOrg/ExampleApp</url>
      <releases><release version="2.0" date="2026-01-01" /></releases>
    </component>''')
    assert parsed['name'] == 'Example' and parsed['version'] == '2.0'
    assert parsed[SUGGESTED_SOURCE_KEY] == SOURCE
    assert parsed[SOURCE_ORIGIN_KEY] == 'appstream_vcs'


def test_generic_homepage_bugtracker_and_ambiguous_repositories_not_guessed():
    for urls in (
        '<url type="homepage">https://example.org/apps/example</url>',
        '<url type="bugtracker">https://github.com/o/r/issues</url>',
        '<url type="vcs-browser">https://github.com/o/r</url>'
        '<url type="vcs-browser">https://github.com/other/repo</url>',
    ):
        parsed = _parse_metainfo(f'<component><name>Example</name>{urls}</component>'.encode())
        assert SUGGESTED_SOURCE_KEY not in parsed


def test_fallback_component_match_and_primary_update_info_wins(monkeypatch):
    reader = AppImageFormat()
    monkeypatch.setattr(reader, '_read_desktop', lambda im: {'Name': 'Example'})
    monkeypatch.setattr(reader, '_read_metainfo', lambda im: {
        'name': 'Example', SUGGESTED_SOURCE_KEY: SOURCE, SOURCE_ORIGIN_KEY: 'appstream_vcs'})
    monkeypatch.setattr(reader, '_find_icon', lambda *a: None)
    metadata = AppMetadata('appimage', 'Filename')
    reader._fill_from_image(None, metadata)
    assert metadata.extra[SUGGESTED_SOURCE_KEY] == SOURCE
    assert 'AppStream repository metadata' in source_detection_message(metadata)
    primary = AppMetadata('appimage', 'Filename', extra={
        SUGGESTED_SOURCE_KEY: 'https://github.com/primary/update', SOURCE_ORIGIN_KEY: 'update_info'})
    reader._fill_from_image(None, primary)
    assert primary.extra[SUGGESTED_SOURCE_KEY] == 'https://github.com/primary/update'
    monkeypatch.setattr(reader, '_read_desktop', lambda im: {'Name': 'Different app'})
    unrelated = AppMetadata('appimage', 'Filename')
    reader._fill_from_image(None, unrelated)
    assert SUGGESTED_SOURCE_KEY not in unrelated.extra


def test_no_source_message_in_add_and_discovery(qapp, tmp_path, service):
    # Same reported filename, deliberately constructed without update data.
    # This verifies the no-metadata case, not the contents of the user's file.
    path = image(tmp_path / 'WiiCompiled-Setup-x86_64.appimage', '')
    dialog = AddApplicationDialog(service, initial_path=str(path))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == ''
    assert 'No automatic update source found' in dialog.repo_msg.text()
    assert 'Enter a repository URL manually' in dialog.repo_msg.text()
    dialog.repo_edit.setText('https://github.com/patchzyy/Wiicompiled')
    assert 'No automatic update source found' not in dialog.repo_msg.text()
    dialog.close()
    preview = DiscoveryDialog(service, preview=scan([str(tmp_path)]))
    editor = preview.table.cellWidget(0, 5)
    assert editor.placeholderText() == 'No source detected'
    assert 'No automatic update source found' in editor.toolTip()
    preview.close()


def test_clear_suggestion_does_not_claim_detection_failed(qapp, tmp_path, service):
    path = image(tmp_path / 'Example.AppImage', INFO)
    dialog = AddApplicationDialog(service, initial_path=str(path))
    wait(qapp, lambda: dialog.metadata is not None)
    assert dialog.repo_edit.text() == SOURCE
    dialog.repo_edit.clear()
    dialog.repo_edit.textEdited.emit('')
    assert 'left empty' in dialog.repo_msg.text()
    assert 'No automatic update source found' not in dialog.repo_msg.text()
    dialog.close()


def test_real_appstream_only_image_has_suggestion(fixtures, tmp_path):
    import make_fixtures
    import subprocess
    from appforge.core.library import inspect_file
    build = make_fixtures.subprocess.run
    def inject_metainfo(command, **kwargs):
        appdir = tmp_path / 'fallback.AppDir'
        folder = appdir / 'usr/share/metainfo'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'org.example.Fallback.metainfo.xml').write_text('''
        <component xmlns="https://specifications.freedesktop.org/metainfo/1.0">
          <id>fallback</id><name>Fallback App</name>
          <url type="vcs-browser">https://github.com/ExampleOrg/ExampleApp</url>
        </component>''')
        return build(command, **kwargs)
    # Install a temporary wrapper without leaving the global subprocess module changed.
    from unittest.mock import patch
    with patch.object(subprocess, 'run', inject_metainfo):
        path = make_fixtures.build(tmp_path, 'fallback', 'Fallback App', '1.0', '#123456')
    metadata = inspect_file(path)
    assert metadata.extra[SUGGESTED_SOURCE_KEY] == SOURCE
    assert metadata.extra[SOURCE_ORIGIN_KEY] == 'appstream_vcs'
