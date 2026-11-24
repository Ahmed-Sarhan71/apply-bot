"""Email Writer: job + matcher result in, a ready-to-send EmailDraft out.

Split of responsibilities (so a model slip can never reach a recruiter):
  code  -> subject, greeting, links, CV line and signature (fixed, deterministic)
  model -> opening, 3-4 bullets, one optional honest gap sentence, closing, optional "why hire" note
  code  -> checks the model's text and sends it back for repair if it breaks a rule

The shared prompt (instructions + resume + cards + the candidate's own example emails) comes first and is
identical for every job, so DeepSeek's prefix cache applies. The job goes last.
"""

import html
import json
import logging
import os
import re
import time
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ai.candidate_matcher import CandidateContext, MatchResult
from ai.job_analyzer import JobAnalysis, get_client

log = logging.getLogger("jobbot.writer")

# Fixed parts, taken from the candidate's own reference emails.
SENDER_NAME = "Ahmed Sarhan"
PORTFOLIO_URL = "https://www.ahmedsarhan.space/"
LINKEDIN_URL = "https://www.linkedin.com/in/ahmed-sarhan01/"
GITHUB_URL = "https://github.com/Ahmed-Sarhan71"
CV_LINE = "I've attached my updated CV for your consideration. Thank you for your time."
BULLETS_INTRO = "My relevant experience includes:"
OTHERS_TAIL = "All of them are on my GitHub and in my portfolio."
# The candidate's chosen wording for the degree (the resume says "Electronics Engineering ... majoring in Computer").
DEGREE_FIELD = "Computer Engineering"

MIN_WORDS = 180  # the whole finished email: greeting, body, links, CV line and sign-off
MAX_WORDS = 220
MAX_BULLETS = 3


def word_count(text: str) -> int:
    """Words as a reader counts them: tokens with at least one letter or digit (bullet dashes don't count)."""
    return sum(1 for t in text.split() if re.search(r"\w", t))

INSTRUCTIONS = """You write short job-application emails for the candidate whose resume and project cards appear below. You receive one job (including the employer's business need) plus the matcher's analysis (projects to feature, skills the candidate has with evidence, skills the candidate lacks). Write the body in the candidate's own style (see the STYLE EXAMPLES at the end), but shorter and more business-focused: show the employer that the candidate's projects solve the kind of business problem the employer has.

Return ONLY a JSON object with exactly these keys:

{
  "opening": string,
  "bullets": [{"label": string, "text": string}],
  "acknowledged_gap": string or null,
  "closing": string,
  "why_hire": string or null
}

Rules:
- Use ONLY facts in the resume and project cards. Never invent skills, tools, employers, projects, results, savings, numbers or years of experience. Never write a number of years (no "2 years of experience"). Use any other number only if it appears in the resume or cards.
- LENGTH IS STRICT: the finished email (greeting, your text, links, CV line and sign-off) must be 190 to 220 words. About 70 of those words are added automatically (links, CV line, sign-off and two sentences that list the candidate's other projects and say they are on GitHub and in the portfolio), so opening, bullets, acknowledged_gap, closing and why_hire together must be about 120 to 150 words.
- opening: two sentences. First: "I'm applying for the <role_title> position at <company>." (leave out "at <company>" when the company is null). Second: say the candidate holds a Bachelor's degree in Computer Engineering (always use exactly this wording, even though the resume's EDUCATION section words the degree differently) and builds solutions to the employer's business need, put in plain words from business_need (do not quote it).
- bullets: 2 or 3 items, NEVER more than 3, best fit first. Prefer the project cards the matcher selected. "label" is the project name in a few words. "text" is ONE sentence of at most 22 words with this shape: the business problem the project solves, what the candidate built, and the benefit or result, taken from that card's Problem, Solution, Business benefit, Cost and Results lines. Choose projects whose business problem resembles the employer's need and write in business terms (time saved, cost avoided, risk reduced, data kept private), naming at most two technologies. Use a benefit only if the card states it; never invent savings or figures.
- NEVER claim a skill listed in missing_skills anywhere except acknowledged_gap: do not use its name, hint at it or imply familiarity. Claim a matched skill only where the evidence quote supports it.
- acknowledged_gap: the style examples show the candidate being honest about ONE core requirement they lack, in one positive sentence ("Although I haven't worked directly with X in a professional environment, I'm eager to learn it."). Do the same, in at most 20 words, about the single most central required skill in missing_skills, only when it is clearly a core requirement of the job; otherwise null. Never mention years of experience or seniority and never list several gaps.
- closing: ONE sentence of at most 15 words on what the candidate would bring to this employer's business need. Do not repeat the sign-off, links or CV line, and do not list other projects; those are added automatically.
- why_hire: when special_requirements ask for a short note on why they should hire the candidate (a brief, cover note or motivation), write two sentences at most answering it from true facts, and shorten the bullets so the length limit still holds; otherwise null.
- Write in English, first person, professional and concise like the examples. No emojis, no markdown, no greeting, no sign-off.
- Output JSON only, no commentary.

EXAMPLE JSON OUTPUT (shows the format and length only; choose the projects and facts that fit the actual job):
{
  "opening": "I'm applying for the AI Engineer position at Acme. I hold a Bachelor's degree in Computer Engineering and build AI systems that let teams get reliable answers from their own documents.",
  "bullets": [
    {"label": "AI Research Assistant", "text": "Built a private RAG assistant on local models, so teams get answers from confidential PDFs in seconds with no per-query API fees."},
    {"label": "Edge-AI Pest Monitoring Station", "text": "Replaced manual trap counting with an on-device vision system that runs 16 days per charge, giving farmers continuous pest data without internet."},
    {"label": "DFU Ensemble Classifier", "text": "Built a wound-image screening model with 0.968 infection recall, giving clinicians consistent first-pass triage."}
  ],
  "acknowledged_gap": "Although I haven't worked with Kubernetes professionally, I'm eager to learn it.",
  "closing": "I'd bring the same business focus to your team.",
  "why_hire": null
}"""


