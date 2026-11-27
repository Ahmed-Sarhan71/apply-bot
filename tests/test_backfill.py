import base64

from scripts.backfill_bodies import extract_text


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_text_prefers_the_plain_part_and_decodes_it():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html copy</p>")}},
            {
                "mimeType": "multipart/related",
                "parts": [{"mimeType": "text/plain", "body": {"data": _b64("Dear team,\n\nplain copy")}}],
            },
        ],
    }
    assert extract_text(payload) == "Dear team,\n\nplain copy"
    assert extract_text({"mimeType": "text/html", "body": {"data": _b64("<p>x</p>")}}) == ""


def _sent_post(con, h: str, text: str, posted: str = "2026-09-10T09:00:00+00:00"):
    from database.connection import mark_inbox, save_inbox

    save_inbox(con, post_hash=h, text=text, channel="ch", link=f"https://t.me/ch/{h}", posted_at=posted)
    mark_inbox(con, h, "sent")


def test_backfill_inserts_one_row_when_the_post_has_one_address(tmp_path):
    from database.connection import connect
    from scripts.backfill_bodies import backfill_sent_rows

    con = connect(tmp_path / "t.db")
    _sent_post(con, "h1", "Senior Python dev, remote.\nSend your CV to hr@acme.com")
    backfill_sent_rows(con, apply=True)
    row = con.execute("SELECT to_email, listed, applied_at, company, body FROM applications").fetchone()
    assert row["to_email"] == "hr@acme.com"
    assert row["listed"] == 0  # old post: recorded, hidden from All Applications
    assert row["applied_at"] == con.execute("SELECT saved_at FROM inbox WHERE post_hash='h1'").fetchone()[0]
    assert row["company"] == "" and row["body"] == ""


def test_backfill_reports_several_addresses_instead_of_guessing(tmp_path, capsys):
    from database.connection import connect
    from scripts.backfill_bodies import backfill_sent_rows

    con = connect(tmp_path / "t.db")
    _sent_post(con, "h1", "Two inboxes: apply@acme.com or jobs@acme.com")
    backfill_sent_rows(con, apply=True)
    assert con.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    out = capsys.readouterr().out
    assert "cannot tell" in out and "apply@acme.com" in out and "jobs@acme.com" in out and "h1" in out


def test_backfill_dry_run_writes_nothing(tmp_path, capsys):
    from database.connection import connect
    from scripts.backfill_bodies import backfill_sent_rows

    con = connect(tmp_path / "t.db")
    _sent_post(con, "h1", "Send your CV to hr@acme.com")
    backfill_sent_rows(con)
    assert con.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    out = capsys.readouterr().out
    assert "would add 1 row(s)" in out and "--apply" in out


def test_backfill_leaves_posts_that_already_have_a_row_alone(tmp_path):
    from database.connection import connect, record
    from scripts.backfill_bodies import backfill_sent_rows

    con = connect(tmp_path / "t.db")
    _sent_post(con, "h1", "Send your CV to hr@acme.com")
    record(con, post_text="p", post_hash="h1", to_email="hr@acme.com")
    backfill_sent_rows(con, apply=True)
    assert con.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 1
