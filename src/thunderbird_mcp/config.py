"""Locate the active Thunderbird profile directory across platforms.

Resolution order:

1. ``THUNDERBIRD_PROFILE`` — an absolute path to a profile directory. Use this
   when Thunderbird lives on a different filesystem than the server, e.g. running
   under WSL against a Windows install, or pointing at a backup.
2. The default profile recorded in Thunderbird's ``profiles.ini``, searched in the
   standard per-platform locations.

A "profile directory" is the folder that contains ``global-messages-db.sqlite``
and ``prefs.js``.
"""

from __future__ import annotations

import configparser
import os
import sys
from functools import lru_cache
from pathlib import Path


def _candidate_roots() -> list[Path]:
    """Standard locations of Thunderbird's ``profiles.ini`` per platform."""
    home = Path.home()
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        return [Path(appdata) / "Thunderbird"] if appdata else []
    if sys.platform == "darwin":
        return [home / "Library" / "Thunderbird"]
    # Linux / other unix, including the Snap and Flatpak sandboxes.
    return [
        home / ".thunderbird",
        home / ".mozilla-thunderbird",
        home / "snap" / "thunderbird" / "common" / ".thunderbird",
        home / ".var" / "app" / "org.mozilla.Thunderbird" / ".thunderbird",
    ]


def _profile_from_ini(root: Path) -> Path | None:
    """Resolve the default profile path declared in ``root/profiles.ini``."""
    ini = root / "profiles.ini"
    if not ini.exists():
        return None

    cp = configparser.ConfigParser()
    cp.read(ini, encoding="utf-8")

    # Prefer the [InstallXXXX] Default= entry: that's the profile Thunderbird
    # actually launches when several profiles exist.
    for section in cp.sections():
        if section.startswith("Install") and cp.has_option(section, "Default"):
            path = root / cp.get(section, "Default")
            if path.exists():
                return path

    # Fall back to the [ProfileN] flagged Default=1, else the first one declared.
    fallback: Path | None = None
    for section in cp.sections():
        if not section.startswith("Profile") or not cp.has_option(section, "Path"):
            continue
        rel = cp.get(section, "Path")
        is_relative = cp.getboolean(section, "IsRelative", fallback=True)
        path = (root / rel) if is_relative else Path(rel)
        if cp.getboolean(section, "Default", fallback=False):
            return path
        fallback = fallback or path
    return fallback


@lru_cache(maxsize=1)
def profile_dir() -> Path:
    """Return the resolved Thunderbird profile directory.

    Raises:
        FileNotFoundError: if no profile can be located and no override is set.
    """
    override = os.environ.get("THUNDERBIRD_PROFILE")
    if override:
        path = Path(override).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"THUNDERBIRD_PROFILE points to a missing directory: {path}"
            )
        return path

    for root in _candidate_roots():
        profile = _profile_from_ini(root)
        if profile and profile.exists():
            return profile

    raise FileNotFoundError(
        "Could not locate a Thunderbird profile automatically. Set the "
        "THUNDERBIRD_PROFILE environment variable to your profile directory "
        "(the folder containing global-messages-db.sqlite)."
    )


def database_path() -> Path:
    """Path to the GLODA global message index inside the active profile."""
    return profile_dir() / "global-messages-db.sqlite"


def prefs_path() -> Path:
    """Path to ``prefs.js`` inside the active profile."""
    return profile_dir() / "prefs.js"