class WriterError(RuntimeError):
    pass


class Bullet(BaseModel):
    label: str
    text: str


class WriterOutput(BaseModel):
    opening: str = ""
    bullets: list[Bullet] = Field(default_factory=list)
    acknowledged_gap: str | None = None
    closing: str = ""
    why_hire: str | None = None


class EmailDraft(BaseModel):
    subject: str
    greeting: str
    body: WriterOutput
    other_projects: list[str] = Field(default_factory=list)  # short names of the projects not featured, best first

    def word_count(self) -> int:
        return word_count(self.text())

    def _closing(self) -> str:
        b = self.body
        return f"{b.closing.strip()} {(b.acknowledged_gap or '').strip()}".strip()

    def text(self) -> str:
        b = self.body
        bullets = "\n".join(f"- {x.label.strip()}: {x.text.strip()}" for x in b.bullets)
        parts = [self.greeting, b.opening.strip(), f"{BULLETS_INTRO}\n\n{bullets}", others_paragraph(self.other_projects)]
        if b.why_hire and b.why_hire.strip():
            parts.append(b.why_hire.strip())
        parts.append(self._closing())
        parts.append(f"Portfolio: {PORTFOLIO_URL}\nGitHub: {GITHUB_URL}\nLinkedIn: {LINKEDIN_URL}")
        parts += [CV_LINE, f"Best regards,\n{SENDER_NAME}"]
        return "\n\n".join(p for p in parts if p)

    def html(self) -> str:
        e = html.escape
        b = self.body
        items = "".join(f"<li><b>{e(x.label.strip())}:</b> {e(x.text.strip())}</li>" for x in b.bullets)
        paras = [others_paragraph(self.other_projects)]
        if b.why_hire and b.why_hire.strip():
            paras.append(b.why_hire.strip())
        paras.append(self._closing())
        body_paras = "".join(f"<p>{e(p)}</p>" for p in paras if p)
        return (
            f"<p>{e(self.greeting)}</p><p>{e(b.opening.strip())}</p><p>{e(BULLETS_INTRO)}</p><ul>{items}</ul>{body_paras}"
            f'<p>Portfolio: <a href="{PORTFOLIO_URL}">{PORTFOLIO_URL}</a><br>'
            f'GitHub: <a href="{GITHUB_URL}">{GITHUB_URL}</a><br>'
            f'LinkedIn: <a href="{LINKEDIN_URL}">{LINKEDIN_URL}</a></p>'
            f"<p>{e(CV_LINE)}</p><p>Best regards,<br>{e(SENDER_NAME)}</p>"
        )


