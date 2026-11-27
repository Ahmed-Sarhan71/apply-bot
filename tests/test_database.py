from database.connection import already_sent, connect, record, record_failure


def test_a_failed_post_is_kept_and_cleared_once_it_sends(tmp_path):
    con = connect(tmp_path / "t.db")
    record_failure(con, post_text="post", post_hash="h1", reason="writing: one word short")
    record_failure(con, post_text="post", post_hash="h1", reason="writing: mentioned monitoring")
    rows = con.execute("SELECT reason FROM failures").fetchall()
    assert len(rows) == 1, "same post must not pile up rows"
    assert "monitoring" in rows[0][0], "latest reason wins"

    record(con, post_text="post", post_hash="h1", to_email="hr@acme.com", subject="s", body="Dear team,\n\nhello")
    assert con.execute("SELECT COUNT(*) FROM failures").fetchone()[0] == 0
    assert already_sent(con, post_hash="h1")
    assert "Dear team" in con.execute("SELECT body FROM applications").fetchone()[0]


def test_record_then_already_sent(tmp_path):
    con = connect(tmp_path / "t.db")
    assert not already_sent(con, post_hash="abc")
    record(con, post_text="post", post_hash="abc", to_email="HR@Acme.com", company="Acme", role_title="Dev", subject="Application for Dev")
    assert already_sent(con, post_hash="abc")
    assert already_sent(con, to_email="hr@acme.com")  # stored lowercased
    assert not already_sent(con, to_email="other@acme.com")
    assert con.execute("SELECT status FROM applications").fetchone()[0] == "sent"


def test_email_cannot_be_recorded_twice(tmp_path):
    con = connect(tmp_path / "t.db")
    record(con, post_text="a", post_hash="h1", to_email="hr@acme.com")
    try:
        record(con, post_text="b", post_hash="h2", to_email="hr@acme.com")
    except Exception as e:
        assert "UNIQUE" in str(e)
    else:
        raise AssertionError("a second application to the same address was allowed")


def test_inbox_new_is_newest_first_within_days_and_limited(tmp_path):
    from datetime import datetime, timedelta, timezone

    from database.connection import inbox_new, mark_inbox, save_inbox

    con = connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    for name, age in (("fresh", 1), ("month", 30), ("ancient", 120)):
        save_inbox(con, post_hash=name, text=name, channel="c", posted_at=(now - timedelta(days=age)).isoformat(timespec="seconds"))
    assert [r["post_hash"] for r in inbox_new(con, days=90)] == ["fresh", "month"]  # 3 months back, newest first
    assert [r["post_hash"] for r in inbox_new(con, days=90, limit=1)] == ["fresh"]
    assert len(inbox_new(con, days=90, limit=None)) == 2  # no limit means the whole inbox
    mark_inbox(con, "fresh", "sent")
    assert [r["post_hash"] for r in inbox_new(con, days=90)] == ["month"]  # done posts are not picked again
    assert con.execute("SELECT status, result FROM inbox WHERE post_hash='fresh'").fetchone()[:] == ("done", "sent")


def test_old_inbox_table_gets_the_result_column(tmp_path):
    import sqlite3

    raw = sqlite3.connect(tmp_path / "old.db")
    raw.execute("CREATE TABLE inbox (id INTEGER PRIMARY KEY, post_hash TEXT UNIQUE, source TEXT, channel TEXT, message_id INTEGER,"
                " link TEXT, posted_at TEXT, saved_at TEXT, text TEXT, status TEXT DEFAULT 'new')")
    raw.commit(); raw.close()
    con = connect(tmp_path / "old.db")
    assert "result" in {r[1] for r in con.execute("PRAGMA table_info(inbox)")}


def test_inbox_sent_counts_as_already_sent_but_analyzed_does_not(tmp_path):
    from database.connection import mark_inbox, save_inbox

    con = connect(tmp_path / "t.db")
    for h in ("sent_from_inbox", "only_analyzed"):
        save_inbox(con, post_hash=h, text=h, channel="c", posted_at="2026-09-15T10:00:00+00:00")
    mark_inbox(con, "sent_from_inbox", "sent")
    mark_inbox(con, "only_analyzed", "no email")
    # an old post sends no applications row, so this is the only record that it went out
    assert already_sent(con, post_hash="sent_from_inbox")
    assert not already_sent(con, post_hash="only_analyzed")


def test_failed_inbox_post_is_not_done_and_is_retried_only_on_request(tmp_path):
    from datetime import datetime, timezone

    from database.connection import inbox_new, mark_inbox, save_inbox

    con = connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for h in ("ok", "bad"):
        save_inbox(con, post_hash=h, text=h, channel="c", posted_at=now)
    mark_inbox(con, "ok", "sent")
    mark_inbox(con, "bad", "failed")
    assert con.execute("SELECT status, result FROM inbox WHERE post_hash='bad'").fetchone()[:] == ("new", "failed")
    assert con.execute("SELECT status FROM inbox WHERE post_hash='ok'").fetchone()[0] == "done"
    assert inbox_new(con) == []  # a plain run leaves the failed post alone
    assert [r["post_hash"] for r in inbox_new(con, retry_failed=True)] == ["bad"]