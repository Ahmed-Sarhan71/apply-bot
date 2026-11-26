import json
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai.candidate_matcher import (
    INSTRUCTIONS,
    MatcherError,
    build_system_prompt,
    load_candidate_context,
    match_candidate,
)
from ai.job_analyzer import JobAnalysis

CARDS = """# Project Cards

## 1. AI Research Assistant (private document Q&A)
**Tech:** Python, FastAPI, Qdrant, RAG

## 2. Edge-AI Pest Monitoring Station
**Tech:** Raspberry Pi, OpenCV, TensorFlow Lite

## 3. Tennis Fusion (e-commerce platform)
**Tech:** .NET 9, Angular, Docker, Redis
"""

RESUME = """Ahmed Sarhan  AI Engineer
ahm161001@gmail.com
+201514160333
linkedin.com/in/ahmed-sarhan01
Skills: Python, LLM, RAG, LangChain, FastAPI, Docker, OpenCV, Matplotlib, Seaborn
Profile: strong software engineering skills and experience in AI agents,
LLM orchestration, RAG, and workflow automation.
"""

TODAY = date(2026, 11, 23)


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.replies.pop(0)
        if not isinstance(content, str):
            content = json.dumps(content)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "project_cards.md").write_text(CARDS, encoding="utf-8")
    (tmp_path / "resume.txt").write_text(RESUME, encoding="utf-8")
    return load_candidate_context(tmp_path)


def job(**kw):
    base = dict(role_title="AI Engineer", company="Acme", required_skills=["Python", "RAG", "Kubernetes"])
    return JobAnalysis(**{**base, **kw})


def test_loader_parses_cards_and_strips_contact_lines(ctx):
    assert ctx.project_names == {
        1: "AI Research Assistant (private document Q&A)",
        2: "Edge-AI Pest Monitoring Station",
        3: "Tennis Fusion (e-commerce platform)",
    }
    assert "gmail.com" not in ctx.resume_text
    assert "+2015" not in ctx.resume_text
    assert "linkedin" not in ctx.resume_text.lower()
    assert "Python, LLM, RAG" in ctx.resume_text


