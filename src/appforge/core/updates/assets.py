"""Choosing the right AppImage among a release's assets."""
from __future__ import annotations

import fnmatch
import platform
import re
from dataclasses import dataclass

from .github import Asset, Release

_IGNORED_SUFFIXES = (".zsync", ".sha256", ".sha256sum", ".sha512", ".sig", ".asc", ".digest",
                     ".txt", ".yml", ".yaml", ".json", ".md5", ".blockmap")
_ARCH_ALIASES = {
    "x86_64": ("x86_64", "x86-64", "amd64", "x64"),
    "aarch64": ("aarch64", "arm64", "armv8"),
    "armv7l": ("armhf", "armv7", "arm32"),
    "i686": ("i686", "i386", "ia32"),
}
_ALL_ARCH_TOKENS = {t for toks in _ARCH_ALIASES.values() for t in toks} | {"ppc64le", "riscv64", "s390x"}


def host_arch() -> str:
    m = platform.machine().lower()
    return "x86_64" if m in ("x86_64", "amd64") else m


def is_appimage_name(name: str) -> bool:
    low = name.lower()
    return ".appimage" in low and not low.endswith(_IGNORED_SUFFIXES)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t}


@dataclass
class AssetChoice:
    asset: Asset
    ambiguous: bool            # several equally good candidates – ask the user
    candidates: list[Asset]


def score_asset(asset: Asset, *, current_filename: str, app_name: str, pattern: str | None,
                arch: str) -> int:
    toks = _tokens(asset.name)
    mine = set(_ARCH_ALIASES.get(arch, (arch,)))
    score = 0
    if toks & mine:
        score += 50
    elif toks & (_ALL_ARCH_TOKENS - mine):
        score -= 100                      # clearly built for another architecture
    # similarity to the file the user already has / the app's name
    known = _tokens(re.sub(r"\d+(?:[._]\d+)*", " ", current_filename)) | _tokens(app_name)
    score += 5 * len(toks & known)
    if pattern and fnmatch.fnmatchcase(asset.name.lower(), pattern.lower()):
        score += 200
    return score


def choose_asset(release: Release, *, current_filename: str, app_name: str,
                 pattern: str | None = None, arch: str | None = None) -> AssetChoice | None:
    arch = arch or host_arch()
    cands = [a for a in release.assets if is_appimage_name(a.name)]
    if pattern:
        matched = [a for a in cands if fnmatch.fnmatchcase(a.name.lower(), pattern.lower())]
        if len(matched) == 1:
            return AssetChoice(matched[0], False, cands)
    scored = sorted(((score_asset(a, current_filename=current_filename, app_name=app_name,
                                  pattern=pattern, arch=arch), a) for a in cands),
                    key=lambda t: (-t[0], t[1].name))
    scored = [(s, a) for s, a in scored if s > -50]   # drop wrong-architecture builds
    if not scored:
        return None
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    return AssetChoice(scored[0][1], ambiguous, [a for _, a in scored])
