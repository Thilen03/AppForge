"""Tolerant version parsing/comparison for release tags and AppImage versions.

Handles ``v1.2.3``, ``release-1.2``, ``5.0-1234`` (build numbers), ``2024-05-01`` (dates),
``2.0.0-rc.1`` / ``beta2`` (pre-releases). Returns ``None`` when a string has no digits at all
(``nightly``, ``continuous``) because such tags cannot be ordered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PRE = {"dev": -5, "nightly": -5, "snapshot": -5, "alpha": -4, "a": -4, "beta": -3, "b": -3,
        "preview": -2, "pre": -2, "rc": -1, "candidate": -1}
_NUMBERED_NIGHTLY = re.compile(r"(?:nightly|snapshot)[-_](\d+)(?:[-_][0-9a-f]{7,40})?", re.IGNORECASE)
_LEGACY_COMMIT_BUILD = re.compile(r"(\d+)-([0-9a-f]{7,40})", re.IGNORECASE)

_POST = {"post": 1, "patch": 1, "p": 1, "hotfix": 1}


@dataclass(frozen=True)
class Version:
    nums: tuple[int, ...]
    rank: int = 0       # <0 pre-release, 0 release, >0 post-release
    rank_num: int = 0

    def _key(self, width: int):
        return (self.nums + (0,) * (width - len(self.nums)), self.rank, self.rank_num)


def parse_version(text: str | None) -> Version | None:
    if not text:
        return None
    # Numbered nightly builds are ordered by build number, never by commit hash.
    nightly = _NUMBERED_NIGHTLY.fullmatch(text.strip())
    if nightly:
        return Version((int(nightly.group(1)),))
    legacy = _LEGACY_COMMIT_BUILD.fullmatch(text.strip())
    if legacy and re.search(r"[a-f]", legacy.group(2), re.IGNORECASE):
        return Version((int(legacy.group(1)),))
    m = re.search(r"\d", text)
    if not m:
        return None
    s = text[m.start():]
    core = re.match(r"\d+(?:[._]\d+)*", s)
    nums = [int(x) for x in re.split(r"[._]", core.group(0))]
    rest = s[core.end():]
    # "-1234" / "-05-01" style numeric groups extend the version (build numbers, dates)
    while (g := re.match(r"-(\d+(?:[._]\d+)*)(?![A-Za-z0-9._])", rest)):
        nums += [int(x) for x in re.split(r"[._]", g.group(1))]
        rest = rest[g.end():]
    rank, rank_num = 0, 0
    w = re.match(r"[-_.+ ]*([A-Za-z]+)[-_.]?(\d+)?", rest)
    if w:
        word = w.group(1).lower()
        rank = _PRE.get(word, _POST.get(word, 0))
        rank_num = int(w.group(2) or 0) if rank else 0
    return Version(tuple(nums), rank, rank_num)


def compare(a: str | None, b: str | None) -> int | None:
    """-1/0/1 like ``cmp(a, b)``, or None if either side can't be parsed."""
    va, vb = parse_version(a), parse_version(b)
    if va is None or vb is None:
        return None
    width = max(len(va.nums), len(vb.nums))
    ka, kb = va._key(width), vb._key(width)
    return (ka > kb) - (ka < kb)


def display_version(tag: str) -> str:
    """Strip ordinary tag prefixes; retain numbered nightly tags and their build identity."""
    if _NUMBERED_NIGHTLY.fullmatch((tag or "").strip()):
        return tag.strip()
    m = re.search(r"\d", tag or "")
    return tag[m.start():].strip() if m else (tag or "").strip()
