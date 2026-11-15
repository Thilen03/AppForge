"""Add / Edit application dialogs."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.desktop import MENU_CATEGORIES, menu_category_of
from ..core.envvars import ENV_KEY, EnvVarError, clean_env, format_env_text, parse_env_text
from ..core.formats import AppMetadata, get_format
from ..core.formats.appimage_update import metadata_source, source_detection_message
from ..core.library import (
    LibraryError, LibraryService, inspect_file, normalize_path, normalize_repo,
)
from ..core.models import AppEntry
from ..core.launch_options import LAUNCH_KEYS
from .launch_options_dialog import LaunchOptionsDialog
from .icons import app_pixmap, placeholder_pixmap
from .popups import RoundedComboBox

FILE_FILTER = "AppImage (*.AppImage *.appimage);;All files (*)"   # programs and scripts: pick "All files"
SOURCE_HINT = "Repository URL (GitHub, GitLab, Codeberg or a self-hosted Forgejo/Gitea/GitLab), used for update checks."
ICON_FILTER = "Images (*.png *.svg *.jpg *.jpeg *.webp *.bmp *.ico *.xpm);;All files (*)"


class _InspectSignals(QObject):
    done = Signal(int, object)   # token, AppMetadata | str(error)


class _InspectJob(QRunnable):
    def __init__(self, token: int, path: str):
        super().__init__()
        self.token, self.path, self.signals = token, path, _InspectSignals()

    def run(self):
        try:
            result: object = inspect_file(self.path)
        except LibraryError as exc:
            result = str(exc)
        except Exception as exc:  # noqa: BLE001
            result = f"Could not read this file: {exc}"
        self.signals.done.emit(self.token, result)


def _set_invalid(edit: QLineEdit, invalid: bool):
    edit.setProperty("invalid", invalid)
    edit.style().unpolish(edit)
    edit.style().polish(edit)


def _field_label(text: str) -> QLabel:
    return QLabel(text, objectName="sectionLabel")


ENV_HINT = "One per line, NAME=value. Used in the menu launcher and when you press Launch."
ENV_PLACEHOLDER = "QT_QPA_PLATFORM=xcb\nDRI_PRIME=1"


def _menu_category_combo(current: str | None) -> RoundedComboBox:
    """Automatic plus the standard desktop categories (item data = desktop key)."""
    combo = RoundedComboBox()
    combo.addItem("Automatic (from the application)", None)
    for key, label in MENU_CATEGORIES:
        combo.addItem(label, key)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.setToolTip("Used in AppForge and the KDE application launcher (and other desktop menus).")
    return combo


def _env_edit(text: str = "") -> QPlainTextEdit:
    edit = QPlainTextEdit()
    edit.setPlaceholderText(ENV_PLACEHOLDER)
    edit.setPlainText(text)
    edit.setFixedHeight(64)
    edit.setTabChangesFocus(True)
    edit.setToolTip(ENV_HINT)
    return edit


def _env_error(edit: QPlainTextEdit) -> str | None:
    try:
        parse_env_text(edit.toPlainText())
        return None
    except EnvVarError as exc:
        return str(exc)


def _scrolling_body(dialog):
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content = QWidget()
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    return outer, QVBoxLayout(content)


def _launch_options_row(dialog, layout):
    row = QHBoxLayout()
    row.addWidget(_field_label("Environment variables (optional)"), 1)
    dialog.launch_options_btn = QPushButton("Launch options…")
    dialog.launch_options_btn.setToolTip("Command-line arguments, working directory and Run in terminal")
    def edit_options():
        editor = LaunchOptionsDialog(dialog._launch_options, dialog)
        if editor.exec() == QDialog.Accepted:
            dialog._launch_options = editor.options
    dialog.launch_options_btn.clicked.connect(edit_options)
    row.addWidget(dialog.launch_options_btn)
    layout.addLayout(row)


class AddApplicationDialog(QDialog):
    def __init__(self, service: LibraryService, parent=None, initial_path: str | None = None, *, downloaded=None):
        super().__init__(parent)
        self.service = service
        self.downloaded = downloaded
        self.setWindowTitle("Add application")
        self.resize(560, min(770, self.screen().availableGeometry().height() - 80))
        self.setMinimumSize(520, 420)
        self._launch_options = {}
        self.metadata: AppMetadata | None = None
        self.added: AppEntry | None = None
        self.menu_requested = False   # whether the "application menu" box was ticked on accept
        self._token = 0
        self._jobs: list[_InspectJob] = []
        self._name_touched = False
        self._repo_touched = False
        self._auto_repo = None
        self._custom_icon: str | None = None
        self._build()
        if downloaded:
            self.repo_edit.setText(downloaded.choice.source)
        if initial_path:
            self._set_path(initial_path)

    def _build(self):
        outer, lay = _scrolling_body(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Add application", objectName="title"))
        subtitle = QLabel(
            ("Download complete. Review the details and add it to your library. "
             f"Checksum: {self.downloaded.checksum}. The file is kept if you cancel.") if self.downloaded else
            "Pick an AppImage (or a Linux program or script) anywhere on your computer. It stays where it is.",
            objectName="subtitle")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)
        lay.addSpacing(8)

        lay.addWidget(_field_label("File"))
        row = QHBoxLayout()
        self.path_edit = QLineEdit(placeholderText="Choose an AppImage, program or script…")
        self.path_edit.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        self.file_msg = QLabel(objectName="error")
        self.file_msg.setWordWrap(True)
        self.file_msg.hide()
        lay.addWidget(self.file_msg)

        self.details = QWidget()
        d = QHBoxLayout(self.details)
        d.setContentsMargins(0, 10, 0, 0)
        d.setSpacing(18)
        self.icon_lbl = QLabel(objectName="previewTile")
        self.icon_lbl.setFixedSize(104, 104)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        icon_col = QVBoxLayout()
        icon_col.setSpacing(6)
        icon_col.addWidget(self.icon_lbl, 0, Qt.AlignTop)
        self.icon_btn = QPushButton("Change icon…")
        self.icon_btn.setToolTip("Use your own image instead of the AppImage's icon")
        self.icon_btn.clicked.connect(self._choose_icon)
        self.icon_reset_btn = QPushButton("Use default")
        self.icon_reset_btn.clicked.connect(self._reset_icon_choice)
        self.icon_reset_btn.hide()
        icon_col.addWidget(self.icon_btn)
        icon_col.addWidget(self.icon_reset_btn)
        icon_col.addStretch(1)
        d.addLayout(icon_col)
        form = QVBoxLayout()
        form.setSpacing(6)
        form.addWidget(_field_label("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.textEdited.connect(self._on_name_edited)
        self.name_edit.textChanged.connect(self._validate)
        self.name_edit.textChanged.connect(self._refresh_placeholder_icon)
        form.addWidget(self.name_edit)
        self.meta_lbl = QLabel(objectName="hint")
        self.meta_lbl.setWordWrap(True)
        form.addWidget(self.meta_lbl)
        self.warn_lbl = QLabel(objectName="warning")
        self.warn_lbl.setWordWrap(True)
        form.addWidget(self.warn_lbl)
        form.addStretch(1)
        d.addLayout(form, 1)
        lay.addWidget(self.details)
        self._reset_details()

        lay.addSpacing(4)
        lay.addWidget(_field_label("Update source (optional)"))
        self.repo_edit = QLineEdit(placeholderText="https://github.com/owner/repo  or  https://git.example.dev/owner/repo")
        self.repo_edit.textChanged.connect(self._validate)
        self.repo_edit.textEdited.connect(self._on_repo_edited)
        lay.addWidget(self.repo_edit)
        self.repo_msg = QLabel(SOURCE_HINT, objectName="hint")
        self.repo_msg.setWordWrap(True)
        lay.addWidget(self.repo_msg)
        self.menu_cb = QCheckBox("Add to the application menu")
        self.menu_cb.setToolTip("Creates a launcher in your desktop's application menu so you can start "
                                "the app without opening AppForge. The AppImage itself is not touched.")
        self.menu_cb.setChecked(self.service.desktop_default())
        lay.addWidget(self.menu_cb)

        lay.addWidget(_field_label("Category"))
        self.menu_category_cb = _menu_category_combo(None)
        lay.addWidget(self.menu_category_cb)

        _launch_options_row(self, lay)
        self.env_edit = _env_edit()
        self.env_edit.textChanged.connect(self._validate)
        lay.addWidget(self.env_edit)
        self.env_msg = QLabel(ENV_HINT, objectName="hint")
        self.env_msg.setWordWrap(True)
        lay.addWidget(self.env_msg)

        lay.addStretch(1)
        # Keep the attempt/result visible even when optional form fields are scrolled.
        report = QHBoxLayout()
        report.setContentsMargins(24, 4, 24, 0)
        self.source_panel = QFrame(objectName="sourceDetection")
        panel = QVBoxLayout(self.source_panel)
        panel.setContentsMargins(12, 10, 12, 10)
        panel.setSpacing(4)
        panel.addWidget(QLabel("Automatic update-source detection", objectName="sectionLabel"))
        self.source_status_lbl = QLabel("Select a file to start.")
        self.source_status_lbl.setWordWrap(True)
        self.source_status_lbl.setTextFormat(Qt.PlainText)
        panel.addWidget(self.source_status_lbl)
        self.source_progress = QProgressBar(textVisible=False)
        self.source_progress.setRange(0, 0)
        self.source_progress.hide()
        panel.addWidget(self.source_progress)
        self._source_state = "waiting"
        report.addWidget(self.source_panel)
        outer.addLayout(report)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.add_btn = QPushButton("Add to library", objectName="primary")
        self.add_btn.setEnabled(False)
        self.add_btn.setDefault(True)
        self.add_btn.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(self.add_btn)
        btns.setContentsMargins(24, 8, 24, 20)
        outer.addLayout(btns)

    # -- file selection -----------------------------------------------------------------
    def _browse(self):
        start = str(Path(self.path_edit.text()).parent) if self.path_edit.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose an application", start, FILE_FILTER)
        if path:
            self._set_path(path)

    def _set_path(self, path: str):
        path = normalize_path(path)
        self._token += 1
        if not self._repo_touched and self.repo_edit.text() == self._auto_repo:
            self.repo_edit.clear()
        self._auto_repo = None
        self._set_source_state("waiting", "Select a file to start.")
        self.path_edit.setText(path)
        self.path_edit.setToolTip(path)
        self.metadata = None
        self._custom_icon = None
        self._reset_details()
        self._show_file_msg("")
        self._validate()
        if self.service.find_by_path(path):
            self._set_source_state("not_checked", "Not checked: this application is already in your library.")
            self._show_file_msg("This application is already in your library.")
            return
        self.meta_lbl.setText("Reading file…")
        self._set_source_state("checking", "Checking this file for an update source…")
        job = _InspectJob(self._token, path)
        job.signals.done.connect(self._on_inspected)
        self._jobs.append(job)  # keep Python wrapper alive until finished
        QThreadPool.globalInstance().start(job)

    def _on_inspected(self, token: int, result):
        self._jobs = [j for j in self._jobs if j.token != token]
        if token != self._token:
            return  # a newer selection superseded this one
        if isinstance(result, str):
            self._set_source_state("failed", f"Source detection failed: {result}")
            self._reset_details()
            self._show_file_msg(result)
            return
        md: AppMetadata = result
        if self.downloaded and self.path_edit.text() == self.downloaded.path:
            from ..core.downloads import validate_downloaded
            try:
                validate_downloaded(self.downloaded)
            except LibraryError as exc:
                self._set_source_state("failed", f"Source detection failed: {exc}")
                self._show_file_msg(str(exc))
                return
            from ..core.updates.version import parse_version
            release_version = self.downloaded.choice.version
            version = release_version if parse_version(release_version) is not None else md.version or release_version
            md = replace(md, version=version,
                         extra={**md.extra, "installed_version_source": "github_release"})
        self.metadata = md
        suggested = metadata_source(md)
        if suggested and not self._repo_touched and not self.repo_edit.text().strip():
            self._auto_repo = suggested
            self.repo_edit.setText(suggested)
        if suggested:
            kept = (" Your existing source choice has been kept."
                    if self.repo_edit.text() != suggested else " Review the source before adding.")
            self._set_source_state("found", f"Update source found: {suggested}" + kept)
        elif md.format_id == "appimage":
            self._set_source_state("not_found", source_detection_message(md))
        else:
            self._set_source_state("not_applicable",
                                   "Automatic source detection is available for AppImages. "
                                   "You can enter a repository URL manually for this file.")
        self.name_edit.setEnabled(True)
        self.icon_btn.setEnabled(True)
        if not self._name_touched or not self.name_edit.text():
            self.name_edit.setText(md.name_suggestion)
        fmt = get_format(md.format_id)
        bits = [fmt.display_name if fmt else md.format_id,
                f"version {md.version}" if md.version else "version unknown"]
        text = " · ".join(bits)
        if md.description:
            text += f"\n{md.description}"
        self.meta_lbl.setText(text)
        self.warn_lbl.setText("\n".join(md.warnings))
        self.warn_lbl.setVisible(bool(md.warnings))
        self._render_icon()
        self._validate()

    def _set_source_state(self, state: str, message: str):
        self._source_state = state
        self.source_status_lbl.setText(message if len(message) <= 240 else message[:237] + "…")
        self.source_status_lbl.setToolTip(message)
        self.source_status_lbl.setAccessibleName(message)
        self.source_progress.setVisible(state == "checking")

    def _choose_icon(self):
        start = str(Path(self._custom_icon).parent) if self._custom_icon else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose an icon", start, ICON_FILTER)
        if not path:
            return
        if QPixmap(path).isNull() and not path.lower().endswith(".svg"):
            self._show_file_msg("That image couldn't be read. Try a PNG or SVG.")
            return
        self._custom_icon = path
        self._show_file_msg("" if self.metadata else self.file_msg.text())
        self._render_icon()

    def _reset_icon_choice(self):
        self._custom_icon = None
        self._render_icon()

    def _refresh_placeholder_icon(self):
        # the generated placeholder shows the app's initial, so keep it in sync with the name
        if not self._custom_icon and not (self.metadata and self.metadata.icon_data):
            self._render_icon()

    def _render_icon(self):
        dpr = self.devicePixelRatioF()
        if self._custom_icon:
            self.icon_lbl.setPixmap(app_pixmap(self._custom_icon, self.name_edit.text(), 80, dpr))
        elif self.metadata:
            self._show_icon(self.metadata)
        else:
            self.icon_lbl.setPixmap(placeholder_pixmap("?", 80, dpr))
        self.icon_reset_btn.setVisible(bool(self._custom_icon))

    def _reset_details(self):
        self.icon_lbl.setPixmap(placeholder_pixmap("?", 80, self.devicePixelRatioF()))
        self.icon_btn.setEnabled(False)
        self.icon_reset_btn.hide()
        self.name_edit.setEnabled(False)
        self.name_edit.clear()
        self._name_touched = False
        self.meta_lbl.setText("Choose a file to see its name, version and icon.")
        self.warn_lbl.clear()

    def _show_icon(self, md: AppMetadata):
        import tempfile

        icon_path = None
        if md.icon_data and md.icon_ext:
            fd, icon_path = tempfile.mkstemp(suffix="." + md.icon_ext)
            with os.fdopen(fd, "wb") as f:
                f.write(md.icon_data)
        pm = app_pixmap(icon_path, self.name_edit.text() or md.name_suggestion, 80, self.devicePixelRatioF())
        self.icon_lbl.setPixmap(pm)
        if icon_path:
            try:
                os.unlink(icon_path)
            except OSError:
                pass

    def _show_file_msg(self, text: str):
        self.file_msg.setText(text)
        self.file_msg.setVisible(bool(text))
        self._validate()

    # -- validation / save --------------------------------------------------------------
    def _on_name_edited(self, _):
        self._name_touched = True

    def _on_repo_edited(self, _):
        self._repo_touched = True

    def _repo_error(self) -> str | None:
        try:
            normalize_repo(self.repo_edit.text())
            return None
        except LibraryError as exc:
            return str(exc)

    def _validate(self):
        err = self._repo_error()
        _set_invalid(self.repo_edit, bool(err))
        if err:
            self.repo_msg.setText(err)
            self.repo_msg.setObjectName("error")
        else:
            hint = SOURCE_HINT
            if self.metadata and self.metadata.format_id == "appimage":
                if self._auto_repo and self.repo_edit.text() == self._auto_repo:
                    hint = source_detection_message(self.metadata)
                elif not self.repo_edit.text().strip():
                    hint = ("Update source left empty. Add without automatic updates, or enter a repository URL."
                            if metadata_source(self.metadata) else source_detection_message(self.metadata))
            self.repo_msg.setText(hint)
            self.repo_msg.setObjectName("hint")
        self.repo_msg.style().unpolish(self.repo_msg)
        self.repo_msg.style().polish(self.repo_msg)
        env_err = _env_error(self.env_edit)
        self.env_msg.setText(env_err or ENV_HINT)
        self.env_msg.setObjectName("error" if env_err else "hint")
        self.env_msg.style().unpolish(self.env_msg)
        self.env_msg.style().polish(self.env_msg)
        self.add_btn.setEnabled(bool(self.metadata and self.name_edit.text().strip()) and not err
                                and not env_err and not self.file_msg.isVisible())

    def _accept(self):
        self.menu_requested = self.menu_cb.isChecked()
        try:
            md = self.metadata
            if self.downloaded and self.path_edit.text() == self.downloaded.path:
                from ..core.downloads import validate_downloaded
                from ..core.updates.service import pattern_from_asset
                validate_downloaded(self.downloaded)
                if normalize_repo(self.repo_edit.text()) == self.downloaded.choice.source:
                    choice = self.downloaded.choice
                    extra = {**md.extra, "asset_pattern": pattern_from_asset(choice.asset.name, choice.release.tag)}
                    if choice.release.prerelease:
                        extra["include_prereleases"] = True
                    md = replace(md, extra=extra)
            self.added = self.service.add_application(
                self.path_edit.text(), name=self.name_edit.text(),
                github_repo=self.repo_edit.text(), metadata=md,
                custom_icon=self._custom_icon, integrate_desktop=self.menu_requested,
                menu_category=self.menu_category_cb.currentData(),
                env_vars=parse_env_text(self.env_edit.toPlainText()),
                launch_options=self._launch_options,
            )
        except LibraryError as exc:
            self._show_file_msg(str(exc))
            return
        try:   # remember the choice for next time
            self.service.set_desktop_default(self.menu_requested)
        except Exception:  # noqa: BLE001 - a preference must never block adding an app
            pass
        self.accept()


class EditApplicationDialog(QDialog):
    def __init__(self, service: LibraryService, entry: AppEntry, parent=None):
        super().__init__(parent)
        self.service, self.entry = service, entry
        self._launch_options = {k: v for k, v in entry.metadata.items() if k in LAUNCH_KEYS}
        self.setWindowTitle(f"Edit {entry.name}")
        self._orig_path = entry.path
        self._new_icon: str | None = None   # path of a newly chosen image
        self._reset_icon = False            # True = go back to the AppImage's own icon
        outer, lay = _scrolling_body(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(14)
        self.icon_lbl = QLabel(objectName="iconTile")
        self.icon_lbl.setFixedSize(56, 56)
        self.icon_lbl.setPixmap(app_pixmap(entry.icon_path, entry.name, 56, self.devicePixelRatioF()))
        head.addWidget(self.icon_lbl)
        titles = QVBoxLayout()
        titles.addWidget(QLabel("Edit application", objectName="title"))
        fmt = get_format(entry.format)
        added = datetime.fromtimestamp(entry.added_at).strftime("%d %b %Y")
        titles.addWidget(QLabel(f"{fmt.display_name if fmt else entry.format} · added {added}",
                                objectName="subtitle"))
        head.addLayout(titles, 1)
        icon_btns = QVBoxLayout()
        icon_btns.setSpacing(4)
        self.icon_btn = QPushButton("Change icon…")
        self.icon_btn.clicked.connect(self._choose_icon)
        self.icon_reset_btn = QPushButton("Use default icon")
        self.icon_reset_btn.clicked.connect(self._reset_icon_choice)
        self.icon_reset_btn.setVisible(bool(entry.metadata.get("custom_icon")))
        icon_btns.addWidget(self.icon_btn)
        icon_btns.addWidget(self.icon_reset_btn)
        head.addLayout(icon_btns)
        lay.addLayout(head)
        lay.addSpacing(8)

        lay.addWidget(_field_label("Display name"))
        self.name_edit = QLineEdit(entry.name)
        lay.addWidget(self.name_edit)

        lay.addWidget(_field_label("Category"))
        self._original_category = menu_category_of(entry)
        self._category_changed = False
        self.menu_category_cb = _menu_category_combo(self._original_category)
        self.menu_category_cb.currentIndexChanged.connect(self._category_selected)
        self.menu_category_cb.activated.connect(self._category_selected)
        lay.addWidget(self.menu_category_cb)
        if entry.metadata.get("category") and self._original_category is None:
            legacy_hint = QLabel(
                f'Previous library category: {entry.metadata["category"]}. '
                'Choose a category above to use it in both AppForge and your application menu.',
                objectName="hint")
            legacy_hint.setTextFormat(Qt.PlainText)
            legacy_hint.setWordWrap(True)
            lay.addWidget(legacy_hint)

        _launch_options_row(self, lay)
        self.env_edit = _env_edit(format_env_text(clean_env(entry.metadata.get(ENV_KEY))))
        self.env_edit.textChanged.connect(self._revalidate)
        lay.addWidget(self.env_edit)
        self.env_msg = QLabel(ENV_HINT, objectName="hint")
        self.env_msg.setWordWrap(True)
        lay.addWidget(self.env_msg)

        lay.addWidget(_field_label("File location"))
        row = QHBoxLayout()
        self.path_edit = QLineEdit(entry.path)
        self.path_edit.textChanged.connect(self._path_changed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        self.path_msg = QLabel(objectName="error")
        self.path_msg.setWordWrap(True)
        lay.addWidget(self.path_msg)

        lay.addWidget(_field_label("Installed version"))
        self.version_edit = QLineEdit(entry.installed_version or "")
        self.version_edit.setPlaceholderText("Unknown")
        lay.addWidget(self.version_edit)

        lay.addWidget(_field_label("Update source (optional)"))
        self.repo_edit = QLineEdit(entry.github_repo or "")
        self.repo_edit.setPlaceholderText("https://github.com/owner/repo  or  https://git.example.dev/owner/repo")
        self.repo_edit.textChanged.connect(self._repo_changed)
        lay.addWidget(self.repo_edit)
        self.repo_msg = QLabel(objectName="error")
        lay.addWidget(self.repo_msg)
        self.pre_cb = QCheckBox("Include pre-releases when checking for updates")
        self.pre_cb.setChecked(bool(entry.metadata.get("include_prereleases")))
        lay.addWidget(self.pre_cb)
        lay.addWidget(_field_label("Release file pattern (optional)"))
        self.pattern_edit = QLineEdit(entry.metadata.get("asset_pattern") or "")
        self.pattern_edit.setPlaceholderText("Detected automatically, e.g. MyApp-*-x86_64.AppImage")
        self.pattern_edit.setToolTip("Which release file to download. Use * in place of the version.")
        lay.addWidget(self.pattern_edit)

        self.refresh_cb = QCheckBox("Re-read icon and version from the file when saving")
        lay.addWidget(self.refresh_cb)
        self.error_lbl = QLabel(objectName="error")
        self.error_lbl.setWordWrap(True)
        lay.addWidget(self.error_lbl)

        lay.addSpacing(8)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Save changes", objectName="primary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(self.save_btn)
        btns.setContentsMargins(24, 8, 24, 20)
        outer.addLayout(btns)
        self._path_changed()
        self.setMinimumSize(520, 420)
        self.resize(560, min(lay.sizeHint().height() + 110,
                             self.screen().availableGeometry().height() - 80))

    def _category_selected(self):
        self._category_changed = True

    def _choose_icon(self):
        start = str(Path(self._new_icon).parent) if self._new_icon else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose an icon", start, ICON_FILTER)
        if not path:
            return
        if QPixmap(path).isNull() and not path.lower().endswith(".svg"):
            self.error_lbl.setText("That image couldn't be read. Try a PNG or SVG.")
            return
        self.error_lbl.clear()
        self._new_icon, self._reset_icon = path, False
        self.icon_lbl.setPixmap(app_pixmap(path, self.name_edit.text(), 56, self.devicePixelRatioF()))
        self.icon_reset_btn.show()

    def _reset_icon_choice(self):
        self._new_icon, self._reset_icon = None, True
        # preview: show the placeholder until saved (the real built-in icon is restored on save)
        self.icon_lbl.setPixmap(placeholder_pixmap(self.name_edit.text() or self.entry.name, 56,
                                                   self.devicePixelRatioF()))
        self.icon_reset_btn.hide()

    def _browse(self):
        start = str(Path(self.path_edit.text()).parent)
        path, _ = QFileDialog.getOpenFileName(self, "Choose the file", start, FILE_FILTER)
        if path:
            self.path_edit.setText(path)

    def _path_changed(self):
        p = normalize_path(self.path_edit.text()) if self.path_edit.text().strip() else ""
        missing = not p or not Path(p).is_file()
        self.path_msg.setText("That file doesn't exist. You can still save, and fix it later." if missing else "")
        self.path_msg.setVisible(missing)
        if p and p != self._orig_path and not missing:
            self.refresh_cb.setChecked(True)

    def _repo_changed(self):
        try:
            normalize_repo(self.repo_edit.text())
            err = ""
        except LibraryError as exc:
            err = str(exc)
        self.repo_msg.setText(err)
        self.repo_msg.setVisible(bool(err))
        _set_invalid(self.repo_edit, bool(err))
        self._revalidate()

    def _revalidate(self):
        try:
            normalize_repo(self.repo_edit.text())
            repo_ok = True
        except LibraryError:
            repo_ok = False
        env_err = _env_error(self.env_edit)
        self.env_msg.setText(env_err or ENV_HINT)
        self.env_msg.setObjectName("error" if env_err else "hint")
        self.env_msg.style().unpolish(self.env_msg)
        self.env_msg.style().polish(self.env_msg)
        self.save_btn.setEnabled(repo_ok and not env_err)

    def _save(self):
        try:
            new_path = self.path_edit.text().strip()
            changes: dict = dict(name=self.name_edit.text(),
                                 menu_category=self.menu_category_cb.currentData(),
                                 env_vars=parse_env_text(self.env_edit.toPlainText()),
                                 launch_options=self._launch_options,
                                 github_repo=self.repo_edit.text(),
                                 installed_version=self.version_edit.text(),
                                 settings={"include_prereleases": self.pre_cb.isChecked(),
                                           "asset_pattern": self.pattern_edit.text()})
            if self.menu_category_cb.currentData() is not None or self._category_changed:
                changes["category"] = None
            if new_path and normalize_path(new_path) != self.entry.path:
                if Path(normalize_path(new_path)).is_file():
                    changes["path"] = new_path
                else:
                    raise LibraryError("The new file location doesn't exist.")
            typed_version = self.version_edit.text().strip()
            version_edited = typed_version != (self.entry.installed_version or "")
            if self._new_icon:
                changes["icon"] = self._new_icon
            elif self._reset_icon:
                changes["icon"] = None
            entry = self.service.update_application(self.entry.id, **changes)
            if self.refresh_cb.isChecked() and Path(entry.path).is_file():
                entry = self.service.refresh_metadata(entry.id, overwrite_version=True)
                if version_edited and typed_version:  # an explicit manual edit wins
                    entry = self.service.update_application(entry.id, installed_version=typed_version)
            self.entry = entry
        except LibraryError as exc:
            self.error_lbl.setText(str(exc))
            return
        self.accept()


class AssetPickerDialog(QDialog):
    """Lets the user choose which release file to use when automatic detection is unsure."""

    def __init__(self, assets: list[dict], preselect: str | None, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose release file")
        self.setFixedSize(520, 420)
        self.chosen: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Choose release file", objectName="title"))
        sub = QLabel(message, objectName="subtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.list = QListWidget()
        for a in assets:
            mb = f"  ·  {a['size'] / 1e6:.1f} MB" if a.get("size") else ""
            item = QListWidgetItem(a["name"] + mb)
            item.setData(Qt.UserRole, a["name"])
            self.list.addItem(item)
            if a["name"] == preselect:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and assets:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self._accept())
        lay.addWidget(self.list, 1)
        lay.addWidget(QLabel("Your choice is remembered for future updates of this app.", objectName="hint"))
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Use this file", objectName="primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _accept(self):
        item = self.list.currentItem()
        if item:
            self.chosen = item.data(Qt.UserRole)
            self.accept()
