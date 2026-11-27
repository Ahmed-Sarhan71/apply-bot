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


def test_pacer_never_waits_before_the_first_send_and_subtracts_drafting_time(monkeypatch):
    clock, slept = {"t": 1000.0}, []
    monkeypatch.setattr(es.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(es.time, "sleep", lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))

    pacer = es.Pacer(delay=(60, 60))
    pacer.wait()  # the first send goes out immediately
    assert slept == []
    pacer.sent()  # next send is allowed at 1060

    clock["t"] += 20  # drafting the next email took 20s
    pacer.wait()
    assert slept == [40], "the gap is 60s, 20 of which the drafting already used"
