"""Checking one application for updates. Pure function: no database, safe on a worker thread."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..models import UpdateStatus
from .assets import choose_asset
from .github import GitHubError
from .providers import client_for, parse_source
from .version import compare, display_version


@dataclass
class CheckOutcome:
    status: UpdateStatus
    message: str = ""
    latest_version: str | None = None
    tag: str | None = None
    release_url: str | None = None
    asset: dict | None = None            # chosen asset {name,url,size,digest}
    ambiguous: bool = False
    candidates: list[dict] = field(default_factory=list)       # AppImage candidates
    release_assets: list[dict] = field(default_factory=list)   # every asset of the chosen release
    checked_at: float = field(default_factory=time.time)


def check_for_update(*, repo_url: str, installed_version: str | None, current_filename: str,
                     app_name: str, asset_pattern: str | None = None,
                     include_prereleases: bool = False,
                     client=None, token: str | None = None,
                     format_id: str = "appimage") -> CheckOutcome:
    """``client`` (anything with ``releases(owner, name)``) overrides the provider's own client;
    ``token`` is only ever used for GitHub."""
    ref = parse_source(repo_url)
    if ref is None:
        return CheckOutcome(UpdateStatus.FAILED, "The update source URL isn't valid.")
    client = client or client_for(ref, token)
    try:
        releases = client.releases(ref.owner, ref.name)
    except GitHubError as exc:
        return CheckOutcome(UpdateStatus.FAILED, str(exc))

    candidates_seen = False
    chosen = None
    for rel in releases:                     # GitHub lists newest first
        if rel.draft or (rel.prerelease and not include_prereleases):
            continue
        choice = choose_asset(rel, current_filename=current_filename, app_name=app_name,
                              pattern=asset_pattern, format_id=format_id)
        if choice:
            chosen = (rel, choice)
            break
        candidates_seen = candidates_seen or bool(rel.assets)
    if chosen is None:
        newest = next((r for r in releases if not r.draft and (include_prereleases or not r.prerelease)), None)
        what = "AppImage" if format_id == "appimage" else "matching Linux executable (raw binaries only)"
        msg = (f"No {what} was found in the recent releases of this repository." if newest
               else "This repository has no published releases.")
        return CheckOutcome(UpdateStatus.UNAVAILABLE, msg,
                            release_url=newest.html_url if newest else None,
                            tag=newest.tag if newest else None,
                            release_assets=[a.to_dict() for a in (newest.assets if newest else [])])

    rel, choice = chosen
    latest = display_version(rel.tag)
    base = dict(latest_version=latest, tag=rel.tag, release_url=rel.html_url,
                asset=choice.asset.to_dict(), ambiguous=choice.ambiguous,
                candidates=[a.to_dict() for a in choice.candidates],
                release_assets=[a.to_dict() for a in rel.assets])
    if not installed_version:
        return CheckOutcome(UpdateStatus.UNAVAILABLE,
                            "The installed version is unknown. Set it in Edit to enable update checks.", **base)
    cmp = compare(latest, installed_version)
    if cmp is None:
        if latest.strip().lower() == installed_version.strip().lower():
            return CheckOutcome(UpdateStatus.UP_TO_DATE, "", **base)
        return CheckOutcome(UpdateStatus.UNAVAILABLE,
                            f"Can't compare “{installed_version}” with release “{rel.tag}”.", **base)
    if cmp > 0:
        return CheckOutcome(UpdateStatus.UPDATE_AVAILABLE, "", **base)
    return CheckOutcome(UpdateStatus.UP_TO_DATE, "", **base)
