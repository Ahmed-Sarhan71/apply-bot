from ai import email_sender as es
from ai.email_writer import Bullet, EmailDraft, WriterOutput


def draft() -> EmailDraft:
    body = WriterOutput(opening="opening", bullets=[Bullet(label="Project", text="text")], closing="closing")
    return EmailDraft(subject="Application for X", greeting="Dear Team,", body=body)


def test_message_has_text_html_and_cv(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 test")
    msg = es.build_message(draft(), "hr@acme.com", cv)
    assert msg["To"] == "hr@acme.com" and msg["Subject"] == "Application for X"
    types = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in types and "text/html" in types
    assert any(p.get_filename() == "cv.pdf" for p in msg.walk())


def test_send_all_paces_between_sends_but_not_before_the_first(monkeypatch):
    slept, sent = [], []
    monkeypatch.setattr(es.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(es, "send_email", lambda d, to, cv, service: sent.append(to) or f"id-{to}")
    ids = list(es.send_all([(draft(), "a@x.com"), (draft(), "b@x.com"), (draft(), "c@x.com")], "cv.pdf", service=object(), delay=(5, 5)))
    assert sent == ["a@x.com", "b@x.com", "c@x.com"]
    assert ids == ["id-a@x.com", "id-b@x.com", "id-c@x.com"]
    assert slept == [5, 5]
