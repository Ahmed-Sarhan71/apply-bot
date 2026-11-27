"""SQLite store: what was applied to, and whether a post/address was already done.

One file, no server. The Next.js dashboard opens the same file read/write.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
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
    body TEXT,
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'replied', 'rejected', 'no_reply')),
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_hash TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    channel TEXT NOT NULL,
    message_id INTEGER,
    link TEXT,
    posted_at TEXT,
    saved_at TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'done')),
    result TEXT
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
    if "body" not in {r[1] for r in con.execute("PRAGMA table_info(applications)")}:
        con.execute("ALTER TABLE applications ADD COLUMN body TEXT")  # older databases
    if "result" not in {r[1] for r in con.execute("PRAGMA table_info(inbox)")}:
        con.execute("ALTER TABLE inbox ADD COLUMN result TEXT")  # inbox created before results were tracked
    return con


def already_sent(con: sqlite3.Connection, post_hash: str | None = None, to_email: str | None = None) -> bool:
    """True if this exact post (hash) or this address was applied to before."""
    if post_hash and con.execute("SELECT 1 FROM inbox WHERE post_hash = ? AND result = 'sent' LIMIT 1", (post_hash,)).fetchone():
        return True  # sent from the inbox but too old to be listed in All Applications
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
    body: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    con.execute(
        "INSERT INTO applications (applied_at, to_email, company, role_title, subject, body, post_text, post_hash, status, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sent', ?)",
        (now, to_email.lower(), company, role_title, subject, body, post_text, post_hash, now),
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


def save_inbox(
    con: sqlite3.Connection,
    *,
    post_hash: str,
    text: str,
    channel: str,
    message_id: int | None = None,
    link: str | None = None,
    posted_at: str | None = None,
    source: str = "telegram",
) -> bool:
    """Save a collected post. False if the same post (same hash) was already saved, from any channel."""
    cur = con.execute(
        "INSERT OR IGNORE INTO inbox (post_hash, source, channel, message_id, link, posted_at, saved_at, text)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (post_hash, source, channel, message_id, link, posted_at, datetime.now().isoformat(timespec="seconds"), text),
    )
    con.commit()
    return cur.rowcount == 1


def inbox_new(con: sqlite3.Connection, days: int = 90, limit: int | None = None, retry_failed: bool = False) -> list[sqlite3.Row]:
    """Posts still waiting to be processed, newest first, from the last `days` days. No limit means all of them.

    Posts that failed last time (status 'new', result 'failed') are skipped unless retry_failed, so a post that
    always breaks does not cost tokens on every run.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return con.execute(
        "SELECT * FROM inbox WHERE status = 'new' AND COALESCE(posted_at, saved_at) >= ?"
        " AND (? OR result IS NULL OR result != 'failed')"
        " ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC LIMIT ?",
        (cutoff, int(retry_failed), -1 if limit is None else limit),  # SQLite: LIMIT -1 means no limit
    ).fetchall()


def mark_inbox(con: sqlite3.Connection, post_hash: str, result: str) -> None:
    """A finished post becomes 'done'. A failed one keeps status 'new' with result 'failed', so it can be retried."""
    status = "new" if result == "failed" else "done"
    con.execute("UPDATE inbox SET status = ?, result = ? WHERE post_hash = ?", (status, result, post_hash))
    con.commit()