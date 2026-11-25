"""SQLite store: what was applied to, and whether a post/address was already done.

One file, no server. The Next.js dashboard opens the same file read/write.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("APPLYBOT_DB", "data/applications.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applied_at TEXT NOT NULL,
    to_email TEXT NOT NULL UNIQUE,
    company TEXT,
    role_title TEXT,
    subject TEXT NOT NULL,
    post_text TEXT NOT NULL,
    post_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'replied', 'rejected', 'no_reply')),
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failed_at TEXT NOT NULL,
    post_hash TEXT NOT NULL UNIQUE,
    post_text TEXT NOT NULL,
    company TEXT,
    role_title TEXT,
    to_email TEXT,
    reason TEXT NOT NULL
);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def already_sent(con: sqlite3.Connection, post_hash: str | None = None, to_email: str | None = None) -> bool:
    """True if this exact post (hash) or this address was applied to before."""
    where, args = [], []
    if post_hash:
        where.append("post_hash = ?")
        args.append(post_hash)
    if to_email:
        where.append("to_email = ?")
        args.append(to_email.lower())
    if not where:
        return False
    sql = f"SELECT 1 FROM applications WHERE {' OR '.join(where)} LIMIT 1"
    return con.execute(sql, args).fetchone() is not None


def record(
    con: sqlite3.Connection,
    *,
    post_text: str,
    post_hash: str,
    to_email: str,
    company: str | None = None,
    role_title: str | None = None,
    subject: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    con.execute(
        "INSERT INTO applications (applied_at, to_email, company, role_title, subject, post_text, post_hash, status, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'sent', ?)",
        (now, to_email.lower(), company, role_title, subject, post_text, post_hash, now),
    )
    # it went out, so it is no longer waiting to be reapplied
    con.execute("DELETE FROM failures WHERE post_hash = ?", (post_hash,))
    con.commit()


def record_failure(
    con: sqlite3.Connection | None,
    *,
    post_text: str,
    post_hash: str,
    reason: str,
    company: str | None = None,
    role_title: str | None = None,
    to_email: str | None = None,
) -> None:
    """Keep the post so it can be applied to again later. Re-failing the same post updates the reason."""
    if con is None:
        return
    con.execute(
        "INSERT INTO failures (failed_at, post_hash, post_text, company, role_title, to_email, reason)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(post_hash) DO UPDATE SET failed_at = excluded.failed_at, reason = excluded.reason",
        (
            datetime.now().isoformat(timespec="seconds"),
            post_hash,
            post_text,
            company,
            role_title,
            (to_email or "").lower() or None,
            reason[:300],
        ),
    )
    con.commit()