def short_project_name(heading: str) -> str:
    """'Tennis Fusion (e-commerce platform)' -> 'Tennis Fusion'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", heading).strip()


def other_project_names(match: MatchResult, ctx: CandidateContext) -> list[str]:
    """Every card that is not a featured bullet, best-ranked first."""
    featured = {p.project_id for p in match.selected_projects}
    order = ctx.rank or sorted(ctx.project_names)
    return [short_project_name(ctx.project_names[i]) for i in order if i in ctx.project_names and i not in featured]


def not_already_featured(names: list[str], out: "WriterOutput") -> list[str]:
    """Drop projects the model already used in a bullet, so nothing is listed twice."""
    used = " ".join(f"{b.label} {b.text}" for b in out.bullets).lower()
    return [n for n in names if n.lower() not in used]


def others_paragraph(names: list[str]) -> str:
    """Two fixed sentences: the remaining projects, then where to find them. No model involved."""
    if not names:
        return OTHERS_TAIL
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Beyond these, I've also built {listed}. {OTHERS_TAIL}"


# ---------- deterministic parts ----------

GENERIC_MAILBOX_WORDS = {
    "hr", "jobs", "job", "career", "careers", "recruitment", "recruiter", "recruiting", "hiring", "talent",
    "info", "contact", "admin", "apply", "application", "applications", "cv", "cvs", "resume", "support",
    "hello", "team", "office", "mail", "email", "work", "works", "staff", "people", "humanresources",
}  # fmt: skip


def first_name_from_email(email: str | None, company: str | None = None) -> str | None:
    """'salma.ashraf@x.com' -> 'Salma'. Returns None for generic mailboxes like 'recruitment.life@x.com'."""
    if not email or "@" not in email:
        return None
    parts = [re.sub(r"\d+$", "", p) for p in re.split(r"[._-]", email.split("@")[0].lower())]
    if len(parts) < 2:
        return None
    first = parts[0]
    if len(first) < 3 or not first.isalpha() or first in GENERIC_MAILBOX_WORDS:
        return None
    if any(p in GENERIC_MAILBOX_WORDS for p in parts[1:]):
        return None
    if company and first in company.lower():  # 'omnix.something@' at Omnix is a department, not a person
        return None
    return first.capitalize()


def make_greeting(job: JobAnalysis) -> str:
    name = first_name_from_email(job.apply_email, job.company)
    if name:
        return f"Dear {name},"
    if job.company:
        return f"Dear {job.company} Hiring Team,"
    return "Dear Hiring Team,"


def make_subject(job: JobAnalysis) -> str:
    if job.required_subject:
        return job.required_subject
    title = job.role_title
    if not title:
        return f"Job Application - {SENDER_NAME}"
    if any("subject" in r.lower() for r in job.special_requirements):  # e.g. "mention the job title in the subject"
        return title
    return f"Application for {title}"


# ---------- checks on the model's text ----------

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
YEARS_RE = re.compile(r"\b\d+\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
DEGREE_RE = re.compile(
    r"bachelor(?:'s)?(?: degree)? (?:in|of) ([a-z][a-z &-]*?)(?=\s*(?:\(|,|\.|;| and | with | majoring|$))",
    re.IGNORECASE,
)


def _skill_pattern(skill: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(skill.strip())}s?(?![A-Za-z0-9])", re.IGNORECASE)


def find_violations(
    out: WriterOutput,
    ctx: CandidateContext,
    missing_skills: list[str],
    greeting: str = "Dear Hiring Team,",
    other_projects: list[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    main_parts = [out.opening, out.closing, out.why_hire or ""]
    for b in out.bullets:
        main_parts += [b.label, b.text]
    main = "\n".join(main_parts)
    everything = main + "\n" + (out.acknowledged_gap or "")
    norm = everything.replace("’", "'")

    if not out.opening.strip() or not out.closing.strip():
        problems.append("opening and closing must both be non-empty")
    if not 2 <= len(out.bullets) <= MAX_BULLETS:
        problems.append(f"write 2 or 3 bullets, never more than {MAX_BULLETS} (got {len(out.bullets)})")
    if any(not b.label.strip() or not b.text.strip() for b in out.bullets):
        problems.append("every bullet needs a label and a text")
    if out.opening.strip() and out.closing.strip() and out.bullets:
        total = word_count(EmailDraft(subject="", greeting=greeting, body=out, other_projects=other_projects or []).text())
        target = (MIN_WORDS + MAX_WORDS) // 2
        if total > MAX_WORDS:
            problems.append(f"the finished email is {total} words; cut about {total - target} words (limit {MAX_WORDS})")
        elif total < MIN_WORDS:
            problems.append(f"the finished email is {total} words; add about {target - total} words (minimum {MIN_WORDS})")
    if "**" in everything:
        problems.append("no markdown")

    for skill in missing_skills:
        if _skill_pattern(skill).search(main):
            problems.append(f"it mentions '{skill}', a skill the candidate lacks (allowed only in acknowledged_gap)")

    if YEARS_RE.search(everything):
        problems.append("it states a number of years; never mention years of experience")
    known_numbers = set(NUMBER_RE.findall(ctx.searchable))
    for n in dict.fromkeys(NUMBER_RE.findall(everything)):
        if n not in known_numbers:
            problems.append(f"the number '{n}' is not in the resume or cards")

    for m in DEGREE_RE.finditer(norm):
        field = re.sub(r"\s+", " ", m.group(1).lower().strip())
        if field and field != DEGREE_FIELD.lower():
            problems.append(f"degree field '{field}' is wrong; write exactly \"Bachelor's degree in {DEGREE_FIELD}\"")
    return problems


# ---------- prompt building and the model call ----------


def load_style_examples(context_dir: str | Path = "context") -> str:
    path = Path(context_dir) / "reference_examples.txt"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    text = path.read_text(encoding="utf-8").strip()
    log.info("style examples: %s (%d chars)", path.name, len(text))
    return text


def build_system_prompt(ctx: CandidateContext, style_examples: str) -> str:
    """Byte-identical for every job so the provider's prefix cache can hit."""
    return (
        f"{INSTRUCTIONS}\n\n=== CANDIDATE RESUME ===\n{ctx.resume_text}\n\n=== PROJECT CARDS ===\n{ctx.cards_text}"
        f"\n\n=== STYLE EXAMPLES (job posts and the emails the candidate wrote; copy the style, not the facts) ===\n"
        f"{style_examples}"
    )


