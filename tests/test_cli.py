from cli import post_hash, split_posts
 
 
def test_split_on_separator():
    raw = "post one\nline 2\n---\npost two\n  ---  \npost three"
    assert split_posts(raw) == ["post one\nline 2", "post two", "post three"]
 
 
def test_single_post_with_blank_lines_stays_whole():
    raw = "Title\n\nbody\n\n\nmore"
    assert split_posts(raw) == [raw]
 
 
def test_empty_chunks_ignored():
    assert split_posts("---\n\n---\nonly\n---") == ["only"]
 
 
def test_hash_ignores_whitespace_and_case():
    assert post_hash("We're  Hiring\nnow") == post_hash("we're hiring now")
    assert post_hash("a") != post_hash("b")
 

def test_run_batch_reports_an_outcome_per_post(tmp_path, monkeypatch):
    import cli
    from ai.job_analyzer import AnalyzerError, JobAnalysis
    from database.connection import connect, record

    con = connect(tmp_path / "t.db")
    record(con, post_text="applied before", post_hash=cli.post_hash("applied before"), to_email="old@x.com")
    good, bad = "Hiring AI engineer, mail hr@acme.com", "garbage post"

    def fake_analyze(text):
        if text == bad:
            raise AnalyzerError("nope")
        return JobAnalysis(role_title="AI Engineer", company="Acme", apply_method="email", apply_email="hr@acme.com")

    monkeypatch.setattr(cli, "analyze_job", fake_analyze)
    out = cli.run_batch("", set(), False, None, None, False, con, posts=["applied before", good, bad, good])
    assert out[cli.post_hash("applied before")] == "already applied"
    assert out[cli.post_hash(bad)] == "failed"
    assert out[cli.post_hash(good)] == "analyzed"  # the repeated copy must not overwrite the first result


def test_a_sent_old_post_is_hidden_but_its_address_stays_blocked(tmp_path):
    import cli
    from ai.email_writer import Bullet, EmailDraft, WriterOutput
    from ai.job_analyzer import JobAnalysis
    from database.connection import already_sent, connect, save_inbox

    con = connect(tmp_path / "t.db")
    draft = EmailDraft(subject="s", greeting="Hi,", body=WriterOutput(opening="o", bullets=[Bullet(label="P", text="t")], closing="c"))
    for h, posted, to in (
        ("sept", "2026-09-15T10:00:00+00:00", "old@x.com"),
        ("nov", "2026-11-05T10:00:00+00:00", "new@x.com"),
    ):
        save_inbox(con, post_hash=h, text=f"{h} post, mail {to}", channel="c", posted_at=posted)
        job = JobAnalysis(role_title="R", company="C", apply_method="email", apply_email=to)
        cli._record_sent(con, f"{h} post", h, job, draft, "id", to, cli.DEFAULT_LIST_FROM)

    listed = {r["post_hash"]: r["listed"] for r in con.execute("SELECT post_hash, listed FROM applications")}
    assert listed == {"sept": 0, "nov": 1}
    assert already_sent(con, to_email="old@x.com")  # the old post's row is hidden, not missing
    assert already_sent(con, post_hash="sept")


class _FakeCtx:
    def __init__(self, resume_path):
        self.resume_path = resume_path


def _send_flow(tmp_path, monkeypatch, *, fail=(), fatal=(), posts=("one", "two")):
    """Wire run_batch to fakes: 20s of drafting per post, a 60s gap, sends recorded on a fake clock."""
    import cli
    from ai import email_sender as es
    from ai.email_writer import Bullet, EmailDraft, WriterOutput
    from ai.job_analyzer import JobAnalysis
    from database.connection import connect

    clock, slept, events = {"t": 0.0}, [], []
    monkeypatch.setattr(es.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(es.time, "sleep", lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))
    monkeypatch.setattr(es.random, "uniform", lambda a, b: 60)

    monkeypatch.setattr(cli, "analyze_job", lambda text: JobAnalysis(role_title=text, company="Co", apply_method="email", apply_email=f"hr@{text}.com"))
    monkeypatch.setattr(cli, "show_result", lambda *a, **k: None)
    monkeypatch.setattr(cli, "show_match", lambda *a, **k: None)
    monkeypatch.setattr(cli, "show_email", lambda *a, **k: None)
    monkeypatch.setattr(cli, "match_candidate", lambda a, ctx: type("M", (), {"selected_projects": []})())

    def fake_write(a, m, ctx, style):
        clock["t"] += 20  # drafting takes 20s
        events.append(f"draft {a.role_title}")
        return EmailDraft(subject="s", greeting="Hi,", body=WriterOutput(opening="o", bullets=[Bullet(label="P", text="t")], closing="c"))

    def fake_send(draft, to, cv, service):
        if to in fail:
            raise RuntimeError("smtp hiccup")
        if to in fatal:
            raise es.SendError("token expired")
        events.append(f"send {to}")
        return "id"

    monkeypatch.setattr(cli, "write_email", fake_write)
    monkeypatch.setattr(cli, "send_email", fake_send)
    monkeypatch.setattr(cli, "get_service", lambda: object())

    con = connect(tmp_path / "t.db")
    seen_results = []
    outcomes = cli.run_batch(
        "", set(), False, _FakeCtx(tmp_path / "cv.pdf"), "style", True, con,  # type: ignore[arg-type]
        posts=list(posts), on_result=lambda h, r: seen_results.append((h, r))
    )
    return outcomes, events, slept, seen_results, con


def test_each_email_goes_out_right_after_its_draft_and_the_gap_minus_drafting_time(tmp_path, monkeypatch):
    outcomes, events, slept, seen, _ = _send_flow(tmp_path, monkeypatch)
    assert events == ["draft one", "send hr@one.com", "draft two", "send hr@two.com"]
    assert slept == [40]  # 60s gap, 20s of it eaten by drafting; the first send never waits
    assert [r for _, r in seen] == ["sent", "sent"]  # one callback per post, in order
    assert set(outcomes.values()) == {"sent"}


def test_one_broken_send_does_not_stop_the_next_post(tmp_path, monkeypatch):
    outcomes, events, _, seen, con = _send_flow(tmp_path, monkeypatch, fail=("hr@one.com",))
    assert "send hr@two.com" in events  # the run carried on
    assert [r for _, r in seen] == ["failed", "sent"]
    reasons = [r[0] for r in con.execute("SELECT reason FROM failures").fetchall()]
    assert any("sending" in r for r in reasons)


def test_a_token_error_stops_the_whole_run(tmp_path, monkeypatch):
    outcomes, events, _, seen, _ = _send_flow(tmp_path, monkeypatch, posts=("one", "two", "three"), fatal=("hr@one.com",))
    assert "draft two" not in events  # nothing else is attempted
    assert len(seen) == 1 and seen[0][1] == "failed"