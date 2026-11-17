"""Bounded downloads for user-selected custom icons (no library/database access)."""
from __future__ import annotations

import time
from threading import Event
from urllib.parse import urlsplit
from urllib.request import Request

from .updates.net import urlopen

MAX_ICON_BYTES = 10 * 1024 * 1024


class IconDownloadError(ValueError):
    pass


def download_icon(url: str, cancel: Event, progress=None) -> bytes:
    url = url.strip()
    try:
        parts = urlsplit(url)
        valid = parts.scheme.lower() in {"http", "https"} and parts.hostname and not parts.username and not parts.password
    except ValueError:
        valid = False
    if not valid:
        raise IconDownloadError("Enter a direct HTTP or HTTPS image link without login details.")
    try:
        request = Request(url, headers={"User-Agent": "TuxShelf", "Accept": "image/*"})
        deadline = time.monotonic() + 60
        with urlopen(request, timeout=10) as response:
            length = response.headers.get("Content-Length", "")
            total = int(length) if length.isdigit() else 0
            if total > MAX_ICON_BYTES:
                raise IconDownloadError("That image is too large (10 MB maximum).")
            data = bytearray()
            while True:
                if cancel.is_set():
                    raise IconDownloadError("Download cancelled.")
                if time.monotonic() > deadline:
                    raise IconDownloadError("The image download timed out. Try again.")
                chunk = response.read(min(65536, MAX_ICON_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_ICON_BYTES:
                    raise IconDownloadError("That image is too large (10 MB maximum).")
                if progress:
                    progress(len(data), total)
            if not data:
                raise IconDownloadError("The image link returned an empty file.")
            return bytes(data)
    except IconDownloadError:
        raise
    except Exception as exc:
        # Avoid echoing URL query parameters, which can contain private access tokens.
        raise IconDownloadError("Could not download the image. Check the link and your connection.") from exc
