"""HTTPS helper: system CA certificates plus certifi's bundle as a fallback.

The AppImage ships its own OpenSSL, whose built-in certificate path doesn't exist on every distro,
so relying on the system defaults alone could make HTTPS fail on Arch/CachyOS.
"""
from __future__ import annotations

import ssl
import urllib.request

_ctx: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:  # noqa: BLE001 - certifi is a fallback only
            pass
        _ctx = ctx
    return _ctx


def urlopen(req, timeout: float | None = None):
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())  # noqa: S310