def build_job_message(job: JobAnalysis, match: MatchResult) -> str:
    payload = {
        "job": {
            "company": job.company,
            "role_title": job.role_title,
            "required_skills": job.required_skills,
            "nice_to_have_skills": job.nice_to_have_skills,
            "special_requirements": job.special_requirements,
            "summary": job.summary,
            "business_need": job.business_need,
        },
        "matcher": {
            "selected_projects": [{"project_id": p.project_id, "name": p.name, "reason": p.reason} for p in match.selected_projects],
            "matched_skills": [{"skill": s.skill, "evidence": s.evidence} for s in match.matched_skills],
            "missing_skills": match.missing_skills,
            "email_angle_suggestion": match.email_angle,
        },
    }
    return "JOB AND MATCH:\n" + json.dumps(payload, ensure_ascii=False)


def write_email(
    job: JobAnalysis,
    match: MatchResult,
    ctx: CandidateContext,
    style_examples: str,
    client=None,
    model: str | None = None,
    max_attempts: int = 3,
) -> EmailDraft:
    client = client or get_client()
    model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    messages = [
        {"role": "system", "content": build_system_prompt(ctx, style_examples)},
        {"role": "user", "content": build_job_message(job, match)},
    ]
    greeting = make_greeting(job)
    others = other_project_names(match, ctx)
    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        log.info("writer calling %s (attempt %d/%d)", model, attempt, max_attempts)
        started = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        usage = getattr(resp, "usage", None)
        if usage:
            hit = getattr(usage, "prompt_cache_hit_tokens", None)
            miss = getattr(usage, "prompt_cache_miss_tokens", None)
            cache = f", cache hit/miss {hit}/{miss}" if hit is not None else ""
            log.info(
                "writer response in %.1fs, tokens in/out %d/%d%s",
                time.perf_counter() - started,
                usage.prompt_tokens,
                usage.completion_tokens,
                cache,
            )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            last_error = "empty response"
            log.warning("empty response from model; retrying")
            continue
        try:
            out = WriterOutput.model_validate(json.loads(content))
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:200]
            log.warning("invalid JSON or schema from model (%s); retrying", last_error)
            continue

        remaining = not_already_featured(others, out)
        problems = find_violations(out, ctx, match.missing_skills, greeting, remaining)
        if not problems:
            return EmailDraft(subject=make_subject(job), greeting=greeting, body=out, other_projects=remaining)

        last_error = "; ".join(problems)
        log.warning("draft rejected: %s", last_error)
        messages = messages[:2] + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": "Your draft broke these rules: " + "; ".join(problems) + ". Return the full corrected JSON.",
            },
        ]
    raise WriterError(f"no valid draft after {max_attempts} attempts: {last_error}")