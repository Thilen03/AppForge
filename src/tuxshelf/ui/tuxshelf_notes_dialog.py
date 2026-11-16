"""Offline notes for the running TuxShelf version, bundled as package data."""
from importlib.resources import files

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from .. import __version__
from .release_notes_dialog import NotesDocument, open_web_link


class TuxShelfNotesDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"What's new in TuxShelf {__version__}")
        self.resize(660, 520)
        self.setMinimumSize(400, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        self.browser = QTextBrowser()
        self.browser.setDocument(NotesDocument(self.browser))
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(open_web_link)
        try:
            notes = files("tuxshelf").joinpath("resources/release_notes.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            notes = f"# TuxShelf {__version__}\n\nRelease notes are unavailable in this installation."
        self.browser.setMarkdown(notes)
        layout.addWidget(self.browser, 1)
        self.hide_notes_cb = QCheckBox("Don't show again")
        self.hide_notes_cb.setChecked(settings.hide_release_notes)
        self.hide_notes_cb.toggled.connect(lambda checked: setattr(settings, "hide_release_notes", checked))
        layout.addWidget(self.hide_notes_cb)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close", objectName="primary")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
