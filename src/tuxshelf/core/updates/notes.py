"""Read-only release descriptions, keyed by canonical source and exact tag."""
from __future__ import annotations

from .github import GitHubError, Release
from .providers import client_for, parse_source


def release_notes(source: str, release: Release) -> dict:
    return dict(source=source, tag=release.tag, title=release.name, body=release.body,
                published_at=release.published_at, url=release.html_url,
                prerelease=release.prerelease)


def notes_identity(entry) -> tuple[str, str]:
    ref = parse_source(entry.github_repo)
    return (ref.url if ref else "", (entry.metadata.get("update") or {}).get("tag") or "")


def cached_notes(entry) -> dict | None:
    source, tag = notes_identity(entry)
    notes = (entry.metadata.get("update") or {}).get("notes")
    if isinstance(notes, dict) and source and tag and (notes.get("source"), notes.get("tag")) == (source, tag):
        return notes
    return None


def fetch_notes(source: str, tag: str, *, client=None, token=None) -> dict:
    ref = parse_source(source)
    if ref is None or not tag:
        raise GitHubError("Check for updates first to select a release.", "invalid")
    for release in (client or client_for(ref, token)).releases(ref.owner, ref.name):
        if release.tag == tag and not release.draft:
            return release_notes(ref.url, release)
    raise GitHubError("This release is no longer in the provider's recent releases. "
                      "Open the original release page or check for updates again.", "not_found")
