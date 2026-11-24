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
    con.commit()
