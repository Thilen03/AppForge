"""Explicit, opt-in changes for applications with mixed update preferences."""
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from ..core.bulk import UpdatePreferences
from .popups import RoundedComboBox


class BulkUpdateDialog(QDialog):
    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update settings")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        message = QLabel(f"Change update settings for {count} selected applications.\n"
                         "Unchanged settings keep each application's current value.")
        message.setWordWrap(True)
        layout.addWidget(message)
        form = QFormLayout()
        self.paused = RoundedComboBox()
        for label, value in (("Leave unchanged", None), ("Pause updates", True),
                             ("Resume updates", False)):
            self.paused.addItem(label, value)
        form.addRow("Update checks", self.paused)
        self.prereleases = RoundedComboBox()
        for label, value in (("Leave unchanged", None), ("Stable releases only", False),
                             ("Include pre-releases / nightlies", True)):
            self.prereleases.addItem(label, value)
        form.addRow("Release channel", self.prereleases)
        layout.addLayout(form)
        self.change_pattern = QCheckBox("Change release asset pattern")
        layout.addWidget(self.change_pattern)
        self.pattern = QLineEdit(placeholderText="Blank = automatic matching; e.g. *x86_64.AppImage")
        self.pattern.setAccessibleName("Release asset pattern")
        self.pattern.setEnabled(False)
        self.change_pattern.toggled.connect(self.pattern.setEnabled)
        layout.addWidget(self.pattern)
        self.clear_skipped = QCheckBox("Clear skipped versions")
        layout.addWidget(self.clear_skipped)
        hint = QLabel("Repository sources are preserved. Channel or asset changes clear cached "
                      "update results. Use Check for updates afterward to find matching releases.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for combo in (self.paused, self.prereleases):
            combo.currentIndexChanged.connect(self._changed)
        self.change_pattern.toggled.connect(self._changed)
        self.clear_skipped.toggled.connect(self._changed)
        self._changed()

    def _changed(self):
        self.buttons.button(QDialogButtonBox.Apply).setEnabled(
            self.preferences() != UpdatePreferences())

    def preferences(self) -> UpdatePreferences:
        return UpdatePreferences(
            paused=self.paused.currentData(),
            include_prereleases=self.prereleases.currentData(),
            asset_pattern=self.pattern.text() if self.change_pattern.isChecked() else None,
            clear_skipped=self.clear_skipped.isChecked(),
        )
