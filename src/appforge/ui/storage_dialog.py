"""Storage overview, painted donut chart and reviewed asynchronous backup cleanup."""
from copy import deepcopy
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QRectF, QThreadPool, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.storage import StorageSnapshot, scan_storage, cleanup_backups
from . import theme
from .details_dialog import date_text

BLUE, TEAL = '#7195FF', '#25C4AA'


def size_text(value):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:,.0f} {unit}' if unit == 'B' else f'{value:,.1f} {unit}'
        value /= 1024


class StorageChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.application_size = self.backup_size = 0
        self.setMinimumSize(260, 238)
        self.setAccessibleName('Application and backup storage pie chart')

    def set_sizes(self, applications, backups):
        self.application_size, self.backup_size = applications, backups
        total = applications + backups
        self.setToolTip(f'Applications: {size_text(applications)}\nBackups: {size_text(backups)}\n'
                        f'Backups: {backups / total:.1%} of measured storage' if total else 'No storage measured')
        self.setAccessibleDescription(self.toolTip())
        self.update()

    def paintEvent(self, event):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 46
        ring = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        p.setPen(QPen(QColor(t.border), 22))
        p.drawEllipse(ring)
        total = self.application_size + self.backup_size
        angle = 90.0
        if total:
            for value, color in ((self.application_size, BLUE), (self.backup_size, TEAL)):
                span = 360 * value / total
                if not span:
                    continue
                gap = min(3.5, span / 4) if value != total else 0
                pen = QPen(QColor(color), 22, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.drawArc(ring, round((angle - gap / 2) * 16), -round((span - gap) * 16))
                angle -= span
        p.setPen(QColor(t.text))
        font = QFont(self.font())
        font.setPointSize(22)
        font.setBold(True)
        p.setFont(font)
        p.drawText(ring.adjusted(0, -12, 0, -12), Qt.AlignCenter, size_text(total))
        font.setPointSize(10)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor(t.muted))
        p.drawText(ring.adjusted(0, 42, 0, 42), Qt.AlignCenter, 'TOTAL MEASURED')
        p.end()


class NumberItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        a, b = self.data(column, Qt.UserRole), other.data(column, Qt.UserRole)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return super().__lt__(other)


class StorageSignals(QObject):
    done = Signal(object, str)
    progress = Signal(int, int)


class StorageJob(QRunnable):
    def __init__(self, operation, *args):
        super().__init__()
        self.operation, self.args = operation, args
        self.cancel = Event()
        self.signals = StorageSignals()

    def run(self):
        try:
            result = self.operation(*self.args, self.cancel, self.signals.progress.emit)
            self.signals.done.emit(result, '')
        except Exception as exc:
            self.signals.done.emit(None, str(exc))


