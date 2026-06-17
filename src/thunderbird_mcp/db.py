"""Read-only queries over the Thunderbird GLODA snapshot.

GLODA stores its full-text index with a custom ``mozporter`` tokenizer that is not
available in a standalone Python ``sqlite3`` build, so we cannot use the FTS table
directly. Instead we run ``LIKE`` queries against ``messagesText_content``, which
GLODA keeps populated with precomputed columns:

    c0body, c1subject, c2attachmentNames, c3author, c4recipients

Relevant schema:
    messages(id, folderID, conversationID, date, headerMessageID, deleted, ...)
    messagesText_content(docid, c0body, c1subject, c2attachmentNames, c3author, c4recipients)
    folderLocations(id, folderURI, name)
"""

from __future__ import annotations

import sqlite3
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from thunderbird_mcp import snapshot

# Shared SELECT column list.
_BASE_COLS = """
    m.id              AS message_id,
    m.conversationID  AS conversation_id,
    m.date            AS date_us,
    m.headerMessageID AS header_message_id,
    fl.name           AS folder,
    fl.folderURI      AS folder_uri,
    mt.c1subject      AS subject,
    mt.c3author       AS author,
    mt.c4recipients   AS recipients,
    mt.c2attachmentNames AS attachments,
    mt.c0body         AS body
"""


def _con() -> sqlite3.Connection:
    snapshot.ensure_fresh(max_age=900)
    con = sqlite3.connect(
        f"file:{snapshot.snapshot_path()}?mode=ro", uri=True, timeout=10
    )
    con.row_factory = sqlite3.Row
    return con


def _us_to_iso(date_us: int | None) -> str | None:
    """GLODA stores dates as microseconds since the Unix epoch."""
    if not date_us:
        return None
    return datetime.fromtimestamp(date_us / 1_000_000, tz=timezone.utc).isoformat()


def _iso_to_us(s: str) -> int:
    """Accept ``YYYY-MM-DD`` or a full ISO timestamp; return microseconds."""
    s = s.strip()
    if len(s) == 10:
        s += "T00:00:00+00:00"
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000)


def _account_from_uri(uri: str | None) -> str | None:
    """Extract the account email from a folder URI.

    e.g. ``imap://alice%40example.com@mail.example.com/INBOX`` -> ``alice@example.com``
    """
    if not uri:
        return None
    parsed = urllib.parse.urlparse(uri)
    if parsed.username:
        return urllib.parse.unquote(parsed.username)
    return None


def _row_to_dict(r: sqlite3.Row, *, body_chars: int = 600) -> dict[str, Any]:
    body = r["body"] or ""
    return {
        "message_id": r["message_id"],
        "conversation_id": r["conversation_id"],
        "date": _us_to_iso(r["date_us"]),
        "header_message_id": r["header_message_id"],
        "folder": r["folder"],
        "account": _account_from_uri(r["folder_uri"]),
        "subject": r["subject"] or "",
        "author": r["author"] or "",
        "recipients": r["recipients"] or "",
        "attachments": r["attachments"] or "",
        "body_preview": body[:body_chars],
        "body_length": len(body),
    }


