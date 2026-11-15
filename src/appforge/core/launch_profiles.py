"""Named launch configurations. The existing root configuration is always Default."""
from copy import deepcopy
from dataclasses import replace
import re

from .envvars import ENV_KEY, MAX_VARS, validate_pair
from .launch_options import LAUNCH_KEYS, LaunchOptionsError, validate_launch_options

PROFILES_KEY = "launch_profiles"
DEFAULT_PROFILE = "default"
MAX_PROFILES = 32
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_environment(raw):
    if not isinstance(raw, dict) or len(raw) > MAX_VARS:
        raise LaunchOptionsError(f"Environment must contain at most {MAX_VARS} variables.")
    result = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise LaunchOptionsError("Environment names and values must be text.")
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise LaunchOptionsError("Environment values cannot contain invalid Unicode characters.")
        try:
            clean, value = validate_pair(name, value)
        except ValueError as exc:
            raise LaunchOptionsError(str(exc)) from exc
        if clean != name:
            raise LaunchOptionsError("Environment names cannot contain surrounding whitespace.")
        result[clean] = value
    return result


def validate_profiles(raw):
    if not isinstance(raw, list) or len(raw) > MAX_PROFILES:
        raise LaunchOptionsError(f"Use at most {MAX_PROFILES} additional launch profiles.")
    result, ids, names = [], {DEFAULT_PROFILE}, {DEFAULT_PROFILE}
    for profile in raw:
        if not isinstance(profile, dict) or set(profile) - (LAUNCH_KEYS | {'id', 'name', ENV_KEY}):
            raise LaunchOptionsError("Unsupported launch profile fields.")
        ident, name = profile.get('id'), profile.get('name')
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in ids:
            raise LaunchOptionsError("Launch profile IDs must be valid and unique.")
        if (not isinstance(name, str) or not name.strip() or len(name) > 64
                or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in name)):
            raise LaunchOptionsError("Profile names must contain 1–64 characters without control characters.")
        name = name.strip()
        if name.casefold() in names:
            raise LaunchOptionsError("Use a unique profile name; Default is reserved.")
        options = validate_launch_options({k: v for k, v in profile.items() if k in LAUNCH_KEYS})
        env = validate_environment(profile.get(ENV_KEY, {}))
        result.append({'id': ident, 'name': name, **options, ENV_KEY: env})
        ids.add(ident)
        names.add(name.casefold())
    return result


def profiles_of(entry):
    return validate_profiles(entry.metadata.get(PROFILES_KEY, []))


def profile_choices(entry):
    # Corrupt optional metadata must not prevent opening the library or Default.
    try:
        return [(DEFAULT_PROFILE, "Default"), *((p['id'], p['name']) for p in profiles_of(entry))]
    except LaunchOptionsError:
        return [(DEFAULT_PROFILE, "Default")]


def entry_for_profile(entry, profile_id=DEFAULT_PROFILE):
    if profile_id == DEFAULT_PROFILE:
        return entry
    profile = next((p for p in profiles_of(entry) if p['id'] == profile_id), None)
    if profile is None:
        raise LaunchOptionsError("That launch profile no longer exists. Choose another profile.")
    metadata = deepcopy(entry.metadata)
    for key in LAUNCH_KEYS | {ENV_KEY}:
        metadata.pop(key, None)
    metadata.update({k: deepcopy(v) for k, v in profile.items() if k in LAUNCH_KEYS or k == ENV_KEY})
    return replace(entry, metadata=metadata)
