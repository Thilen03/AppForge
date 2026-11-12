"""Minimal GitHub Releases API client (stdlib only; never scrapes web pages)."""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from ... import __version__
from .net import urlopen as _urlopen

API = "https://api.github.com"


class GitHubError(Exception):
    """kind: not_found | rate_limit | network | http | invalid"""

    def __init__(self, message: str, kind: str = "http"):
        super().__init__(message)
        self.kind = kind


@dataclass
class Asset:
    name: str
    url: str
    size: int = 0
    digest: str | None = None   # e.g. "sha256:ab12…" (provided by GitHub for newer uploads)
    content_type: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "url": self.url, "size": self.size, "digest": self.digest}

    @staticmethod
    def from_dict(d: dict) -> "Asset":
        return Asset(d["name"], d["url"], d.get("size", 0), d.get("digest"))


@dataclass
class Release:
    tag: str
    name: str = ""
    prerelease: bool = False
    draft: bool = False
    published_at: str | None = None
    html_url: str | None = None
    assets: list[Asset] = field(default_factory=list)


def user_agent() -> str:
    return f"AppForge/{__version__} (+https://github.com/appforge)"


def default_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: float = 20, api: str = API, opener=None):
        self.token = token if token is not None else default_token()
        self.timeout, self.api = timeout, api
        self._open = opener or _urlopen

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": user_agent()}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def releases(self, owner: str, name: str, per_page: int = 30) -> list[Release]:
        url = f"{self.api}/repos/{owner}/{name}/releases?per_page={per_page}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with self._open(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._map_http_error(exc, f"{owner}/{name}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            raise GitHubError(f"Couldn't reach GitHub ({getattr(exc, 'reason', exc)}).", "network") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubError("GitHub returned an unreadable response.", "invalid") from exc
        if not isinstance(data, list):
            raise GitHubError("Unexpected response from GitHub.", "invalid")
        return [self._release(r) for r in data if isinstance(r, dict)]

    @staticmethod
    def _release(r: dict) -> Release:
        assets = [Asset(a.get("name", ""), a.get("browser_download_url", ""), int(a.get("size") or 0),
                        a.get("digest"), a.get("content_type"))
                  for a in r.get("assets", []) if a.get("browser_download_url")]
        return Release(tag=r.get("tag_name") or "", name=r.get("name") or "",
                       prerelease=bool(r.get("prerelease")), draft=bool(r.get("draft")),
                       published_at=r.get("published_at"), html_url=r.get("html_url"), assets=assets)

    @staticmethod
    def _map_http_error(exc: urllib.error.HTTPError, repo: str) -> GitHubError:
        if exc.code == 404:
            return GitHubError(f"Repository {repo} was not found, or it has no public releases.", "not_found")
        remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
        if exc.code in (403, 429) and (remaining == "0" or exc.code == 429):
            reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
            when = ""
            if reset and reset.isdigit():
                when = " Try again after " + datetime.fromtimestamp(int(reset)).strftime("%H:%M") + "."
            hint = "" if default_token() else " Setting GITHUB_TOKEN raises the limit."
            return GitHubError("GitHub's rate limit was reached." + when + hint, "rate_limit")
        return GitHubError(f"GitHub returned an error (HTTP {exc.code}).", "http")
