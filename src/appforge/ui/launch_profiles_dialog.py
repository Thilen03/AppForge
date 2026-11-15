"""Draft-based editor for Default and independent named launch profiles."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..core.envvars import ENV_KEY, env_of, format_env_text, parse_env_text
from ..core.launch_options import ARGUMENTS, DIRECTORY, TERMINAL, LAUNCH_KEYS, options_of, validate_launch_options
from ..core.launch_profiles import DEFAULT_PROFILE, MAX_PROFILES, profiles_of, validate_profiles
from ..core.library import LibraryError


class LaunchProfilesDialog(QDialog):
    def __init__(self, service, entry, parent=None):
        super().__init__(parent)
        self.service, self.app_id = service, entry.id
        self.setWindowTitle(f"Launch profiles — {entry.name}")
        self.resize(760, 580)
        self.drafts = [{'id': DEFAULT_PROFILE, 'name': 'Default', ENV_KEY: env_of(entry), **options_of(entry)},
                       *profiles_of(entry)]
        self._row = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        heading = QLabel("Launch profiles", objectName="title")
        root.addWidget(heading)
        hint = QLabel("Default uses the settings from Add/Edit and is used by tray and menu shortcuts. "
                      "New profiles start as copies of Default and can be changed independently.", objectName="hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        content = QHBoxLayout()
        left = QVBoxLayout()
        self.profile_list = QListWidget()
        self.profile_list.setAccessibleName("Launch profiles")
        self.profile_list.setMinimumWidth(150)
        self.profile_list.setMaximumWidth(210)
        left.addWidget(self.profile_list)
        self.new_btn = QPushButton("New profile")
        self.new_btn.clicked.connect(self._new)
        left.addWidget(self.new_btn)
        self.delete_btn = QPushButton("Delete profile")
        self.delete_btn.clicked.connect(self._delete)
        left.addWidget(self.delete_btn)
        content.addLayout(left)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Name", self.name_edit)
        self.arguments_edit = QLineEdit(placeholderText='--debug --profile "Test"')
        form.addRow("Arguments", self.arguments_edit)
        directory_row = QWidget()
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        self.directory_edit = QLineEdit(placeholderText="Default: the application's folder")
        directory_layout.addWidget(self.directory_edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        directory_layout.addWidget(browse)
        form.addRow("Working directory", directory_row)
        self.terminal_cb = QCheckBox("Run in terminal")
        form.addRow("", self.terminal_cb)
        self.env_edit = QPlainTextEdit()
        self.env_edit.setPlaceholderText("NAME=value\nOne environment variable per line")
        self.env_edit.setAccessibleName("Profile environment variables")
        form.addRow("Environment", self.env_edit)
        help_text = QLabel("Arguments and variables are passed literally, without a shell. "
                           "Blank arguments or environment mean none for this profile; "
                           "blank working directory uses the application's folder.", objectName="hint")
        help_text.setWordWrap(True)
        form.addRow(help_text)
        content.addLayout(form, 1)
        root.addLayout(content, 1)
        self.error_lbl = QLabel(objectName="error")
        self.error_lbl.setTextFormat(Qt.PlainText)
        self.error_lbl.setWordWrap(True)
        root.addWidget(self.error_lbl)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.save_btn = QPushButton("Save profiles", objectName="primary")
        self.save_btn.clicked.connect(self._save)
        buttons.addWidget(self.save_btn)
        root.addLayout(buttons)
        self.profile_list.currentRowChanged.connect(self._select)
        for profile in self.drafts:
            self.profile_list.addItem(profile['name'])
        self.profile_list.setCurrentRow(0)

    def _collect(self):
        if self._row < 0:
            return
        options = validate_launch_options({ARGUMENTS: self.arguments_edit.text(),
                                           DIRECTORY: self.directory_edit.text(),
                                           TERMINAL: self.terminal_cb.isChecked()})
        env = parse_env_text(self.env_edit.toPlainText())
        candidate = {'id': self.drafts[self._row]['id'], 'name': self.name_edit.text(),
                     ENV_KEY: env, **options}
        pending = deepcopy(self.drafts)
        pending[self._row] = candidate
        validate_profiles(pending[1:])
        self.drafts = pending
        self.profile_list.item(self._row).setText(candidate['name'])
        self.error_lbl.clear()

    def _select(self, row):
        try:
            self._collect()
        except ValueError as exc:
            self.error_lbl.setText(str(exc))
            self.profile_list.blockSignals(True)
            self.profile_list.setCurrentRow(self._row)
            self.profile_list.blockSignals(False)
            return
        self._load(row)

    def _load(self, row):
        self._row = row
        profile = self.drafts[row]
        self.name_edit.setText(profile['name'])
        self.name_edit.setEnabled(row != 0)
        self.delete_btn.setEnabled(row != 0)
        self.new_btn.setEnabled(len(self.drafts) <= MAX_PROFILES)
        self.arguments_edit.setText(profile.get(ARGUMENTS, ''))
        self.directory_edit.setText(profile.get(DIRECTORY, ''))
        self.terminal_cb.setChecked(profile.get(TERMINAL, False))
        self.env_edit.setPlainText(format_env_text(profile.get(ENV_KEY)))

    def _new(self):
        try:
            self._collect()
        except ValueError as exc:
            self.error_lbl.setText(str(exc))
            return
        if len(self.drafts) > MAX_PROFILES:
            return
        names = {p['name'].casefold() for p in self.drafts}
        number = 1
        while f'Profile {number}'.casefold() in names:
            number += 1
        profile = {**deepcopy(self.drafts[0]), 'id': uuid4().hex, 'name': f'Profile {number}'}
        self.drafts.append(profile)
        self.profile_list.addItem(profile['name'])
        self.profile_list.setCurrentRow(len(self.drafts) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _delete(self):
        if self._row <= 0:
            return
        row = self._row
        self.drafts.pop(row)
        self.profile_list.blockSignals(True)
        self.profile_list.takeItem(row)
        self.profile_list.setCurrentRow(min(row, len(self.drafts) - 1))
        self.profile_list.blockSignals(False)
        self.error_lbl.clear()
        self._load(self.profile_list.currentRow())

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Choose working directory", str(Path(self.directory_edit.text() or '~').expanduser()))
        if directory:
            self.directory_edit.setText(directory)

    def _save(self):
        try:
            self._collect()
            default = self.drafts[0]
            self.service.update_application(
                self.app_id, env_vars=default[ENV_KEY],
                launch_options={k: v for k, v in default.items() if k in LAUNCH_KEYS},
                launch_profiles=self.drafts[1:])
        except (ValueError, LibraryError) as exc:
            self.error_lbl.setText(str(exc))
            return
        self.accept()
