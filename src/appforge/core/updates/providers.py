"""Update sources: GitHub, GitLab.com, Codeberg and any self-hosted Forgejo/Gitea/GitLab server.

``parse_source`` understands repository URLs of the well-known hosts (plus ``owner/repo`` shorthand,
which means GitHub, as in earlier versions) and, since 0.5.4, ``https://`` URLs of *any other host*
such as ``https://git.example.dev/owner/repo``.  For those, ``SelfHostedClient`` works out at check
time which API the server speaks (Forgejo/Gitea, then GitLab) and remembers the answer.
Each client returns the same ``Release``/``Asset`` objects, so version comparison, asset choice and
installation are provider-independent.

Safety:
* a client only talks to its own API host, and a token is only ever sent to that host;
* asset links that are not ``https://`` are dropped (GitLab release links can point anywhere);
* repository URLs on hosts other than the three well-known ones must be ``https://``.
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

GITHUB, GITLAB, CODEBERG, CUSTOM = "github", "gitlab", "codeberg", "custom"
HOSTS = {"github.com": GITHUB, "gitlab.com": GITLAB, "codeberg.org": CODEBERG}
PROVIDER_NAMES = {GITHUB: "GitHub", GITLAB: "GitLab", CODEBERG: "Codeberg", CUSTOM: "Git server"}
SUPPORTED_HINT = ("https://github.com/owner/repo  (GitHub, GitLab, Codeberg and self-hosted "
                  "Forgejo/Gitea/GitLab servers such as https://git.example.dev/owner/repo are supported)")

_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_GITLAB_STOP = {"-", "releases", "tags", "blob", "tree", "issues", "merge_requests", "commits",
                "pipelines", "wikis", "raw", "archive"}
_HOSTNAME = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$")
_CUSTOM_PAGES = {"src", "releases", "tags", "commit", "pulls", "pull", "actions", "wiki", "projects",
                 "activity", "branches", "compare", "settings", "packages", "labels", "milestones"}
_PRERELEASE_TAG = re.compile(r"(?i)(?:^|[-._])(alpha|beta|rc|pre|preview)(?:[-._\d]|$)")


@dataclass(frozen=True)
class SourceRef:
    provider: str
    owner: str          # GitLab: the whole namespace, e.g. "group/subgroup"
    name: str
    host: str = ""      # filled in for the well-known providers; required for ``custom``

    def __post_init__(self):
        if not self.host:
            host = next((h for h, p in HOSTS.items() if p == self.provider), "")
            object.__setattr__(self, "host", host)

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
    if provider is None:                           # any other server: Forgejo/Gitea/GitLab/...
        if parts.scheme != "https" or not _HOSTNAME.match(host) or parts.username or parts.password:
            return None
        try:
            port = parts.port
        except ValueError:
            return None
        provider = CUSTOM
        host = f"{host}:{port}" if port and port != 443 else host
    segs = [urllib.parse.unquote(p) for p in parts.path.split("/") if p]
    if provider in (GITLAB, CUSTOM):               # both may use nested namespaces (group/sub/project)
        cut = next((i for i, p in enumerate(segs) if p in _GITLAB_STOP), len(segs))
        segs = segs[:cut]
        if provider == CUSTOM:
            # Forgejo/Gitea pages look like owner/repo/releases/tag/v1 or owner/repo/src/branch/main;
            # without a recognisable stop word we can't tell a subgroup from a page, so use two.
            segs = _custom_segments(segs)
    else:
        segs = segs[:2]
    if len(segs) < 2 or not all(_SEGMENT.match(p) and p not in (".", "..") for p in segs):
        return None
    name = segs[-1]
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not name:
        return None
    return SourceRef(provider, "/".join(segs[:-1]), name, host)


def _custom_segments(segs: list[str]) -> list[str]:
    """Namespace/project of a repository URL on an unknown host.

    Everything up to the first well-known page name (``releases``, ``src``, …) is kept, so both
    ``owner/repo`` (Forgejo, Gitea) and nested ``group/sub/project`` (GitLab) work.
    """
    cut = next((i for i, p in enumerate(segs) if p in _CUSTOM_PAGES), len(segs))
    return segs[:cut]


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

    def __init__(self, host: str = "codeberg.org", timeout: float = 20, opener=None,
                 label: str | None = None):
        self.host, self.timeout, self._open = host, timeout, opener or _urlopen
        if label:
            self.provider = label

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

    def __init__(self, host: str = "gitlab.com", timeout: float = 20, opener=None,
                 label: str | None = None):
        self.host, self.timeout, self._open = host, timeout, opener or _urlopen
        if label:
            self.provider = label

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


class SelfHostedClient:
    """A server we only know by its host name (e.g. ``git.example.dev``).

    Tries the Forgejo/Gitea API first, then GitLab's, and keeps whichever one answered so later
    checks go straight to it.  Network and rate-limit problems are reported immediately: they say
    nothing about which software the server runs.
    """

    def __init__(self, host: str, timeout: float = 20, opener=None):
        self.host = host
        label = host
        self._clients = [ForgejoClient(host, timeout, opener, label),
                         GitLabClient(host, timeout, opener, label)]
        self._working = None

    def releases(self, owner: str, name: str, per_page: int = 30) -> list[Release]:
        if self._working is not None:
            return self._working.releases(owner, name, per_page)
        first_error: GitHubError | None = None
        for client in self._clients:
            try:
                out = client.releases(owner, name, per_page)
            except GitHubError as exc:
                if exc.kind in ("network", "rate_limit"):
                    raise
                first_error = first_error or exc
                continue
            self._working = client
            return out
        raise GitHubError(
            f"{self.host} has no releases for {owner}/{name}: the repository wasn't found, it has no "
            f"public releases, or the server isn't a Forgejo, Gitea or GitLab server.",
            first_error.kind if first_error else "not_found")


def client_for(ref: SourceRef, github_token: str | None = None):
    """The release client for ``ref``. ``github_token`` is only ever given to GitHub."""
    if ref.provider == GITLAB:
        return GitLabClient()
    if ref.provider == CODEBERG:
        return ForgejoClient()
    if ref.provider == CUSTOM:
        return SelfHostedClient(ref.host)
    return GitHubClient(token=github_token)


__all__ = ["SourceRef", "parse_source", "client_for", "GitLabClient", "ForgejoClient",
           "SelfHostedClient", "PROVIDER_NAMES", "SUPPORTED_HINT", "GITHUB", "GITLAB", "CODEBERG",
           "CUSTOM"]