def test_loader_errors_are_clear(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_candidate_context(tmp_path)
    (tmp_path / "project_cards.md").write_text(CARDS, encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_candidate_context(tmp_path)  # cards exist, resume missing


def test_ids_become_names_and_result_is_returned(ctx):
    reply = {
        "selected_projects": [{"project_id": 1, "reason": "RAG overlap"}, {"project_id": 2, "reason": "CV overlap"}],
        "matched_skills": [
            {"skill": "Python", "evidence": "Python, LLM, RAG"},
            {"skill": "RAG", "evidence": "RAG, LangChain"},
        ],
        "missing_skills": ["Kubernetes"],
        "experience_note": None,
        "email_angle": "Lead with RAG.",
    }
    r = match_candidate(job(), ctx, client=FakeClient(reply), today=TODAY)
    assert [p.name for p in r.selected_projects] == [
        "AI Research Assistant (private document Q&A)",
        "Edge-AI Pest Monitoring Station",
    ]
    assert [m.skill for m in r.matched_skills] == ["Python", "RAG"] and r.missing_skills == ["Kubernetes"]


def test_unknown_and_duplicate_project_ids_dropped_and_capped(ctx):
    picks = [{"project_id": i} for i in (99, 1, 1, 2, 3, 2)]
    r = match_candidate(job(), ctx, client=FakeClient({"selected_projects": picks}), today=TODAY)
    assert [p.project_id for p in r.selected_projects] == [1, 2, 3]


def test_fabricated_evidence_for_unknown_skill_moves_it_to_missing(ctx):
    reply = {
        "matched_skills": [
            {"skill": "Python", "evidence": "Python, LLM, RAG"},
            {"skill": "Kubernetes", "evidence": "ran Kubernetes clusters in production"},
        ]
    }
    r = match_candidate(job(), ctx, client=FakeClient(reply), today=TODAY)
    assert [m.skill for m in r.matched_skills] == ["Python"]
    assert r.missing_skills == ["Kubernetes"]


def test_synonym_with_real_quote_is_kept(ctx):
    reply = {"matched_skills": [{"skill": "Data Visualization", "evidence": "Matplotlib, Seaborn"}]}
    r = match_candidate(job(), ctx, client=FakeClient(reply), today=TODAY)
    assert [m.skill for m in r.matched_skills] == ["Data Visualization"]
    assert r.missing_skills == []


def test_quote_spanning_a_line_wrap_is_verified(ctx):
    reply = {"matched_skills": [{"skill": "Agents", "evidence": "experience in AI agents, LLM orchestration"}]}
    r = match_candidate(job(), ctx, client=FakeClient(reply), today=TODAY)
    assert [m.skill for m in r.matched_skills] == ["Agents"]


def test_bad_quote_but_skill_literally_in_resume_is_kept(ctx):
    reply = {"matched_skills": [{"skill": "Python", "evidence": "a sentence the model made up"}]}
    r = match_candidate(job(), ctx, client=FakeClient(reply), today=TODAY)
    assert [m.skill for m in r.matched_skills] == ["Python"]


def test_plain_string_skills_are_tolerated_and_plural_matches(ctx):
    r = match_candidate(job(), ctx, client=FakeClient({"matched_skills": ["LLMs", "Terraform"]}), today=TODAY)
    assert [m.skill for m in r.matched_skills] == ["LLMs"]
    assert r.missing_skills == ["Terraform"]


def test_retries_on_blank_and_invalid_then_succeeds(ctx):
    client = FakeClient("  ", "not json", {"email_angle": "ok"})
    assert match_candidate(job(), ctx, client=client, today=TODAY).email_angle == "ok"
    assert len(client.calls) == 3


def test_gives_up_after_max_attempts(ctx):
    with pytest.raises(MatcherError):
        match_candidate(job(), ctx, client=FakeClient("", "", ""), today=TODAY)


def test_system_prompt_is_identical_across_jobs_for_caching(ctx):
    c = FakeClient({}, {})
    match_candidate(job(role_title="Zq1Probe"), ctx, client=c, today=TODAY)
    match_candidate(job(role_title="Zq2Probe", company="Other"), ctx, client=c, today=TODAY)
    s1, s2 = (call["messages"][0]["content"] for call in c.calls)
    assert s1 == s2 == build_system_prompt(ctx)
    assert "Zq1Probe" not in s1 and "Zq2Probe" not in s1  # job text must not leak into the cached prefix
    assert "Zq2Probe" in c.calls[1]["messages"][1]["content"]


def test_thinking_is_disabled(ctx):
    c = FakeClient({})
    match_candidate(job(), ctx, client=c, today=TODAY)
    assert c.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


# ---- Live check against the real model and your real context/ folder ----
REAL_CONTEXT = Path(__file__).parent.parent / "context"
live = pytest.mark.skipif(
    not (os.environ.get("DEEPSEEK_API_KEY") and (REAL_CONTEXT / "project_cards.md").exists()),
    reason="needs DEEPSEEK_API_KEY and context/project_cards.md",
)


@live
def test_live_ai_job_picks_rag_project_and_flags_kubernetes():
    real = load_candidate_context(REAL_CONTEXT)
    j = job(
        seniority="senior",
        min_years_experience=5,
        required_skills=["Python", "RAG", "Kubernetes", "Terraform"],
    )
    r = match_candidate(j, real)
    assert 1 in [p.project_id for p in r.selected_projects]  # AI Research Assistant
    assert "Kubernetes" in r.missing_skills and "Terraform" in r.missing_skills
    assert "Python" in [m.skill for m in r.matched_skills]
    assert r.experience_note  # 5+ years asked, the resume shows far less


def test_newest_pdf_is_used_when_several_exist(tmp_path, caplog):
    from pypdf import PdfWriter

    (tmp_path / "project_cards.md").write_text(CARDS, encoding="utf-8")
    for name, mtime in (("Resume.pdf", 1_000_000_000), ("Resume_v2.pdf", 1_700_000_000)):
        w = PdfWriter()
        w.add_blank_page(width=72, height=72)
        with open(tmp_path / name, "wb") as f:
            w.write(f)
        os.utime(tmp_path / name, (mtime, mtime))  # Resume.pdf sorts first alphabetically but is the older file
    with caplog.at_level("INFO", logger="jobbot.matcher"):
        load_candidate_context(tmp_path)
    assert "resume: Resume_v2.pdf" in caplog.text
    assert "using the most recently modified: Resume_v2.pdf" in caplog.text


# ---------- ranking block ----------

RANKED_CARDS = CARDS + """
---

## Ranking
Choose the projects in this order, best first:
1. Tennis Fusion
Promotions: jobs about .NET, C# or ASP.NET Core put Tennis Fusion first.
Rank order (card numbers, best first): 3, 1, 99
"""


def _ranked_ctx(tmp_path, cards=RANKED_CARDS):
    (tmp_path / "project_cards.md").write_text(cards, encoding="utf-8")
    (tmp_path / "resume.txt").write_text(RESUME, encoding="utf-8")
    return load_candidate_context(tmp_path)


def test_ranking_block_is_parsed_and_unknown_numbers_ignored(tmp_path):
    c = _ranked_ctx(tmp_path)
    assert c.rank == [3, 1, 2]  # 99 does not exist; card 2 was not listed so it is appended
    assert sorted(c.project_names) == [1, 2, 3]  # "## Ranking" is not mistaken for a card


def test_ranking_text_is_not_evidence_but_is_in_the_prompt(tmp_path):
    c = _ranked_ctx(tmp_path)
    assert "asp.net core" not in c.searchable and "Promotions" not in c.cards_text
    assert "=== PROJECT RANKING ===" in build_system_prompt(c) and "put Tennis Fusion first" in build_system_prompt(c)
    r = match_candidate(job(), c, client=FakeClient({"matched_skills": [{"skill": "ASP.NET Core", "evidence": "ASP.NET Core"}]}), today=TODAY)
    assert [m.skill for m in r.matched_skills] == [] and r.missing_skills == ["ASP.NET Core"]


def test_cards_without_a_ranking_block_still_work(tmp_path):
    c = _ranked_ctx(tmp_path, cards=CARDS)
    assert c.rank == [1, 2, 3] and c.ranking_text == ""
    assert "=== PROJECT RANKING ===" not in build_system_prompt(c)


def test_prompt_tells_the_model_to_follow_the_ranking():
    assert "PROJECT RANKING" in INSTRUCTIONS and "promotions" in INSTRUCTIONS

# ---------- related skills (job names a tool, resume lists the platform) ----------

def test_missing_tool_of_a_listed_platform_is_related_not_a_gap(tmp_path):
    (tmp_path / "project_cards.md").write_text(CARDS, encoding="utf-8")
    (tmp_path / "resume.txt").write_text("Cloud & MLOps: AWS, Azure, GCP, Docker, CI/CD, Linux\n", encoding="utf-8")
    c = load_candidate_context(tmp_path)
    reply = {"missing_skills": ["Azure DevOps", "Kubernetes"]}
    r = match_candidate(job(), c, client=FakeClient(reply), today=TODAY)
    assert r.missing_skills == ["Azure DevOps", "Kubernetes"]  # still never claimed by name
    assert r.related_skills == ["Azure DevOps"]  # but no "I haven't worked with it" for this one