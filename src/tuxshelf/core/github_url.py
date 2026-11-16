"""Parsing of GitHub repository references. (Release fetching arrives in Phase 2.)"""
from __future__ import annotations

import re
from typing import NamedTuple


class RepoRef(NamedTuple):
    owner: str
    name: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


_NAME = r"[A-Za-z0-9._-]+"
_URL_RE = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)"
    rf"/(?P<name>{_NAME})(?:[/?#].*)?$",
    re.IGNORECASE,
)
_SHORT_RE = re.compile(rf"^(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/(?P<name>{_NAME})$")


def parse_repo(text: str) -> RepoRef | None:
    """Accept ``https://github.com/o/r``, ``github.com/o/r(.git)``, ``git@github.com:o/r`` or ``o/r``."""
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("git@github.com:"):
        s = "github.com/" + s[len("git@github.com:"):]
    m = _URL_RE.match(s) or _SHORT_RE.match(s)
    if not m:
        return None
    name = m.group("name")
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not name or name in (".", ".."):
        return None
    return RepoRef(m.group("owner"), name)
