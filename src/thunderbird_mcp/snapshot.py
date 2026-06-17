"""Atomic snapshot of Thunderbird's ``global-messages-db.sqlite`` (GLODA index).

Thunderbird keeps its index open in WAL mode, so it cannot be queried safely
while Thunderbird is running. We copy it with SQLite's online backup API (opening
the source read-only and immutable), which yields a consistent snapshot without
corrupting the live database.

CLI:
    python -m thunderbird_mcp.snapshot                # snapshot now
    python -m thunderbird_mcp.snapshot --max-age 900  # only if older than 15 min
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from thunderbird_mcp import config

CACHE_DIR = Path.home() / ".cache" / "thunderbird-mcp"
SNAPSHOT = CACHE_DIR / "snapshot.sqlite"
STAMP = CACHE_DIR / "last_snapshot"


def snapshot_path() -> Path:
    """Path to the local snapshot the read queries run against."""
    return SNAPSHOT


def snapshot_age_seconds() -> float:
    if not STAMP.exists():
        return float("inf")
    return time.time() - STAMP.stat().st_mtime


def take_snapshot(retries: int = 3, backoff: float = 2.0) -> None:
    """Copy the live GLODA index to the local cache, atomically.

    Raises:
        FileNotFoundError: if the Thunderbird database cannot be located.
        RuntimeError: if the database stays locked after all retries.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db_path = config.database_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Thunderbird index not found at {db_path}")

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            src = sqlite3.connect(
                f"file:{db_path}?mode=ro&immutable=1", uri=True, timeout=10
            )
            tmp = SNAPSHOT.with_suffix(".sqlite.tmp")
            tmp.unlink(missing_ok=True)
            dst = sqlite3.connect(tmp)
            with dst:
                src.backup(dst, pages=2000, sleep=0.05)
            dst.close()
            src.close()
            tmp.replace(SNAPSHOT)  # atomic publish
            STAMP.write_text(str(int(time.time())))
            return
        except sqlite3.OperationalError as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Could not snapshot after {retries} attempts: {last_err}")


def ensure_fresh(max_age: int = 900) -> None:
    """Take a new snapshot if the current one is older than ``max_age`` seconds."""
    if snapshot_age_seconds() > max_age:
        take_snapshot()


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot the Thunderbird GLODA index.")
    ap.add_argument(
        "--max-age",
        type=int,
        default=0,
        help="only snapshot if the current one is older than N seconds (0 = force)",
    )
    args = ap.parse_args()
    if args.max_age and snapshot_age_seconds() < args.max_age:
        print(f"snapshot is {int(snapshot_age_seconds())}s old, skipping")
        return 0
    print("taking snapshot...", flush=True)
    take_snapshot()
    size_mb = SNAPSHOT.stat().st_size / 1024 / 1024
    print(f"OK -> {SNAPSHOT} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
