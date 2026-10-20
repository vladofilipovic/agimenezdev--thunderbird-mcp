"""Read-only MCP server over Thunderbird's local mail index (GLODA).

Exposes tools to search and read email from any MCP client (Claude Desktop,
Claude Code, the Agent SDK, etc.) without touching IMAP or credentials — it reads
an atomic snapshot of Thunderbird's own SQLite index.

Run:
    thunderbird-mcp
    # or: python -m thunderbird_mcp.server
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from thunderbird_mcp import accounts, db

mcp = FastMCP("thunderbird")


@mcp.tool()
def tb_list_accounts() -> dict[str, Any]:
    """List the mail accounts configured in Thunderbird (parsed from prefs.js).

    Returns the configured emails plus the IMAP hostnames/usernames of each server.
    """
    return accounts.load_accounts()


@mcp.tool()
def tb_stats() -> dict[str, Any]:
    """Index stats: total indexed messages and the date range they span."""
    return db.stats()


@mcp.tool()
def tb_folders() -> list[dict]:
    """List known folders (INBOX, Sent, local folders, ...) with per-folder counts."""
    return db.folders()


@mcp.tool()
def tb_search(
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
    from_addr: str | None = None,
    to_addr: str | None = None,
    account: str | None = None,
    folder: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search the Thunderbird index.

    Args:
        query: text to match in subject + body + attachment names (LIKE %query%).
        since: ISO date, inclusive (YYYY-MM-DD or a full ISO timestamp).
        until: ISO date, inclusive.
        from_addr: filter by sender (substring of the From header).
        to_addr: filter by recipient (substring of To/Cc/Bcc).
        account: account email (e.g. "alice@example.com"); filters by folder URI.
        folder: folder name (e.g. "Inbox", "Sent").
        limit: max results (default 20, keep <= 50).

    Returns matches ordered newest-first, each with a 600-char body preview.
    Use tb_get_message for the full body.
    """
    return db.search(
        query=query,
        since=since,
        until=until,
        from_addr=from_addr,
        to_addr=to_addr,
        account=account,
        folder=folder,
        limit=limit,
    )


@mcp.tool()
def tb_recent_by_address(email_or_domain: str, limit: int = 20) -> list[dict]:
    """History of messages with a contact or domain (incoming and outgoing).

    Useful to reconstruct the context of a conversation before replying.

    Args:
        email_or_domain: e.g. "alice@example.com", "example.com" or "@example.com".
        limit: max results (default 20).
    """
    return db.recent_by_address(email_or_domain, limit=limit)


@mcp.tool()
def tb_get_message(message_id: int, body_chars: int = 50_000) -> dict | None:
    """Fetch a single message by id with its full body (up to body_chars)."""
    return db.get_message(message_id, body_chars=body_chars)


@mcp.tool()
def tb_thread(conversation_id: int, body_chars: int = 1500) -> list[dict]:
    """All messages in a conversation, oldest first.

    body_chars caps the body length per message (default 1500) to keep the
    response small for long threads.
    """
    return db.thread(conversation_id, body_chars=body_chars)


def main() -> None:
    try:
        mcp.run()
    except KeyboardInterrupt:
        try:
            print("MCP server stopped.", file=sys.stderr)
        except Exception:
            pass
        return 130

if __name__ == "__main__":
    main()
