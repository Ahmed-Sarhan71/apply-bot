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