from datetime import datetime, timedelta, timezone

from database.connection import connect
from telegram_reader import handle_message, parse_channels

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
POST = "We are hiring an AI Engineer. Python, RAG, FastAPI. Send your CV to jobs@acme.com"


def test_same_post_in_three_channels_is_saved_once(tmp_path):
    con = connect(tmp_path / "t.db")
    assert handle_message(con, "chan_a", 1, NOW, POST, now=NOW) == "saved"
    assert handle_message(con, "chan_b", 77, NOW, "  " + POST.upper() + "\n", now=NOW) == "duplicate"  # case/whitespace ignored
    assert handle_message(con, "chan_c", 5, NOW, POST, now=NOW) == "duplicate"
    rows = con.execute("SELECT channel, status FROM inbox").fetchall()
    assert [tuple(r) for r in rows] == [("chan_a", "new")]  # the first channel wins


def test_old_short_and_empty_posts_are_ignored(tmp_path):
    con = connect(tmp_path / "t.db")
    assert handle_message(con, "c", 1, NOW - timedelta(days=91), POST, now=NOW) == "old"
    assert handle_message(con, "c", 2, NOW, "thanks all!", now=NOW) == "short"
    assert handle_message(con, "c", 3, NOW, None, now=NOW) == "short"
    assert handle_message(con, "c", 4, NOW - timedelta(days=89), POST, now=NOW) == "saved"
    assert con.execute("SELECT COUNT(*) FROM inbox").fetchone()[0] == 1


def test_channel_names_are_cleaned():
    assert parse_channels("@technicalJobsapply, https://t.me/DailySWJobs/, technicalJobsapply,,") == [
        "technicalJobsapply",
        "DailySWJobs",
    ]


def test_post_without_an_email_is_not_saved(tmp_path):
    con = connect(tmp_path / "t.db")
    no_email = "We are hiring an AI Engineer. Python, RAG, FastAPI. Apply here: https://acme.com/careers/ai"
    assert handle_message(con, "c", 1, NOW, no_email, now=NOW) == "no_email"
    assert con.execute("SELECT COUNT(*) FROM inbox").fetchone()[0] == 0
    assert handle_message(con, "c", 2, NOW, POST, now=NOW) == "saved"  # the same job with an address is kept