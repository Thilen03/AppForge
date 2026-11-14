"""Modeless, read-only Markdown release notes; network work never touches SQLite."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from ..core.updates.notes import cached_notes, fetch_notes, notes_identity


class NotesDocument(QTextDocument):
    def loadResource(self, resource_type, url):
        # Release text is untrusted. Do not read local files or fetch remote images.
        return None


def open_web_link(url):
    url = QUrl(url)
    if url.scheme().lower() in ("https", "http") and url.host() and not url.userInfo():
        QDesktopServices.openUrl(url)


class NotesSignals(QObject):
    done = Signal(object)


class NotesJob(QRunnable):
    def __init__(self, identity, client, token):
        super().__init__()
        self.identity, self.client, self.token = identity, client, token
        self.signals = NotesSignals()

    def run(self):
        try:
            result = fetch_notes(*self.identity, client=self.client, token=self.token)
        except Exception as exc:
            result = str(exc) or "Could not load release notes. Try refreshing."
        self.signals.done.emit(result)


class ReleaseNotesDialog(QDialog):
    def __init__(self, service, app_id, client=None, token=None, parent=None):
        super().__init__(parent)
        self.service, self.app_id, self.client, self.token = service, app_id, client, token
        self._closed = False
        self._job = None
        self._identity = None
        self._notes = None
        self._requested_identity = None
        self.resize(720, 620)
        self.setMinimumSize(440, 340)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        self.heading = QLabel(objectName="title")
        self.heading.setTextFormat(Qt.PlainText)
        self.heading.setWordWrap(True)
        root.addWidget(self.heading)
        self.metadata = QLabel()
        self.metadata.setTextFormat(Qt.PlainText)
        self.metadata.setWordWrap(True)
        root.addWidget(self.metadata)
        self.browser = QTextBrowser()
        self.browser.setDocument(NotesDocument(self.browser))
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(open_web_link)
        root.addWidget(self.browser, 1)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load)
        row.addWidget(self.refresh_btn)
        self.page_btn = QPushButton("Open release page")
        self.page_btn.clicked.connect(self.open_page)
        row.addWidget(self.page_btn)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)
        self.sync()

    def sync(self):
        if self._closed:
            return
        entry = self.service.get(self.app_id)
        if entry is None:
            self.close()
            return
        self.setWindowTitle(f"{entry.name} — Release notes")
        identity = notes_identity(entry)
        notes = cached_notes(entry)
        if identity != self._identity:
            self._identity = identity
            self._notes = None
            self.browser.clear()
            self.heading.setText(f"{entry.name} — {identity[1] or 'Release notes'}")
            self.metadata.clear()
            self.notice.setText("Check for updates first to select a release." if not all(identity) else "")
        if notes is not None and notes != self._notes:
            self.render(notes)
        info = entry.metadata.get("update") or {}
        self._url = (self._notes or {}).get("url") or info.get("release_url") or ""
        self.page_btn.setEnabled(QUrl(self._url).scheme() in ("https", "http"))
        self.refresh_btn.setEnabled(all(identity) and self._job is None)
        if (self._notes is None and all(identity) and self._job is None
                and identity != self._requested_identity):
            self.load()

    def render(self, notes):
        self._notes = notes
        self.heading.setText(notes.get("title") or notes["tag"])
        self.metadata.setText(f"{notes['tag']} · {'Prerelease' if notes.get('prerelease') else 'Stable release'}"
                              f" · Published: {notes.get('published_at') or 'Unknown'}")
        body = notes.get("body") or ""
        if body.strip():
            # Disable raw HTML while retaining Markdown headings, lists, code and links.
            self.browser.document().setMarkdown(body, QTextDocument.MarkdownDialectGitHub |
                                                QTextDocument.MarkdownNoHTML)
        else:
            self.browser.setPlainText("No release description is available for this version.")
        block = self.browser.document().begin()
        link_format = QTextCharFormat()
        link_format.setForeground(self.palette().link())
        while block.isValid():
            fragments = block.begin()
            while not fragments.atEnd():
                fragment = fragments.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    cursor = QTextCursor(self.browser.document())
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    cursor.mergeCharFormat(link_format)
                fragments += 1
            block = block.next()
        self.browser.moveCursor(QTextCursor.Start)
        self.browser.verticalScrollBar().setValue(0)
        self._url = notes.get("url") or ""
        self.page_btn.setEnabled(QUrl(self._url).scheme() in ("https", "http"))

    def load(self):
        if self._closed or self._job is not None or not all(self._identity):
            return
        identity = self._identity
        self._requested_identity = identity
        job = NotesJob(identity, self.client, self.token)
        self._job = job
        self.refresh_btn.setEnabled(False)
        self.notice.setText("Loading release notes…")
        job.signals.done.connect(self._loaded)
        QThreadPool.globalInstance().start(job)

    def _loaded(self, result):
        job, self._job = self._job, None
        if self._closed:
            return
        entry = self.service.get(self.app_id)
        if entry is None:
            self.close()
            return
        if notes_identity(entry) != job.identity:
            self.sync()
            return
        self.refresh_btn.setEnabled(True)
        if isinstance(result, str):
            self.notice.setText(f"Could not refresh release notes: {result}" +
                                (" Showing cached notes." if self._notes else ""))
            return
        entry.metadata.setdefault("update", {})["notes"] = result
        self.service.db.update(entry)  # Qt main thread only; no change to install/update state
        self.render(result)
        self.notice.clear()

    def open_page(self):
        open_web_link(self._url)

    def done(self, result):
        self._closed = True
        super().done(result)
