"""Edit launch preferences locally; the parent Add/Edit dialog commits them."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from ..core.launch_options import ARGUMENTS, DIRECTORY, TERMINAL, LaunchOptionsError, validate_launch_options


class LaunchOptionsDialog(QDialog):
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Launch options")
        self.options = dict(options)
        self.resize(580, 430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Launch options", objectName="title"))
        hint = QLabel("Used by TuxShelf, the tray and desktop-menu launchers. "
                      "Applied when you save the application.", objectName="hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Command-line arguments (optional)", objectName="sectionLabel"))
        self.arguments_edit = QLineEdit()
        self.arguments_edit.setPlaceholderText('--profile "Work profile" --verbose')
        self.arguments_edit.setText(options.get(ARGUMENTS, ""))
        layout.addWidget(self.arguments_edit)
        hint = QLabel("Separate arguments with spaces; quote values containing spaces. "
                      "Arguments are passed literally: no shell commands, variable or wildcard expansion.",
                      objectName="hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Working directory (optional)", objectName="sectionLabel"))
        row = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("Default: the application's folder")
        self.directory_edit.setText(options.get(DIRECTORY, ""))
        row.addWidget(self.directory_edit, 1)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)
        layout.addLayout(row)
        self.directory_hint = QLabel(objectName="hint")
        self.directory_hint.setTextFormat(Qt.PlainText)
        self.directory_hint.setWordWrap(True)
        layout.addWidget(self.directory_hint)
        self.terminal_cb = QCheckBox("Run in terminal")
        self.terminal_cb.setChecked(options.get(TERMINAL, False))
        layout.addWidget(self.terminal_cb)
        hint = QLabel("Useful for interactive scripts and command-line tools. Uses your desktop's "
                      "terminal helper when available, with fallbacks including Konsole. "
                      "The terminal controls whether it stays open after the app exits.", objectName="hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error_lbl = QLabel(objectName="error")
        self.error_lbl.setWordWrap(True)
        layout.addWidget(self.error_lbl)
        layout.addStretch(1)
        buttons = QHBoxLayout()
        defaults = QPushButton("Reset to defaults")
        defaults.clicked.connect(self._defaults)
        buttons.addWidget(defaults)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.use_btn = QPushButton("Use options", objectName="primary")
        self.use_btn.setDefault(True)
        self.use_btn.clicked.connect(self._accept)
        buttons.addWidget(self.use_btn)
        layout.addLayout(buttons)
        self.arguments_edit.textChanged.connect(self._validate)
        self.directory_edit.textChanged.connect(self._validate)
        self.terminal_cb.toggled.connect(self._validate)
        self._validate()

    def _values(self):
        return validate_launch_options({ARGUMENTS: self.arguments_edit.text(),
                                        DIRECTORY: self.directory_edit.text(),
                                        TERMINAL: self.terminal_cb.isChecked()})

    def _validate(self):
        try:
            options = self._values()
        except LaunchOptionsError as exc:
            self.error_lbl.setText(str(exc))
            self.use_btn.setEnabled(False)
            self.directory_hint.clear()
            return
        self.error_lbl.clear()
        self.use_btn.setEnabled(True)
        directory = options.get(DIRECTORY)
        try:
            available = not directory or Path(directory).is_dir()
        except OSError:
            available = False
        self.directory_hint.setText("This folder is missing or inaccessible. Choose an existing folder before launching."
                                    if not available else
                                    "Leave blank to use the application's folder. You can also use ~/folder.")

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Choose working directory", str(Path(self.directory_edit.text() or "~").expanduser()))
        if directory:
            self.directory_edit.setText(directory)

    def _defaults(self):
        self.arguments_edit.clear()
        self.directory_edit.clear()
        self.terminal_cb.setChecked(False)

    def _accept(self):
        try:
            self.options = self._values()
        except LaunchOptionsError:
            self._validate()
            return
        self.accept()
