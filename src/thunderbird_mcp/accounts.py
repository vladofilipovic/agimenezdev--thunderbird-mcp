"""Parse Thunderbird's ``prefs.js`` to map identities and servers to accounts."""

from __future__ import annotations

import re
from functools import lru_cache

from thunderbird_mcp import config

_PAT_ID_EMAIL = re.compile(r'mail\.identity\.(id\d+)\.useremail",\s*"([^"]+)"')
_PAT_SERVER_HOST = re.compile(r'mail\.server\.(server\d+)\.hostname",\s*"([^"]+)"')
_PAT_SERVER_USER = re.compile(r'mail\.server\.(server\d+)\.userName",\s*"([^"]+)"')


def parse_prefs(text: str) -> dict:
    """Extract account info from the contents of a ``prefs.js`` file.

    Returns a dict with:
        emails:  sorted list of configured email addresses
        by_id:   {identity_id: {"email": ...}}
        servers: {server_id: {"hostname": ..., "username": ...}}
    """
    by_id: dict[str, dict] = {
        ident: {"email": email} for ident, email in _PAT_ID_EMAIL.findall(text)
    }

    servers: dict[str, dict] = {}
    for srv, host in _PAT_SERVER_HOST.findall(text):
        servers.setdefault(srv, {})["hostname"] = host
    for srv, user in _PAT_SERVER_USER.findall(text):
        servers.setdefault(srv, {})["username"] = user

    emails = sorted({v["email"] for v in by_id.values()})
    return {"emails": emails, "by_id": by_id, "servers": servers}


@lru_cache(maxsize=1)
def load_accounts() -> dict:
    """Read and parse the active profile's ``prefs.js`` (empty result if absent)."""
    prefs = config.prefs_path()
    if not prefs.exists():
        return {"emails": [], "by_id": {}, "servers": {}}
    return parse_prefs(prefs.read_text(encoding="utf-8", errors="ignore"))


def list_emails() -> list[str]:
    return load_accounts()["emails"]
