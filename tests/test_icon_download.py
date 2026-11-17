"""Custom image URLs: bounded transfer, validation, cancellation and persisted overrides."""
from io import BytesIO
from threading import Event

import pytest
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog

from test_gui import qapp, wait_for
from tuxshelf.core import icon_download as net
from tuxshelf.ui import dialogs, icon_url_dialog as ui


class Response(BytesIO):
    headers = {}


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'ftp://example.com/a', 'hello',
                                  'https://user:password@example.com/a', 'https://[broken'])
def test_invalid_url_never_opens_network(url, monkeypatch):
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: pytest.fail('unexpected network'))
    with pytest.raises(net.IconDownloadError, match='HTTP'):
        net.download_icon(url, Event())


def test_download_limit_empty_cancel_and_progress(monkeypatch):
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: Response(b'abc'))
    progress = []
    assert net.download_icon('https://example.com/icon', Event(), lambda *x: progress.append(x)) == b'abc'
    assert progress == [(3, 0)]
    cancelled = Event()
    cancelled.set()
    with pytest.raises(net.IconDownloadError, match='cancelled'):
        net.download_icon('https://example.com/icon', cancelled)
    monkeypatch.setattr(net, 'MAX_ICON_BYTES', 2)
    with pytest.raises(net.IconDownloadError, match='too large'):
        net.download_icon('https://example.com/icon', Event())
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: Response(b''))
    with pytest.raises(net.IconDownloadError, match='empty'):
        net.download_icon('https://example.com/icon', Event())


def test_declared_oversize_and_network_failure(monkeypatch):
    response = Response(b'')
    response.headers = {'Content-Length': str(net.MAX_ICON_BYTES + 1)}
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: response)
    with pytest.raises(net.IconDownloadError, match='too large'):
        net.download_icon('http://example.com/icon', Event())
    def fail(*a, **k):
        raise OSError('private-query-token')
    monkeypatch.setattr(net, 'urlopen', fail)
    with pytest.raises(net.IconDownloadError, match='connection') as exc:
        net.download_icon('https://example.com/?token=secret', Event())
    assert 'token' not in str(exc.value)


def png():
    image = QImage(24, 24, QImage.Format_ARGB32)
    image.fill(0xffff5500)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    assert image.save(buffer, 'PNG')
    return bytes(data)


def test_worker_download_and_invalid_content_retry(qapp, monkeypatch):
    dialog = ui.IconUrlDialog()
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: Response(b'<html>not an image</html>'))
    dialog.url_edit.setText('https://example.com/icon')
    dialog._start()
    assert wait_for(qapp, lambda: dialog._job is None)
    assert dialog.image is None and dialog.status.text()
    monkeypatch.setattr(net, 'urlopen', lambda *a, **k: Response(png_bytes))
    png_bytes = png()
    dialog._start()
    assert wait_for(qapp, lambda: dialog.result() == QDialog.Accepted)
    assert dialog.image.width() == 24
    dialog.close()


def test_cancel_ignores_late_success(qapp):
    dialog = ui.IconUrlDialog()
    dialog.reject()
    dialog._finished(png())
    assert dialog.image is None and dialog.result() == QDialog.Rejected


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_add_edit_url_cache_and_reset(qapp, service, tmp_path, monkeypatch, mode):
    from tuxshelf.ui.theme import apply_theme
    apply_theme(qapp, mode)
    script = tmp_path / 'app.sh'
    script.write_text('#!/bin/sh\necho app\n')
    def downloaded(self):
        self._finished(png())
        return self.result()
    monkeypatch.setattr(ui.IconUrlDialog, 'exec', downloaded)
    add = dialogs.AddApplicationDialog(service, initial_path=str(script))
    assert wait_for(qapp, lambda: add.metadata is not None)
    add.show()
    add.icon_url_btn.click()
    assert add._custom_icon and add.icon_reset_btn.isVisible()
    source = add._custom_icon
    add._accept()
    entry = add.added
    assert entry and entry.metadata['custom_icon']
    assert entry.icon_path != source
    assert QImage(entry.icon_path).width() == 24
    refreshed = service.refresh_metadata(entry.id)
    assert refreshed.icon_path == entry.icon_path and refreshed.metadata['custom_icon']
    edit = dialogs.EditApplicationDialog(service, entry)
    edit.show()
    edit.icon_url_btn.click()
    assert edit._new_icon and not edit._reset_icon
    edit._save()
    assert service.get(entry.id).metadata['custom_icon']
    reset = dialogs.EditApplicationDialog(service, service.get(entry.id))
    reset._reset_icon_choice()
    reset._save()
    assert not service.get(entry.id).metadata.get('custom_icon')
    add.close()
    edit.close()
    reset.close()


def test_running_download_can_be_cancelled_without_blocking_ui(qapp, monkeypatch):
    started, finished = Event(), Event()
    def download(url, cancel, progress):
        started.set()
        assert cancel.wait(3)
        finished.set()
        raise net.IconDownloadError("Download cancelled.")
    monkeypatch.setattr(ui, 'download_icon', download)
    dialog = ui.IconUrlDialog()
    dialog.url_edit.setText('https://example.com/icon')
    dialog._start()
    assert wait_for(qapp, started.is_set)
    assert not dialog.download_btn.isEnabled()
    dialog.reject()
    assert wait_for(qapp, finished.is_set)
    assert wait_for(qapp, lambda: dialog._job is None)
    assert dialog.result() == QDialog.Rejected and dialog.image is None
