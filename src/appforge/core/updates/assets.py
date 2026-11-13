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


# Files that are never a bare executable (archives, packages, other platforms, metadata).
_NOT_EXECUTABLE_SUFFIXES = _IGNORED_SUFFIXES + (
    ".zip", ".tar", ".gz", ".tgz", ".xz", ".txz", ".bz2", ".tbz", ".zst", ".7z", ".deb", ".rpm",
    ".apk", ".pkg", ".dmg", ".msi", ".exe", ".snap", ".flatpak", ".appimage", ".pem", ".pub", ".sbom",
    ".spdx", ".intoto", ".jsonl", ".crt", ".html", ".pdf", ".sh", ".ps1", ".bat", ".dll", ".so",
    ".dylib", ".a", ".whl", ".jar", ".asc")
_OTHER_OS = {"windows", "win", "win32", "win64", "darwin", "macos", "osx", "mac", "freebsd",
             "openbsd", "netbsd", "android", "ios", "apple", "msvc"}


def is_executable_name(name: str) -> bool:
    """A release file that could be a raw Linux binary (not an archive, package or checksum)."""
    low = name.lower()
    if low.endswith(_NOT_EXECUTABLE_SUFFIXES) or "checksum" in low or "sha256" in low:
        return False
    return not (_tokens(low) & _OTHER_OS)


def is_candidate_name(name: str, format_id: str = "appimage") -> bool:
    return is_executable_name(name) if format_id == "executable" else is_appimage_name(name)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t}


@dataclass
class AssetChoice:
    asset: Asset
    ambiguous: bool            # several equally good candidates – ask the user
    candidates: list[Asset]


def score_asset(asset: Asset, *, current_filename: str, app_name: str, pattern: str | None,
                arch: str, format_id: str = "appimage") -> int:
    toks = _tokens(asset.name)
    mine = set(_ARCH_ALIASES.get(arch, (arch,)))
    score = 0
    if format_id == "executable" and "linux" in toks:
        score += 20                       # raw binaries are often named tool-linux-amd64
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
                 pattern: str | None = None, arch: str | None = None,
                 format_id: str = "appimage") -> AssetChoice | None:
    arch = arch or host_arch()
    cands = [a for a in release.assets if is_candidate_name(a.name, format_id)]
    if pattern:
        matched = [a for a in cands if fnmatch.fnmatchcase(a.name.lower(), pattern.lower())]
        if len(matched) == 1:
            return AssetChoice(matched[0], False, cands)
    scored = sorted(((score_asset(a, current_filename=current_filename, app_name=app_name,
                                  pattern=pattern, arch=arch, format_id=format_id), a) for a in cands),
                    key=lambda t: (-t[0], t[1].name))
    scored = [(s, a) for s, a in scored if s > -50]   # drop wrong-architecture builds
    if not scored:
        return None
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    return AssetChoice(scored[0][1], ambiguous, [a for _, a in scored])
