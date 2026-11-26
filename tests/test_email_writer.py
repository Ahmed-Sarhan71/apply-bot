import json
from types import SimpleNamespace

import pytest

from ai.candidate_matcher import CandidateContext, MatchedSkill, MatchResult, ProjectPick
from ai.email_writer import (
    CV_LINE,
    LINKEDIN_URL,
    PORTFOLIO_URL,
    GITHUB_URL,
    not_already_featured,
    other_project_names,
    others_paragraph,
    short_project_name,
    WriterError,
    build_system_prompt,
    find_violations,
    first_name_from_email,
    make_greeting,
    make_subject,
    write_email,
    WriterOutput,
)
from ai.job_analyzer import JobAnalysis

RESUME = """Ahmed Sarhan AI Engineer
PROFILE
AI Engineer with a Bachelor's degree in Electronics Engineering (Computer major), with experience in AI agents,
LLM orchestration, RAG and workflow automation. Skilled in Python, backend development and FastAPI.
EDUCATION
Bachelor of Electronics Engineering (Hons.) majoring in Computer, Multimedia University (MMU) Nov 2020 - Mar 2025
"""
CARDS = """## 1. AI Research Assistant (private document Q&A)
Tech: Python, FastAPI, Qdrant. Runs offline.
## 2. DFU Ensemble Classifier (medical-image screening)
Infection F1 0.855 and ischaemia F1 0.824 using 5 ResNet18 models.
"""
CTX = CandidateContext(
    resume_text=RESUME,
    cards_text=CARDS,
    project_names={1: "AI Research Assistant (private document Q&A)", 2: "DFU Ensemble Classifier (medical-image screening)"},
)
STYLE = "1- job post ... 1- email Dear Team, ..."

GOOD = {
    "opening": "I'm applying for the AI Engineer position at Acme. I hold a Bachelor's degree in Computer Engineering, and I build AI systems that give teams reliable answers from their own documents while keeping that data private and cutting recurring cloud costs.",
    "bullets": [
        {"label": "AI Research Assistant", "text": "Built an offline document question-answering app with FastAPI and Qdrant, so teams get answers from confidential PDFs without sending data to any cloud service and without per-query fees."},
        {"label": "DFU Ensemble Classifier", "text": "Built an ensemble of 5 ResNet18 models reaching an infection F1 of 0.855, giving clinicians a consistent first pass over wound images before specialist review."},
        {"label": "Workflow automation", "text": "Developed automation workflows around AI agents that remove repetitive manual decisions from daily operations and free the team for higher-value work."},
    ],
    "acknowledged_gap": "Although I haven't worked with Kubernetes in a professional environment, I'm eager to learn it.",
    "closing": "I would bring the same business focus and care with data to Acme's AI projects.",
    "why_hire": None,
}


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


def job(**kw):
    base = dict(company="Acme", role_title="AI Engineer", apply_method="email", apply_email="jobs@acme.com")
    return JobAnalysis(**{**base, **kw})


def match(missing=("Kubernetes",)):
    return MatchResult(
        selected_projects=[
            ProjectPick(project_id=1, reason="RAG", name=CTX.project_names[1]),
            ProjectPick(project_id=2, reason="metrics", name=CTX.project_names[2]),
        ],
        matched_skills=[MatchedSkill(skill="Python", evidence="Skilled in Python")],
        missing_skills=list(missing),
        email_angle="Lead with RAG.",
    )


def variant(**changes):
    return {**GOOD, **changes}


# ---------- deterministic parts ----------


@pytest.mark.parametrize(
    "email, company, expected",
    [
        ("salma.ashraf@fawry.com", "Fawry", "Salma"),
        ("yasser.alaaeldin6@gmail.com", None, "Yasser"),
        ("recruitment.life@qnb.com.eg", "QNB", None),
        ("omnix.career@omnix.com", "Omnix", None),
        ("s.mohamed@propath.edu.sa", "ProPath", None),
        ("jobs@acme.com", "Acme", None),
        ("talabat.egypt@talabat.com", "Talabat", None),
        (None, None, None),
    ],
)
def test_first_name_heuristic(email, company, expected):
    assert first_name_from_email(email, company) == expected


def test_greeting_variants():
    assert make_greeting(job(apply_email="salma.ashraf@fawry.com")) == "Dear Salma,"
    assert make_greeting(job()) == "Dear Acme Hiring Team,"
    assert make_greeting(job(company=None)) == "Dear Hiring Team,"


def test_subject_rules():
    assert make_subject(job(required_subject="Senior AI/ML Engineer")) == "Senior AI/ML Engineer"
    assert make_subject(job(special_requirements=["Mention job title in email subject"])) == "AI Engineer"
    assert make_subject(job()) == "Application for AI Engineer"
    assert make_subject(job(role_title=None)) == "Job Application - Ahmed Sarhan"


# ---------- rendering ----------


