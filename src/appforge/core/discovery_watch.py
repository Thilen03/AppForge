"""Stable-file observations for opt-in discovery polling. No Qt or database access."""
from __future__ import annotations

from dataclasses import dataclass, field

from .discovery import _signature, scan
from .library import normalize_path

WATCHED_KEY = "discovery_watched_roots"
TEMP_SUFFIXES = (".part", ".partial", ".tmp", ".download", ".crdownload")


@dataclass
class WatchState:
    observations: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def scan_watched(roots, registered=(), ignored=(), previous=None, cancel=None):
    """Offer files unchanged across two polls; reuse metadata only for identical files."""
    previous = previous or WatchState()
    observed = {}
    metadata = dict(previous.metadata)
    excluded = {normalize_path(p) for p in (*registered, *ignored)}

    def ready(path, info):
        if path.name.startswith('.') or path.name.lower().endswith(TEMP_SUFFIXES):
            return False
        key = str(path)
        fingerprint = (*_signature(info), info.st_mode, info.st_ctime_ns)
        observed[key] = fingerprint
        return key not in excluded and previous.observations.get(key) == fingerprint

    result = scan(roots, registered, ignored, cancel=cancel, file_filter=ready,
                  metadata_cache=metadata)
    result.candidates = [c for c in result.candidates if not c.registered and not c.ignored]
    metadata = {p: value for p, value in metadata.items()
                if p not in excluded and observed.get(p) == value[0]}
    return result, WatchState(observed, metadata)