def search(
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
    from_addr: str | None = None,
    to_addr: str | None = None,
    account: str | None = None,
    folder: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search messages by content, headers, date, account or folder.

    ``query`` matches subject + body + attachment names (LIKE ``%query%``).
    Results are ordered most-recent-first.
    """
    where = ["m.deleted = 0"]
    params: list[Any] = []

    if query:
        like = f"%{query}%"
        where.append(
            "(mt.c0body LIKE ? OR mt.c1subject LIKE ? OR mt.c2attachmentNames LIKE ?)"
        )
        params += [like, like, like]
    if from_addr:
        where.append("mt.c3author LIKE ?")
        params.append(f"%{from_addr}%")
    if to_addr:
        where.append("mt.c4recipients LIKE ?")
        params.append(f"%{to_addr}%")
    if folder:
        where.append("fl.name LIKE ?")
        params.append(f"%{folder}%")
    if account:
        # The email is URL-encoded inside folderURI (alice@x -> alice%40x).
        enc = urllib.parse.quote(account, safe="")
        where.append("fl.folderURI LIKE ?")
        params.append(f"%{enc}%")
    if since:
        where.append("m.date >= ?")
        params.append(_iso_to_us(since))
    if until:
        where.append("m.date <= ?")
        params.append(_iso_to_us(until))

    sql = f"""
    SELECT {_BASE_COLS}
    FROM messages m
    JOIN messagesText_content mt ON mt.docid = m.id
    LEFT JOIN folderLocations fl ON fl.id = m.folderID
    WHERE {' AND '.join(where)}
    ORDER BY m.date DESC
    LIMIT ?
    """
    params.append(int(limit))

    with _con() as con:
        return [_row_to_dict(r) for r in con.execute(sql, params).fetchall()]


def recent_by_address(email_or_domain: str, limit: int = 20) -> list[dict]:
    """Messages (incoming and outgoing) involving an address or domain."""
    like = f"%{email_or_domain}%"
    sql = f"""
    SELECT {_BASE_COLS}
    FROM messages m
    JOIN messagesText_content mt ON mt.docid = m.id
    LEFT JOIN folderLocations fl ON fl.id = m.folderID
    WHERE m.deleted = 0 AND (mt.c3author LIKE ? OR mt.c4recipients LIKE ?)
    ORDER BY m.date DESC
    LIMIT ?
    """
    with _con() as con:
        return [
            _row_to_dict(r)
            for r in con.execute(sql, [like, like, int(limit)]).fetchall()
        ]


def get_message(message_id: int, body_chars: int = 50_000) -> dict | None:
    """Return one message by id with its full body (up to ``body_chars``)."""
    sql = f"""
    SELECT {_BASE_COLS}
    FROM messages m
    JOIN messagesText_content mt ON mt.docid = m.id
    LEFT JOIN folderLocations fl ON fl.id = m.folderID
    WHERE m.id = ?
    """
    with _con() as con:
        r = con.execute(sql, [int(message_id)]).fetchone()
    return _row_to_dict(r, body_chars=body_chars) if r else None


def thread(conversation_id: int, body_chars: int = 1_500) -> list[dict]:
    """All messages in a conversation, oldest first."""
    sql = f"""
    SELECT {_BASE_COLS}
    FROM messages m
    JOIN messagesText_content mt ON mt.docid = m.id
    LEFT JOIN folderLocations fl ON fl.id = m.folderID
    WHERE m.deleted = 0 AND m.conversationID = ?
    ORDER BY m.date ASC
    """
    with _con() as con:
        rows = con.execute(sql, [int(conversation_id)]).fetchall()
    return [_row_to_dict(r, body_chars=body_chars) for r in rows]


def folders() -> list[dict]:
    """Known folders with inferred account and message count."""
    sql = """
    SELECT fl.id, fl.name, fl.folderURI, COUNT(m.id) AS count
    FROM folderLocations fl
    LEFT JOIN messages m ON m.folderID = fl.id AND m.deleted = 0
    GROUP BY fl.id
    ORDER BY count DESC
    """
    with _con() as con:
        rows = con.execute(sql).fetchall()
    return [
        {
            "name": r["name"],
            "uri": r["folderURI"],
            "account": _account_from_uri(r["folderURI"]),
            "count": r["count"],
        }
        for r in rows
    ]


def stats() -> dict:
    """Total message count and date range of the index."""
    with _con() as con:
        total = con.execute("SELECT COUNT(*) FROM messages WHERE deleted=0").fetchone()[
            0
        ]
        oldest = con.execute(
            "SELECT MIN(date) FROM messages WHERE deleted=0"
        ).fetchone()[0]
        newest = con.execute(
            "SELECT MAX(date) FROM messages WHERE deleted=0"
        ).fetchone()[0]
    return {
        "messages": total,
        "oldest": _us_to_iso(oldest),
        "newest": _us_to_iso(newest),
    }
