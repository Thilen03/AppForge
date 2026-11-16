"""One desktop-category dropdown drives launchers and library organization."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QLabel

from tuxshelf.core.database import Database
from tuxshelf.core.desktop import MENU_CATEGORIES, menu_category_of, render_entry
from tuxshelf.core.library import LibraryService
from tuxshelf.core.library_transfer import export_library, read_export, preview_import, prepare_import
from tuxshelf.core.models import AppEntry
from tuxshelf.core.organize import category_of, categories_in_use, matches, Filter
from tuxshelf.ui.dialogs import AddApplicationDialog, EditApplicationDialog
from tuxshelf.ui.main_window import MainWindow
from test_gui import qapp, wait_for  # noqa: F401


def app(service, tmp_path, metadata=None):
    path = tmp_path / 'Example-1.0.sh'
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    entry = service.add_application(str(path), integrate_desktop=True)
    entry.metadata.update(metadata or {})
    service.db.update(entry)
    return service.get(entry.id)


@pytest.mark.parametrize('key,label', MENU_CATEGORIES)
def test_shared_category_drives_launcher_filter_and_search(key, label):
    entry = AppEntry(name='Example', path='/opt/example', format='executable',
                     metadata={'menu_category': key, 'category': 'Old custom', 'categories': 'Utility;Qt;'})
    assert category_of(entry) == label
    assert categories_in_use([entry]) == [label]
    assert matches(entry, Filter(category=label))
    assert matches(entry, Filter(query=label))
    assert not matches(entry, Filter(category='Old custom'))
    assert f'Categories={key};Qt;' in render_entry(entry)


def test_popup_selection_saves_one_category_and_updates_library(qapp, service, tmp_path):
    entry = app(service, tmp_path, {'category': 'Old custom', 'menu_category': 'Office'})
    dlg = EditApplicationDialog(service, entry)
    window = MainWindow(service)
    try:
        assert dlg.findChildren(QComboBox) == [dlg.menu_category_cb]
        labels = [label.text() for label in dlg.findChildren(QLabel)]
        assert labels.count('Category') == 1 and 'Application menu category' not in labels
        combo = dlg.menu_category_cb
        assert not combo.isEditable() and combo.currentData() == 'Office'
        assert [(combo.itemData(i), combo.itemText(i)) for i in range(1, combo.count())] == list(MENU_CATEGORIES)
        dlg.show()
        qapp.processEvents()
        combo.showPopup()
        view = combo.view()
        index = combo.model().index(combo.findData('Game'), 0)
        view.scrollTo(index)
        qapp.processEvents()
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
        assert combo.currentData() == 'Game'
        dlg.save_btn.click()
        saved = service.get(entry.id)
        assert saved.metadata['menu_category'] == 'Game' and 'category' not in saved.metadata
        assert category_of(saved) == 'Games'
        assert 'Categories=Game;' in service.desktop.entry_path(saved.id).read_text()
        window.reload()
        category_index = window.category_cb.findData('Games')
        assert category_index > 0
        window.category_cb.setCurrentIndex(category_index)
        assert not window._card(entry.id).isHidden()
        with_db = Database(service.db.path)
        try:
            reopened = with_db.get(entry.id)
            assert category_of(reopened) == 'Games' and reopened.metadata['menu_category'] == 'Game'
        finally:
            with_db.close()
    finally:
        dlg.close()
        window._quitting = True
        window.close()
        dlg.deleteLater()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize('legacy,key,label', [('Games', 'Game', 'Games'),
                                              ('Internet', 'Network', 'Internet'),
                                              ('Science', 'Science', 'Science & Math')])
def test_standard_legacy_category_becomes_shared_on_save(qapp, service, tmp_path, legacy, key, label):
    entry = app(service, tmp_path, {'category': legacy})
    assert menu_category_of(entry) == key and category_of(entry) == label
    assert f'Categories={key};' in render_entry(entry)
    dlg = EditApplicationDialog(service, entry)
    try:
        assert dlg.menu_category_cb.currentData() == key
        dlg._save()
        assert service.get(entry.id).metadata['menu_category'] == key
        assert 'category' not in service.get(entry.id).metadata
    finally:
        dlg.close()


def test_custom_legacy_category_preserved_until_explicit_choice(qapp, service, tmp_path):
    entry = app(service, tmp_path, {'category': 'My Work'})
    dlg = EditApplicationDialog(service, entry)
    try:
        assert dlg.menu_category_cb.currentData() is None
        dlg.name_edit.setText('Renamed')
        dlg._save()
        saved = service.get(entry.id)
        assert saved.metadata['category'] == 'My Work' and category_of(saved) == 'My Work'
    finally:
        dlg.close()
    # Explicitly selecting Automatic also replaces a custom category, even
    # when the dropdown was already showing Automatic.
    dlg = EditApplicationDialog(service, saved)
    try:
        dlg.menu_category_cb.activated.emit(0)
        dlg._save()
        assert 'category' not in service.get(entry.id).metadata
        assert 'menu_category' not in service.get(entry.id).metadata
    finally:
        dlg.close()


def test_reset_to_automatic_and_cancel_preserve_expected_metadata(qapp, service, tmp_path):
    entry = app(service, tmp_path, {'menu_category': 'Game', 'category': 'Old', 'categories': 'Graphics;Qt;'})
    dlg = EditApplicationDialog(service, entry)
    dlg.menu_category_cb.setCurrentIndex(dlg.menu_category_cb.findData('Office'))
    dlg.reject()
    assert service.get(entry.id).metadata == entry.metadata
    dlg = EditApplicationDialog(service, entry)
    try:
        dlg.menu_category_cb.setCurrentIndex(0)
        dlg._save()
        saved = service.get(entry.id)
        assert 'category' not in saved.metadata and 'menu_category' not in saved.metadata
        assert category_of(saved) == 'Graphics'
        assert 'Categories=Graphics;Qt;' in service.desktop.entry_path(entry.id).read_text()
    finally:
        dlg.close()


def test_add_category_applies_without_menu_and_survives_transfer(qapp, service, tmp_path):
    path = tmp_path / 'New-1.0.sh'
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    dlg = AddApplicationDialog(service, None, str(path))
    imported_db = None
    try:
        assert wait_for(qapp, lambda: dlg.metadata is not None)
        dlg.menu_cb.setChecked(False)
        dlg.menu_category_cb.setCurrentIndex(dlg.menu_category_cb.findData('Network'))
        dlg._accept()
        saved = service.get(dlg.added.id)
        assert category_of(saved) == 'Internet'
        assert not service.desktop.entry_path(saved.id).exists()
        destination = tmp_path / 'export.json'
        export_library([saved], destination)
        imported_db = Database(tmp_path / 'imported.db')
        target = LibraryService(imported_db, service.icons_dir)
        candidate = preview_import(read_export(destination), [])[0]
        imported = target.import_configuration(prepare_import(candidate, [], target.icons_dir))
        assert imported.metadata['menu_category'] == 'Network' and category_of(imported) == 'Internet'
        imported = target.set_desktop_integration(imported.id, True)
        assert 'Categories=Network;' in target.desktop.entry_path(imported.id).read_text()
    finally:
        dlg.close()
        if imported_db:
            imported_db.close()


@pytest.mark.parametrize('raw,label', [('Utility;Development;', 'Development'),
                                      ('Game;Graphics;', 'Graphics'),
                                      ('Audio;Game;', 'Multimedia'),
                                      ('Emulator;', 'Games'),
                                      ('Science;', 'Science & Math'),
                                      ('Settings;', 'Settings')])
def test_automatic_category_uses_shared_labels_with_existing_priority(raw, label):
    entry = AppEntry(name='Example', path='/opt/example', metadata={'categories': raw})
    assert category_of(entry) == label


@pytest.mark.parametrize('invalid', ['Bogus', [], {}])
def test_invalid_desktop_category_does_not_break_library(invalid):
    entry = AppEntry(name='Example', path='/opt/example',
                     metadata={'menu_category': invalid, 'categories': 'Graphics;'})
    assert category_of(entry) == 'Graphics'
    assert 'Categories=Graphics;' in render_entry(entry)
