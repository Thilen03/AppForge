"""Update sources: GitHub, GitLab.com and Codeberg (Forgejo), all through their public release APIs.

``parse_source`` understands repository URLs of the three hosts (plus ``owner/repo`` shorthand,
which means GitHub, as in earlier versions). Each client returns the same ``Release``/``Asset``
objects, so version comparison, asset choice and installation are provider-independent.

Safety:
* a client only talks to its own API host, and a token is only ever sent to that host;
* asset links that are not ``https://`` are dropped (GitLab release links can point anywhere).
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from posixpath import basename

from .github import Asset, GitHubClient, GitHubError, Release, user_agent
from .net import urlopen as _urlopen

GITHUB, GITLAB, CODEBERG = "github", "gitlab", "codeberg"
HOSTS = {"github.com": GITHUB, "gitlab.com": GITLAB, "codeberg.org": CODEBERG}
PROVIDER_NAMES = {GITHUB: "GitHub", GITLAB: "GitLab", CODEBERG: "Codeberg"}
SUPPORTED_HINT = "https://github.com/owner/repo  (GitHub, GitLab and Codeberg are supported)"

_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_GITLAB_STOP = {"-", "releases", "tags", "blob", "tree", "issues", "merge_requests", "commits",
                "pipelines", "wikis", "raw", "archive"}
_PRERELEASE_TAG = re.compile(r"(?i)(?:^|[-._])(alpha|beta|rc|pre|preview)(?:[-._\d]|$)")


@dataclass(frozen=True)
class SourceRef:
    provider: str
    owner: str          # GitLab: the whole namespace, e.g. "group/subgroup"
    name: str

    @property
    def host(self) -> str:
        return next(h for h, p in HOSTS.items() if p == self.provider)

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.name}"

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAMES[self.provider]


def parse_source(text: str | None) -> SourceRef | None:
    """Parse a repository reference; ``None`` if it isn't a supported one."""
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("git@"):                       # git@host:owner/repo.git
        host, _, path = s[4:].partition(":")
        s = f"https://{host}/{path}"
    elif re.match(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$", s) and "." not in s.split("/")[0]:
        s = "https://github.com/" + s              # owner/repo shorthand = GitHub
    elif "://" not in s:
        s = "https://" + s
    parts = urllib.parse.urlsplit(s)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    provider = HOSTS.get(host)
    if provider is None:
        return None
    segs = [urllib.parse.unquote(p) for p in parts.path.split("/") if p]
    if provider == GITLAB:
        cut = next((i for i, p in enumerate(segs) if p in _GITLAB_STOP), len(segs))
        segs = segs[:cut]
    else:
        segs = segs[:2]
    if len(segs) < 2 or not all(_SEGMENT.match(p) and p not in (".", "..") for p in segs):
        return None
    name = segs[-1]
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not name:
        return None
    return SourceRef(provider, "/".join(segs[:-1]), name)


# -- shared HTTP/JSON plumbing ----------------------------------------------------------------
def _get_json(url: str, headers: dict[str, str], timeout: float, opener, label: str,
              provider: str) -> object:
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubError(f"{label} was not found on {provider}, or it has no public releases.",
                              "not_found") from exc
        if exc.code == 429:
            raise GitHubError(f"{provider}'s rate limit was reached. Try again later.", "rate_limit") from exc
        raise GitHubError(f"{provider} returned an error (HTTP {exc.code}).", "http") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        raise GitHubError(f"Couldn't reach {provider} ({getattr(exc, 'reason', exc)}).", "network") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitHubError(f"{provider} returned an unreadable response.", "invalid") from exc


def _https(url: str | None) -> bool:
    return bool(url) and url.lower().startswith("https://")


class ForgejoClient:
    """Codeberg (and any Forgejo/Gitea host): ``/api/v1/repos/{owner}/{repo}/releases``."""

    provider = "Codeberg"

    def __init__(self, host: str = "codeberg.org", timeout: float = 20, opener=None):
        self.host, self.timeout, self._open = host, timeout, opener or _urlopen

    def releases(self, owner: str, name: str, per_page: int = 30) -> list[Release]:
        url = (f"https://{self.host}/api/v1/repos/{urllib.parse.quote(owner)}/"
               f"{urllib.parse.quote(name)}/releases?limit={per_page}")
        data = _get_json(url, {"Accept": "application/json", "User-Agent": user_agent()},
                         self.timeout, self._open, f"{owner}/{name}", self.provider)
        if not isinstance(data, list):
            raise GitHubError(f"Unexpected response from {self.provider}.", "invalid")
        out = []
        for r in data:
            if not isinstance(r, dict):
                continue
            assets = [Asset(a.get("name", ""), a["browser_download_url"], int(a.get("size") or 0))
                      for a in r.get("assets") or []
                      if isinstance(a, dict) and _https(a.get("browser_download_url")) and a.get("name")]
            out.append(Release(tag=r.get("tag_name") or "", name=r.get("name") or "",
                               prerelease=bool(r.get("prerelease")), draft=bool(r.get("draft")),
                               published_at=r.get("published_at"), html_url=r.get("html_url"),
                               assets=assets))
        return out


class GitLabClient:
    """GitLab.com: ``/api/v4/projects/{url-encoded path}/releases``."""

    provider = "GitLab"

    def __init__(self, host: str = "gitlab.com", timeout: float = 20, opener=None):
        self.host, self.timeout, self._open = host, timeout, opener or _urlopen

    def releases(self, owner: str, name: str, per_page: int = 30) -> list[Release]:
        project = urllib.parse.quote(f"{owner}/{name}", safe="")
        url = f"https://{self.host}/api/v4/projects/{project}/releases?per_page={per_page}"
        data = _get_json(url, {"Accept": "application/json", "User-Agent": user_agent()},
                         self.timeout, self._open, f"{owner}/{name}", self.provider)
        if not isinstance(data, list):
            raise GitHubError(f"Unexpected response from {self.provider}.", "invalid")
        out = []
        for r in data:
            if not isinstance(r, dict):
                continue
            tag = r.get("tag_name") or ""
            links = ((r.get("assets") or {}).get("links")) or []
            assets = []
            for link in links:
                if not isinstance(link, dict):
                    continue
                href = link.get("direct_asset_url") or link.get("url")
                if not _https(href):
                    continue
                # the link "name" is a free-text label; the file name in the URL is what matters
                fname = urllib.parse.unquote(basename(urllib.parse.urlsplit(href).path)) or link.get("name") or ""
                assets.append(Asset(fname, href, 0))
            web = ((r.get("_links") or {}).get("self")) or f"https://{self.host}/{owner}/{name}/-/releases/{tag}"
            out.append(Release(tag=tag, name=r.get("name") or "",
                               prerelease=bool(r.get("upcoming_release")) or bool(_PRERELEASE_TAG.search(tag)),
                               published_at=r.get("released_at"), html_url=web, assets=assets))
        return out


def client_for(ref: SourceRef, github_token: str | None = None):
    """The release client for ``ref``. ``github_token`` is only ever given to GitHub."""
    if ref.provider == GITLAB:
        return GitLabClient()
    if ref.provider == CODEBERG:
        return ForgejoClient()
    return GitHubClient(token=github_token)


__all__ = ["SourceRef", "parse_source", "client_for", "GitLabClient", "ForgejoClient",
           "PROVIDER_NAMES", "SUPPORTED_HINT", "GITHUB", "GITLAB", "CODEBERG"]
