# thunderbird-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that lets an LLM
search and read your **Thunderbird** email — locally, with no IMAP connection
and no credentials.

It works by querying Thunderbird's own full-text index (GLODA, the
`global-messages-db.sqlite` that Thunderbird already maintains). The server takes
an atomic snapshot of that database and exposes a handful of focused tools to any
MCP client: Claude Desktop, Claude Code, or the Agent SDK.

```
You:  "What did the vendor say about the shipment quote last month?"
LLM:  → tb_search(query="shipment quote", since="2024-01-01")
      → tb_thread(conversation_id=…)
      "They approved it on Jan 11 and attached po.pdf. Here's the thread…"
```

## Why

Most "email + LLM" integrations log into your IMAP server, re-download
everything, and need an app password. This one doesn't move any mail or hold any
secret. Thunderbird has already indexed every message you have — including local
folders and archived accounts — so the fastest, safest path is to read *that*
index directly.

- **No credentials.** Nothing to configure, nothing to leak. Read-only by design.
- **Offline.** Searches your local index; works on a plane.
- **Whole history.** Every account and local folder Thunderbird knows about, in
  one place.
- **Cross-platform.** Auto-detects your profile on Linux, macOS and Windows
  (including running under WSL against a Windows install).

## Tools

| Tool | What it does |
| --- | --- |
| `tb_search(query, since, until, from_addr, to_addr, account, folder, limit)` | Full-text + header + date search, newest first |
| `tb_recent_by_address(email_or_domain, limit)` | Every message to/from a contact or domain |
| `tb_thread(conversation_id, body_chars)` | A full conversation, oldest first |
| `tb_get_message(message_id, body_chars)` | One message with its complete body |
| `tb_folders()` | All folders with per-folder message counts |
| `tb_list_accounts()` | Configured accounts and their IMAP servers |
| `tb_stats()` | Total indexed messages and their date range |

## Install

Requires Python 3.11+ and a local Thunderbird install.

```bash
git clone https://github.com/agimenez-dev/thunderbird-mcp
cd thunderbird-mcp
uv sync          # or: pip install -e .
```

## Use with Claude Desktop / Claude Code

Add the server to your MCP config (`claude_desktop_config.json`, or `.mcp.json`
for Claude Code):

```json
{
  "mcpServers": {
    "thunderbird": {
      "command": "uv",
      "args": ["--directory", "/path/to/thunderbird-mcp", "run", "thunderbird-mcp"]
    }
  }
}
```

Restart the client and ask it about your mail.

## Configuration

The server auto-detects the default Thunderbird profile. Override it when
Thunderbird lives elsewhere — for example, querying a Windows install from WSL:

```bash
export THUNDERBIRD_PROFILE="/mnt/c/Users/You/AppData/Roaming/Thunderbird/Profiles/xxxx.default-release"
```

`THUNDERBIRD_PROFILE` must point at the profile **directory** — the folder that
contains `global-messages-db.sqlite`.

## How it works

```
Thunderbird
  └─ <profile>/global-messages-db.sqlite   (GLODA full-text index, WAL mode)
          │
          │  snapshot.py — SQLite online-backup API (read-only + immutable),
          │  atomic publish, retries on lock. Refreshes lazily (>15 min old).
          ▼
  ~/.cache/thunderbird-mcp/snapshot.sqlite  (read-only copy)
          │
          │  db.py — LIKE queries over messagesText_content
          ▼
  server.py — FastMCP, 7 tools
```

Two implementation notes worth knowing:

- **Why a snapshot?** Thunderbird keeps the index open in WAL mode. Reading it
  live risks a `database is locked` error or an inconsistent read, so the server
  copies it with SQLite's online-backup API before querying — never touching the
  original.
- **Why `LIKE` instead of FTS?** GLODA's full-text table uses a custom
  `mozporter` tokenizer that isn't compiled into a standard Python `sqlite3`.
  Rather than ship a patched SQLite, the server queries the precomputed text
  columns GLODA already maintains (`c0body`, `c1subject`, …) with `LIKE`.

## What it deliberately does *not* do

- Send, move, delete or modify mail. **Read-only, full stop.**
- Touch IMAP or store any credential.
- Re-index. It trusts the index Thunderbird already keeps current.
- Return attachment binaries — only their file names.

## Development

```bash
uv sync --extra dev
uv run pytest        # query + parsing layers are covered without Thunderbird installed
uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
