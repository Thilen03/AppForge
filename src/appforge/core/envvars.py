"""Per-application environment variables (Qt-free).

The same variables are used in two places, so they can never drift apart:

* written into the application-menu launcher as ``Exec=env NAME=value … /path/to/app`` – exactly
  what KDE's own menu editor does – and
* applied to the process AppForge starts when you press *Launch*.

Stored in ``entry.metadata["env_vars"]`` as a ``{name: value}`` dict (insertion order is kept).
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

ENV_KEY = "env_vars"
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BAD_VALUE_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_VARS = 64
MAX_VALUE_LEN = 4096


class EnvVarError(ValueError):
    """User-presentable problem with an environment variable definition."""


def validate_pair(name: str, value: str) -> tuple[str, str]:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise EnvVarError(f"“{name or '…'}” isn't a valid variable name (letters, digits and _, "
                          "not starting with a digit).")
    if _BAD_VALUE_RE.search(value):
        raise EnvVarError(f"The value of {name} contains control characters.")
    if len(value) > MAX_VALUE_LEN:
        raise EnvVarError(f"The value of {name} is too long.")
    return name, value


def parse_env_text(text: str | None) -> dict[str, str]:
    """Parse ``NAME=value`` lines (blank lines and ``#`` comments ignored). Raises :class:`EnvVarError`.

    Everything after the first ``=`` is the value, verbatim (spaces and further ``=`` are kept).
    A later line for the same name replaces an earlier one.
    """
    result: dict[str, str] = {}
    for number, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvVarError(f"Line {number}: use NAME=value.")
        name, value = line.split("=", 1)
        try:
            name, value = validate_pair(name, value.strip())
        except EnvVarError as exc:
            raise EnvVarError(f"Line {number}: {exc}") from exc
        result.pop(name, None)       # a repeated name moves to the end, last value wins
        result[name] = value
    if len(result) > MAX_VARS:
        raise EnvVarError(f"At most {MAX_VARS} variables are supported.")
    return result


def format_env_text(env: Mapping[str, str] | None) -> str:
    return "\n".join(f"{k}={v}" for k, v in (env or {}).items())


def clean_env(raw: object) -> dict[str, str]:
    """Normalise whatever is stored in metadata; silently drops invalid entries."""
    out: dict[str, str] = {}
    if isinstance(raw, Mapping):
        items: Iterable = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = [p for p in raw if isinstance(p, (list, tuple)) and len(p) == 2]
    else:
        return out
    for k, v in items:
        try:
            name, value = validate_pair(str(k), str(v))
        except EnvVarError:
            continue
        out[name] = value
    return out


def env_of(entry) -> dict[str, str]:
    """The environment variables configured for ``entry`` (may be empty)."""
    return clean_env(entry.metadata.get(ENV_KEY))


__all__ = ["ENV_KEY", "EnvVarError", "parse_env_text", "format_env_text", "clean_env", "env_of",
           "validate_pair"]