def test_render_text_and_html():
    d = write_email(job(), match(), CTX, STYLE, client=FakeClient(GOOD))
    t = d.text()
    assert t.startswith("Dear Acme Hiring Team,\n\nI'm applying for the AI Engineer position at Acme.")
    assert "- AI Research Assistant: Built an offline" in t
    assert "business focus and care with data to Acme's AI projects. Although I haven't worked with Kubernetes" in t
    assert f"Portfolio: {PORTFOLIO_URL}" in t and f"LinkedIn: {LINKEDIN_URL}" in t
    assert "GitHub: https://github.com/Ahmed-Sarhan71" in t
    assert t.endswith("Best regards,\nAhmed Sarhan") and CV_LINE in t
    h = d.html()
    assert "<li><b>AI Research Assistant:</b>" in h and f'href="{PORTFOLIO_URL}"' in h


def test_html_escapes_model_text():
    out = variant(closing="I like <script>alert(1)</script> & tools, and I would bring the same business focus to Acme's AI projects and help the team ship.")
    h = write_email(job(), match(), CTX, STYLE, client=FakeClient(out)).html()
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_why_hire_paragraph_is_included():
    d = write_email(job(), match(), CTX, STYLE, client=FakeClient(variant(why_hire="I learn quickly and ship end to end.")))
    t = d.text()
    assert t.index("I learn quickly") < t.index("I would bring the same business focus")


# ---------- the safety net ----------


def test_missing_skill_in_bullets_is_rejected_then_repaired():
    bad = variant(bullets=GOOD["bullets"] + [{"label": "Ops", "text": "Ran Kubernetes clusters."}])
    c = FakeClient(bad, GOOD)
    d = write_email(job(), match(), CTX, STYLE, client=c)
    assert "Kubernetes clusters" not in d.text()
    assert len(c.calls) == 2
    feedback = c.calls[1]["messages"][-1]["content"]
    assert "Kubernetes" in feedback and "acknowledged_gap" in feedback


def test_missing_skill_is_allowed_inside_acknowledged_gap():
    assert find_violations(WriterOutput.model_validate(GOOD), CTX, ["Kubernetes"]) == []


def test_unverified_number_and_years_are_flagged():
    out = WriterOutput.model_validate(variant(closing="I have 3 years of experience and led 12 projects."))
    problems = " | ".join(find_violations(out, CTX, []))
    assert "years" in problems and "'12'" in problems


def test_numbers_from_cards_are_allowed():
    assert find_violations(WriterOutput.model_validate(GOOD), CTX, []) == []  # 5, 0.855 come from the cards


def test_wrong_degree_wording_is_flagged():
    out = WriterOutput.model_validate(variant(opening="I hold a Bachelor's degree in Electronics Engineering and love RAG."))
    assert any("electronics engineering" in p for p in find_violations(out, CTX, []))
    out = WriterOutput.model_validate(variant(opening="I hold a Bachelor of Software Engineering and love RAG."))
    assert any("software engineering" in p for p in find_violations(out, CTX, []))


def test_correct_degree_wording_passes_with_curly_apostrophe():
    out = WriterOutput.model_validate(variant(opening=GOOD["opening"].replace("'", "’")))
    assert find_violations(out, CTX, []) == []


def test_structure_problems():
    out = WriterOutput.model_validate(variant(bullets=GOOD["bullets"][:1], closing="**bold**"))
    problems = " | ".join(find_violations(out, CTX, []))
    assert "bullets" in problems and "markdown" in problems


def test_gives_up_after_max_attempts():
    bad = variant(closing="Experienced with Kubernetes.")
    with pytest.raises(WriterError):
        write_email(job(), match(), CTX, STYLE, client=FakeClient(bad, bad, bad))


def test_blank_and_invalid_replies_retry():
    c = FakeClient("", "not json", GOOD)
    write_email(job(), match(), CTX, STYLE, client=c)
    assert len(c.calls) == 3


# ---------- prompt and call settings ----------


def test_system_prompt_is_identical_across_jobs_and_has_no_job_text():
    c = FakeClient(GOOD, GOOD)
    write_email(job(company="FirstCo"), match(), CTX, STYLE, client=c)
    write_email(job(company="SecondCo"), match(), CTX, STYLE, client=c)
    s1, s2 = (call["messages"][0]["content"] for call in c.calls)
    assert s1 == s2 == build_system_prompt(CTX, STYLE)
    assert "FirstCo" not in s1 and "SecondCo" not in s1
    assert "SecondCo" in c.calls[1]["messages"][1]["content"]


def test_prompt_contains_resume_cards_and_style():
    p = build_system_prompt(CTX, STYLE)
    assert "Bachelor's degree in Computer Engineering" in p and "AI Research Assistant" in p and "1- email" in p


def test_thinking_disabled():
    c = FakeClient(GOOD)
    write_email(job(), match(), CTX, STYLE, client=c)
    assert c.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


# ---------- length, project limit and business focus ----------


def test_word_count_ignores_bullet_dashes_and_blank_tokens():
    from ai.email_writer import word_count

    assert word_count("- one two\n\n- three  ") == 3


def test_finished_email_is_between_150_and_180_words():
    d = write_email(job(), match(), CTX, STYLE, client=FakeClient(GOOD))
    assert 190 <= d.word_count() <= 220


