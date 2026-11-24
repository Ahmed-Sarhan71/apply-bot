from database.connection import already_sent, connect, record


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
