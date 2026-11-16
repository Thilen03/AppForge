"""Checking one application for updates. Pure function: no database, safe on a worker thread."""
from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass, field

from ..models import UpdateStatus
from ..formats.appimage import version_from_filename
from .assets import choose_asset
from .github import GitHubError
from .providers import client_for, parse_source
from .version import compare, display_version, parse_version
from .installer import InstallError, find_expected_checksum, _hash_file
from .notes import release_notes


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
    prereleases_only: bool = False
    notes: dict | None = None
    comparison: str | None = None


def check_for_update(*, repo_url: str, installed_version: str | None, current_filename: str,
                     app_name: str, asset_pattern: str | None = None,
                     include_prereleases: bool = False,
                     client=None, token: str | None = None,
                     format_id: str = "appimage", installed_path: str | None = None) -> CheckOutcome:
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

    published = [r for r in releases if not r.draft]
    eligible = [r for r in published if include_prereleases or not r.prerelease]
    prereleases_only = bool(published) and not eligible
    chosen = None
    for rel in eligible:                     # provider APIs list newest first
        choice = choose_asset(rel, current_filename=current_filename, app_name=app_name,
                              pattern=asset_pattern, format_id=format_id)
        if choice:
            chosen = (rel, choice)
            break
    if chosen is None:
        newest = next(iter(eligible), None)
        what = "AppImage" if format_id == "appimage" else "matching Linux executable (raw binaries only)"
        if prereleases_only:
            newest = published[0]
            msg = ('Only pre-releases are available. Choose "Enable pre-releases" in the card menu, '
                   'or enable "Include pre-releases when checking for updates" in Edit. '
                   'Choosing a release asset also offers to enable pre-releases for this app.')
        else:
            if newest and asset_pattern:
                msg = (f"No {what} matching the saved file pattern was found. "
                       "Choose a release asset again or clear the pattern in Edit.")
            elif newest:
                msg = f"No {what} was found in the recent releases of this repository."
            else:
                msg = "This repository has no published releases."
        return CheckOutcome(UpdateStatus.UNAVAILABLE, msg,
                            release_url=newest.html_url if newest else None,
                            tag=newest.tag if newest else None,
                            release_assets=[a.to_dict() for a in (newest.assets if newest else [])],
                            prereleases_only=prereleases_only,
                            notes=release_notes(ref.url, newest) if newest else None)

    rel, choice = chosen
    latest = display_version(rel.tag)
    if parse_version(rel.tag) is None:
        # Rolling/channel tags often put the actual version in the title or file.
        latest = (version_from_filename(rel.name) or version_from_filename(choice.asset.name)
                  or latest)
    base = dict(notes=release_notes(ref.url, rel), latest_version=latest, tag=rel.tag, release_url=rel.html_url,
                asset=choice.asset.to_dict(), ambiguous=choice.ambiguous,
                candidates=[a.to_dict() for a in choice.candidates],
                release_assets=[a.to_dict() for a in rel.assets])
    # Existing records may predate numbered-nightly filename detection. Use only
    # the known filename fallback when the installed version has not been set.
    installed_version = installed_version or version_from_filename(current_filename)
    cmp = compare(latest, installed_version)
    if cmp is not None and (cmp != 0 or parse_version(rel.tag) is not None):
        return CheckOutcome(UpdateStatus.UPDATE_AVAILABLE if cmp > 0 else UpdateStatus.UP_TO_DATE,
                            "", **base)

    # A hash identifies bytes, not version ordering. Never use a mismatch to
    # override a comparable version (in particular, never offer a downgrade).
    if installed_path and not choice.ambiguous:
        try:
            expected = find_expected_checksum(base["asset"], base["release_assets"])
            if expected:
                algo, want = expected
                path = Path(installed_path)
                before = path.stat()
                got = _hash_file(path, algo)
                after = path.stat()
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    return CheckOutcome(UpdateStatus.UNAVAILABLE,
                                        "The installed file changed during comparison. Check again.", **base)
                if got == want:
                    return CheckOutcome(UpdateStatus.UP_TO_DATE,
                                        f"The installed file matches the release's {algo.upper()} checksum.",
                                        comparison="checksum", **base)
                return CheckOutcome(UpdateStatus.UPDATE_AVAILABLE,
                                    "The release file differs from the installed file (published checksum). "
                                    "Version ordering is unknown; review the release before updating.",
                                    comparison="checksum", **base)
        except InstallError as exc:
            return CheckOutcome(UpdateStatus.UNAVAILABLE, str(exc), **base)
        except OSError:
            return CheckOutcome(UpdateStatus.UNAVAILABLE,
                                "The installed file could not be read for checksum comparison.", **base)
    if cmp == 0:
        return CheckOutcome(UpdateStatus.UP_TO_DATE,
                            "The version matches, but no usable checksum comparison is available "
                            "to detect rebuilt release files.", **base)
    if not installed_version:
        message = ("The installed version is unknown and no usable checksum comparison is available. "
                   "Set the installed version in Edit to compare versions.")
    else:
        message = (f"Can't compare “{installed_version}” with release “{rel.tag}”, and no usable "
                   "checksum comparison is available. Check the installed version in Edit.")
    if choice.ambiguous:
        message += " Choose the correct release asset first."
    return CheckOutcome(UpdateStatus.UNAVAILABLE, message, **base)