def test_too_long_and_too_short_are_rejected_with_the_count():
    long_ = WriterOutput.model_validate(variant(closing="word " * 60))
    short = WriterOutput.model_validate(variant(closing="Thanks.", acknowledged_gap=None, why_hire=None, bullets=GOOD["bullets"][:2]))
    assert any("cut about" in p for p in find_violations(long_, CTX, [], "Dear Acme Hiring Team,"))
    assert any("add about" in p for p in find_violations(short, CTX, [], "Dear Acme Hiring Team,"))


def test_four_bullets_are_rejected_and_repaired():
    four = variant(bullets=GOOD["bullets"] + [{"label": "Extra", "text": "Built another useful project."}])
    c = FakeClient(four, GOOD)
    d = write_email(job(), match(), CTX, STYLE, client=c)
    assert len(d.body.bullets) == 3 and len(c.calls) == 2
    assert "never more than 3" in c.calls[1]["messages"][-1]["content"]


def test_length_problem_triggers_a_rewrite():
    c = FakeClient(variant(closing="word " * 80), GOOD)
    d = write_email(job(), match(), CTX, STYLE, client=c)
    assert 190 <= d.word_count() <= 220 and len(c.calls) == 2


def test_business_need_reaches_the_model_and_the_prompt_asks_for_business_terms():
    c = FakeClient(GOOD)
    write_email(job(business_need="Acme needs faster answers from its documents."), match(), CTX, STYLE, client=c)
    assert "Acme needs faster answers from its documents." in c.calls[0]["messages"][1]["content"]
    system = c.calls[0]["messages"][0]["content"]
    assert "business problem" in system and "NEVER more than 3" in system and "190 to 220" in system


# ---------- the rest of the projects, GitHub link ----------

FOUR = CandidateContext(
    resume_text=RESUME,
    cards_text=CARDS,
    project_names={
        1: "AI Research Assistant (private document Q&A)",
        2: "DFU Ensemble Classifier (medical-image screening)",
        3: "Tennis Fusion (e-commerce platform)",
        4: "Nextcloud Home Server (private cloud storage)",
    },
    rank=[2, 4, 1, 3],
)


def test_short_name_strips_the_parenthesis():
    assert short_project_name("Tennis Fusion (e-commerce platform)") == "Tennis Fusion"
    assert short_project_name("Pyro Protector") == "Pyro Protector"


def test_other_projects_are_the_unfeatured_cards_in_rank_order():
    m = MatchResult(selected_projects=[ProjectPick(project_id=2, name="x")])
    assert other_project_names(m, FOUR) == ["Nextcloud Home Server", "AI Research Assistant", "Tennis Fusion"]


def test_others_paragraph_is_two_fixed_sentences():
    p = others_paragraph(["A", "B", "C"])
    assert p == "Beyond these, I've also built A, B and C. All of them are on my GitHub and in my portfolio."
    assert others_paragraph(["A"]).startswith("Beyond these, I've also built A. ")
    assert others_paragraph([]) == "All of them are on my GitHub and in my portfolio."


def test_project_already_in_a_bullet_is_not_listed_again():
    out = WriterOutput.model_validate(GOOD)
    assert not_already_featured(["DFU Ensemble Classifier", "Pyro Protector"], out) == ["Pyro Protector"]


def test_email_lists_remaining_projects_and_github_in_text_and_html():
    m = MatchResult(
        selected_projects=[ProjectPick(project_id=1, name="x"), ProjectPick(project_id=2, name="y")],
        missing_skills=["Kubernetes"],
    )
    reply = variant()  # all three bullets
    d = write_email(job(), m, FOUR, STYLE, client=FakeClient(reply))
    assert d.other_projects == ["Nextcloud Home Server", "Tennis Fusion"]
    t = d.text()
    assert "Beyond these, I've also built Nextcloud Home Server and Tennis Fusion. All of them are on my GitHub and in my portfolio." in t
    assert t.index("Beyond these") > t.index("- DFU Ensemble Classifier:") and t.index("Beyond these") < t.index("Portfolio:")
    assert f'href="{GITHUB_URL}"' in d.html() and "Nextcloud Home Server" in d.html()
    assert 190 <= d.word_count() <= 220


def test_prompt_tells_the_model_not_to_list_other_projects():
    p = build_system_prompt(CTX, STYLE)
    assert "do not list other projects" in p and "GitHub" in p

def test_gap_sentence_is_dropped_for_a_skill_the_resume_covers():
    from ai.candidate_matcher import MatchResult
    from ai.email_writer import WriterOutput, drop_unneeded_gap

    match = MatchResult(missing_skills=["Azure DevOps", "Kubernetes"], related_skills=["Azure DevOps"])
    body = dict(opening="o", bullets=[], closing="c")
    out = WriterOutput(**body, acknowledged_gap="Although I haven't worked with Azure DevOps professionally, I'm eager to learn it.")
    drop_unneeded_gap(out, match)
    assert out.acknowledged_gap is None

    out = WriterOutput(**body, acknowledged_gap="Although I haven't worked with Kubernetes professionally, I'm eager to learn it.")
    drop_unneeded_gap(out, match)
    assert out.acknowledged_gap is not None  # a real gap is still allowed