class StorageDialog(QDialog):
    def __init__(self, library, backups, busy, parent=None):
        super().__init__(parent)
        self.library, self.backups, self.busy = library, backups, busy
        self.snapshot = StorageSnapshot()
        self._job = None
        self._pending_close = None
        self.setWindowTitle('Storage · AppForge')
        self.resize(1020, 870)
        self.setMinimumSize(860, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(QLabel('Storage', objectName='title'))
        heading.addWidget(QLabel('Know your footprint. Make room for what’s next.', objectName='subtitle'))
        top.addLayout(heading)
        top.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self.refresh_btn)
        root.addLayout(top)

        card = QFrame(objectName='card')
        overview = QHBoxLayout(card)
        self.chart = StorageChart()
        overview.addWidget(self.chart, 1)
        stats = QVBoxLayout()
        self.apps_stat = QLabel(objectName='title')
        self.backups_stat = QLabel(objectName='title')
        self.count_stat = QLabel(objectName='subtitle')
        for title, color, value in (('APPLICATIONS', BLUE, self.apps_stat), ('SAVED BACKUPS', TEAL, self.backups_stat)):
            label = QLabel('●  ' + title)
            label.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 700;')
            stats.addWidget(label)
            stats.addWidget(value)
        stats.addWidget(self.count_stat)
        overview.addLayout(stats, 1)
        leaders = QVBoxLayout()
        leaders.addWidget(QLabel('SPACE LEADERS', objectName='sectionLabel'))
        self.leaders = QLabel('Scanning…')
        self.leaders.setTextFormat(Qt.PlainText)
        self.leaders.setWordWrap(True)
        leaders.addWidget(self.leaders)
        note = QLabel('Logical file sizes • shared hard links may use less disk space.', objectName='hint')
        note.setWordWrap(True)
        leaders.addWidget(note)
        overview.addLayout(leaders, 1)
        root.addWidget(card)

        filters = QHBoxLayout()
        filters.addWidget(QLabel('Your applications', objectName='sectionLabel'))
        filters.addStretch()
        self.only_backups = QCheckBox('With backups only')
        self.only_backups.toggled.connect(self._render_apps)
        filters.addWidget(self.only_backups)
        self.sort = QComboBox()
        self.sort.addItems(['Largest combined', 'Largest applications', 'Largest backups', 'Name'])
        self.sort.currentIndexChanged.connect(self._sort_apps)
        filters.addWidget(self.sort)
        root.addLayout(filters)
        splitter = QSplitter(Qt.Vertical)
        self.apps = QTreeWidget()
        self.apps.setHeaderLabels(['Application', 'Current file', 'Backups', 'Backup size', 'Combined', 'Status'])
        self.apps.setRootIsDecorated(False)
        self.apps.setSortingEnabled(True)
        self.apps.setSelectionMode(QAbstractItemView.SingleSelection)
        self.apps.setAlternatingRowColors(True)
        self.apps.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.apps.itemSelectionChanged.connect(self._render_backups)
        splitter.addWidget(self.apps)
        backup_panel = QWidget()
        bl = QVBoxLayout(backup_panel)
        bl.setContentsMargins(0, 8, 0, 0)
        actions = QHBoxLayout()
        self.backup_heading = QLabel('Saved backups', objectName='sectionLabel')
        actions.addWidget(self.backup_heading, 1)
        self.older_btn = QPushButton('Select older than retention')
        self.older_btn.clicked.connect(self._select_older)
        actions.addWidget(self.older_btn)
        self.clear_btn = QPushButton('Clear selection')
        self.clear_btn.clicked.connect(lambda: self._check_backups(False))
        actions.addWidget(self.clear_btn)
        bl.addLayout(actions)
        self.files = QTreeWidget()
        self.files.setHeaderLabels(['Backup version', 'Saved', 'Size', 'Estimated savings'])
        self.files.setRootIsDecorated(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.setColumnWidth(1, 170)
        self.files.setColumnWidth(2, 115)
        self.files.setColumnWidth(3, 155)
        self.files.itemChanged.connect(self._selection_changed)
        bl.addWidget(self.files)
        self.retention = QLabel(objectName='hint')
        self.retention.setWordWrap(True)
        bl.addWidget(self.retention)
        splitter.addWidget(backup_panel)
        splitter.setSizes([175, 235])
        root.addWidget(splitter, 1)
        self.notice = QLabel(objectName='hint')
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.PlainText)
        root.addWidget(self.notice)
        footer = QHBoxLayout()
        self.savings = QLabel('No backups selected', objectName='subtitle')
        footer.addWidget(self.savings, 1)
        self.delete_btn = QPushButton('Delete selected…')
        self.delete_btn.clicked.connect(self._delete)
        footer.addWidget(self.delete_btn)
        self.cancel_btn = QPushButton('Stop')
        self.cancel_btn.clicked.connect(self._cancel)
        footer.addWidget(self.cancel_btn)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        root.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        self.refresh()

    def _start(self, job, callback):
        self._job = job
        job.signals.done.connect(callback)
        job.signals.progress.connect(self._progress)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._sync()
        QThreadPool.globalInstance().start(job)

    def _progress(self, done, total):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)

    def _finish(self):
        self._job = None
        self.progress.hide()
        self._sync()
        if self._pending_close is not None:
            super().done(self._pending_close)
            return True
        return False

    def refresh(self):
        if self._job:
            return
        self._entries = deepcopy(self.library.list_applications())
        self.notice.setText('Measuring application files and managed backups…')
        self._start(StorageJob(scan_storage, self._entries), self._scanned)

    def _scanned(self, snapshot, error):
        if self._finish():
            return
        if error:
            self.notice.setText('Storage scan failed: ' + error)
            return
        if self.library.list_applications() != self._entries:
            self.refresh()
            return
        self.snapshot = snapshot
        self.chart.set_sizes(snapshot.application_size, snapshot.backup_size)
        self.apps_stat.setText(size_text(snapshot.application_size))
        self.backups_stat.setText(size_text(snapshot.backup_size))
        self.count_stat.setText(f'{len(self._entries)} registered apps  ·  {snapshot.backup_count} backups')
        largest = max(snapshot.apps, key=lambda a: a.size, default=None)
        most = max(snapshot.apps, key=lambda a: a.backup_size, default=None)
        self.leaders.setText(f'Largest application\n{largest.entry.name} · {size_text(largest.size)}\n\n'
                             f'Most backup storage\n{most.entry.name} · {size_text(most.backup_size)}'
                             if largest else 'Your library is empty. Add an app to get started.')
        issues = sum(bool(a.notices) for a in snapshot.apps)
        self.notice.setText(('Scan stopped. Partial totals shown; refresh for a complete overview.' if snapshot.cancelled
                             else f'{issues} apps have unavailable files or folders; totals may be incomplete. See Status.'
                             if issues else 'Storage measured. Select an application to review its saved backups.'))
        self._render_apps()

    def _render_apps(self):
        selected = self._app()
        selected_id = selected.entry.id if selected else None
        self.apps.clear()
        for app in self.snapshot.apps:
            if self.only_backups.isChecked() and not app.backups:
                continue
            row = NumberItem([app.entry.name, size_text(app.size) if not any(n.startswith('Application') for n in app.notices)
                              else 'Unavailable', str(len(app.backups)), size_text(app.backup_size),
                              size_text(app.total), '; '.join(app.notices) or 'Measured'])
            row.setData(0, Qt.UserRole, app)
            row.setToolTip(0, app.entry.path)
            row.setToolTip(5, '\n'.join(app.notices))
            for col, number in ((1, app.size), (2, len(app.backups)), (3, app.backup_size), (4, app.total)):
                row.setData(col, Qt.UserRole, number)
            self.apps.addTopLevelItem(row)
            if app.entry.id == selected_id:
                self.apps.setCurrentItem(row)
        self._sort_apps()
        if not self.apps.currentItem() and self.apps.topLevelItemCount():
            self.apps.setCurrentItem(self.apps.topLevelItem(0))
        self._render_backups()

    def _sort_apps(self):
        column = [4, 1, 3, 0][self.sort.currentIndex()]
        self.apps.sortItems(column, Qt.AscendingOrder if column == 0 else Qt.DescendingOrder)

    def _app(self):
        row = self.apps.currentItem()
        return row.data(0, Qt.UserRole) if row else None

    def _render_backups(self):
        self.files.clear()
        app = self._app()
        keep = self.backups.retention()
        self.retention.setText(f'Retention: keep {keep} newest backups per app.' if keep else 'Retention: keep all backups.')
        self.retention.setText(self.retention.text() + ' Individual deletions are explicit; automatic retention stays unchanged.')
        self.backup_heading.setText('Saved backups · ' + app.entry.name if app else 'Saved backups · select an application')
        if app:
            for backup in app.backups:
                row = QTreeWidgetItem([str(backup.version or 'Unknown version'), date_text(backup.created),
                                       size_text(backup.size), size_text(backup.reclaimable)])
                row.setData(0, Qt.UserRole, backup)
                row.setCheckState(0, Qt.Unchecked)
                row.setToolTip(0, backup.path)
                self.files.addTopLevelItem(row)
        if not app or not app.backups:
            self.retention.setText(self.retention.text() + ' No saved backups for this selection.')
        self._selection_changed()

    def _selected(self):
        return [self.files.topLevelItem(i).data(0, Qt.UserRole)
                for i in range(self.files.topLevelItemCount())
                if self.files.topLevelItem(i).checkState(0) == Qt.Checked]

    def _check_backups(self, checked):
        for i in range(self.files.topLevelItemCount()):
            self.files.topLevelItem(i).setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def _select_older(self):
        keep = self.backups.retention()
        for i in range(self.files.topLevelItemCount()):
            self.files.topLevelItem(i).setCheckState(0, Qt.Checked if keep and i >= keep else Qt.Unchecked)

    def _selection_changed(self, *args):
        selected = self._selected()
        self.savings.setText(f'{len(selected)} selected · up to {size_text(sum(b.reclaimable for b in selected))} reclaimed'
                             if selected else 'No backups selected')
        self._sync()

    def _sync(self):
        working = self._job is not None
        app = self._app()
        idle_app = app is not None and app.entry.id not in self.busy
        self.refresh_btn.setEnabled(not working)
        self.cancel_btn.setVisible(working)
        self.delete_btn.setEnabled(not working and idle_app and bool(self._selected()))
        self.older_btn.setEnabled(not working and idle_app)
        self.clear_btn.setEnabled(not working)
        self.apps.setEnabled(not working)
        self.files.setEnabled(not working)

    def _delete(self):
        app, selected = self._app(), self._selected()
        if self._job or not app or not selected:
            return
        box = QMessageBox(QMessageBox.Warning, 'Delete selected backups',
                          f'Delete {len(selected)} saved backups of {app.entry.name}?', parent=self)
        box.setInformativeText(f'Expected savings: up to {size_text(sum(b.reclaimable for b in selected))}.\n'
                               'Deletion is permanent. Shared hard links may save no disk space.\n'
                               'The current application file is protected. Retention settings stay unchanged.')
        box.setDetailedText('\n'.join(f'{b.version or "Unknown"} · {date_text(b.created)} · {size_text(b.size)}\n{b.path}'
                                      for b in selected))
        go = box.addButton('Delete backups', QMessageBox.DestructiveRole)
        cancel = box.addButton('Cancel', QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not go:
            return
        if app.entry.id in self.busy or self.library.get(app.entry.id) != app.entry:
            self.notice.setText('Application changed or is busy. Refresh before cleaning up.')
            return
        paths = [e.path for e in self.library.list_applications()]
        self.notice.setText('Removing the approved backups…')
        self._start(StorageJob(cleanup_backups, [(deepcopy(app.entry), b) for b in selected], paths), self._cleaned)

    def _cleaned(self, result, error):
        # Only the GUI thread touches the database. Preserve concurrent metadata changes.
        if result:
            for app_id in {a for a, path in result.removed}:
                entry = self.library.get(app_id)
                if entry:
                    removed = {path for a, path in result.removed if a == app_id}
                    entry.backup_info['backups'] = [r for r in entry.backup_info.get('backups', [])
                                                    if r.get('file') not in removed]
                    try:
                        self.library.db.update(entry)
                    except Exception as exc:
                        result.errors.append(f'Files removed, but backup records could not be saved: {exc}')
        if self._finish():
            return
        if error:
            QMessageBox.warning(self, 'Cleanup failed', error)
        elif result.errors:
            QMessageBox.warning(self, 'Cleanup partially completed',
                                f'{len(result.removed)} backups deleted.\n' + '\n'.join(result.errors))
        elif result.cancelled:
            QMessageBox.information(self, 'Cleanup stopped', f'{len(result.removed)} backups deleted before stopping.')
        self.refresh()

    def _cancel(self):
        if self._job:
            self._job.cancel.set()
            self.notice.setText('Stopping after the current file…')

    def done(self, result):
        if self._job:
            self._pending_close = result
            self._cancel()
            return
        super().done(result)
