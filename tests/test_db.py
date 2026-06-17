"""Query layer tested against a synthetic GLODA-shaped snapshot."""

import sqlite3

import pytest

from thunderbird_mcp import db, snapshot

# Microseconds-since-epoch timestamps (GLODA's format).
_JAN = 1_700_000_000_000_000  # ~2023-11-14
_FEB = 1_705_000_000_000_000  # ~2024-01-11


def _build_snapshot(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE folderLocations (id INTEGER PRIMARY KEY, folderURI TEXT, name TEXT);
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY, folderID INTEGER, conversationID INTEGER,
            date INTEGER, headerMessageID TEXT, deleted INTEGER
        );
        CREATE TABLE messagesText_content (
            docid INTEGER PRIMARY KEY, c0body TEXT, c1subject TEXT,
            c2attachmentNames TEXT, c3author TEXT, c4recipients TEXT
        );
        """)
    con.execute(
        "INSERT INTO folderLocations VALUES (1, 'imap://alice%40example.com@imap.example.com/INBOX', 'Inbox')"
    )
    rows = [
        # id, folder, conv, date, hdr, deleted
        (1, 1, 100, _JAN, "<m1@example.com>", 0),
        (2, 1, 100, _FEB, "<m2@example.com>", 0),
        (3, 1, 200, _FEB, "<m3@example.com>", 1),  # deleted
    ]
    con.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)", rows)
    text = [
        (
            1,
            "Quote for the shipment",
            "Shipment quote",
            "",
            "bob@vendor.com",
            "alice@example.com",
        ),
        (
            2,
            "Re: thanks, approved",
            "Re: Shipment quote",
            "po.pdf",
            "alice@example.com",
            "bob@vendor.com",
        ),
        (3, "deleted body", "Deleted", "", "spam@bad.com", "alice@example.com"),
    ]
    con.executemany("INSERT INTO messagesText_content VALUES (?, ?, ?, ?, ?, ?)", text)
    con.commit()
    con.close()


@pytest.fixture(autouse=True)
def fake_snapshot(tmp_path, monkeypatch):
    snap = tmp_path / "snapshot.sqlite"
    _build_snapshot(snap)
    monkeypatch.setattr(snapshot, "SNAPSHOT", snap)
    monkeypatch.setattr(snapshot, "ensure_fresh", lambda max_age=900: None)
    yield


def test_stats_excludes_deleted():
    s = db.stats()
    assert s["messages"] == 2
    assert s["oldest"].startswith("2023-11")
    assert s["newest"].startswith("2024-01")


def test_search_query_matches_body_and_subject():
    hits = db.search(query="shipment")
    assert {h["message_id"] for h in hits} == {1, 2}
    # newest first
    assert hits[0]["message_id"] == 2


def test_search_excludes_deleted():
    assert all(h["message_id"] != 3 for h in db.search(query="deleted"))


def test_search_by_from_addr():
    hits = db.search(from_addr="bob@vendor.com")
    assert [h["message_id"] for h in hits] == [1]


def test_search_since_filter():
    hits = db.search(since="2024-01-01")
    assert [h["message_id"] for h in hits] == [2]


def test_account_inferred_from_uri():
    assert db.search(query="shipment")[0]["account"] == "alice@example.com"


def test_recent_by_address_both_directions():
    hits = db.recent_by_address("bob@vendor.com")
    assert {h["message_id"] for h in hits} == {1, 2}


def test_thread_is_chronological():
    msgs = db.thread(100)
    assert [m["message_id"] for m in msgs] == [1, 2]


def test_get_message_full_body():
    msg = db.get_message(1)
    assert msg["subject"] == "Shipment quote"
    assert msg["body_preview"] == "Quote for the shipment"
    assert db.get_message(999) is None


def test_folders_counts_non_deleted():
    folders = db.folders()
    assert folders[0]["name"] == "Inbox"
    assert folders[0]["account"] == "alice@example.com"
    assert folders[0]["count"] == 2
