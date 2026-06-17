"""prefs.js parsing."""

from thunderbird_mcp import accounts

SAMPLE_PREFS = """
user_pref("mail.identity.id1.useremail", "alice@example.com");
user_pref("mail.identity.id2.useremail", "bob@work.example.org");
user_pref("mail.server.server1.hostname", "imap.example.com");
user_pref("mail.server.server1.userName", "alice@example.com");
user_pref("mail.server.server2.hostname", "mail.work.example.org");
user_pref("unrelated.pref", "ignore me");
"""


def test_parse_prefs_extracts_emails():
    result = accounts.parse_prefs(SAMPLE_PREFS)
    assert result["emails"] == ["alice@example.com", "bob@work.example.org"]


def test_parse_prefs_servers():
    servers = accounts.parse_prefs(SAMPLE_PREFS)["servers"]
    assert servers["server1"] == {
        "hostname": "imap.example.com",
        "username": "alice@example.com",
    }
    assert servers["server2"]["hostname"] == "mail.work.example.org"


def test_parse_prefs_empty():
    assert accounts.parse_prefs("") == {"emails": [], "by_id": {}, "servers": {}}
