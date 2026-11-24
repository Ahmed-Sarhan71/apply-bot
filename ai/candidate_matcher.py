"""Candidate Matcher: JobAnalysis in, the best-fitting projects and honest skill gaps out.

The prompt is split so DeepSeek's automatic context cache can work:
  system message = fixed instructions + resume + project cards (identical on every call)
  user message   = the job (changes on every call)

Nothing here filters jobs. It only selects what to emphasise and records which
required skills the candidate does NOT have, so the email writer never claims them.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from ai.job_analyzer import JobAnalysis, get_client

log = logging.getLogger("jobbot.matcher")

MAX_PROJECTS = 3
CARD_HEADING_RE = re.compile(r"^## (\d+)\.\s+(.+?)\s*$", re.MULTILINE)
RANKING_HEADING_RE = re.compile(r"^## Ranking\b.*$", re.MULTILINE)
RANK_LINE_RE = re.compile(r"^Rank order[^:\n]*:\s*([\d,\s]+)$", re.MULTILINE)
CONTACT_RE = re.compile(r"@|\+\d{6,}|^\s*\+?[\d\s()-]{9,}\s*$|linkedin\.com", re.IGNORECASE)

INSTRUCTIONS = """You are the Candidate Matcher in a job-application assistant. You receive a candidate's resume, a set of numbered project cards, and then one job. Decide which of the candidate's projects best support an application to that job, and which required skills the candidate honestly lacks.

Return ONLY a JSON object with exactly these keys:

{
  "selected_projects": [{"project_id": integer, "reason": string}],
  "matched_skills": [{"skill": string, "evidence": string}],
  "missing_skills": [string],
  "experience_note": string or null,
  "email_angle": string
}

Rules:
- Use ONLY facts in the resume and project cards. Never invent skills, tools, employers, results or years of experience.
- A skill counts as matched only if the resume or a card explicitly shows it. Do not infer one skill from a related one (Docker is not Kubernetes, SQL Server is not AWS, a RAG app is not Azure AI Foundry).
- For every matched skill, "evidence" must be an exact quote, copied word for word (at most 12 words), from the resume or a project card. The quote must show the skill itself or a tool that directly implements it (for example "Matplotlib, Seaborn" is evidence for Data Visualization). If you cannot quote such evidence, the skill is missing, not matched.
- matched_skills and missing_skills together should cover the job's required skills. Keep each skill a short name copied from the job's skill list. Put nice-to-have skills in matched_skills only if the candidate has them; do not list unmatched nice-to-haves as missing.
- selected_projects: choose 2 or 3 project_id values (the number in each card heading), best first, following the PROJECT RANKING section that comes after the cards. First apply its promotions (for example a .NET or similar job puts Tennis Fusion first), then fill the remaining places from the top of the ranking, skipping a ranked project only when it has no connection at all to the job's work or requirements. Each reason is one short sentence naming the concrete overlap (a shared business problem or technology). If nothing connects well, still choose the 2 highest-ranked projects and say honestly what overlaps.
- experience_note: if the job asks for more years of experience or a higher seniority than the resume supports, write one honest, neutral sentence about the gap, using the dates in the resume and today's date from the job message. Otherwise null.
- email_angle: one sentence on what the application email should lead with, using only true facts from the resume and cards. Never suggest mentioning, admitting or apologising for a missing skill or a lack of experience: the email simply does not claim what the candidate lacks. Neither the angle nor any reason may claim a skill you list under missing_skills.
- Output JSON only, no commentary.

EXAMPLE JSON OUTPUT:
{
  "selected_projects": [
    {"project_id": 1, "reason": "A local RAG app with FastAPI and a vector database matches the job's RAG and FastAPI requirements."},
    {"project_id": 6, "reason": "Edge computer-vision pipeline in Python matches the computer vision requirement."}
  ],
  "matched_skills": [
    {"skill": "Python", "evidence": "Skilled in Python, backend development"},
    {"skill": "RAG", "evidence": "experience in AI agents, LLM orchestration, RAG, MCP servers"},
    {"skill": "Data Visualization", "evidence": "Matplotlib, Seaborn"}
  ],
  "missing_skills": ["Kubernetes", "Terraform"],
  "experience_note": "The job asks for 5+ years; the resume shows about two years of professional experience.",
  "email_angle": "Lead with the production-style RAG and agent-automation work, then the edge-AI project."
}"""


class MatcherError(RuntimeError):
    pass


@dataclass
class CandidateContext:
    resume_text: str
    cards_text: str
    project_names: dict[int, str]
    ranking_text: str = ""  # the "## Ranking" block of project_cards.md; kept out of cards_text so it is never evidence
    rank: list[int] = field(default_factory=list)  # card numbers, best first

    @property
    def searchable(self) -> str:
        """Resume + cards, lowercased with whitespace collapsed (so quotes survive PDF line wraps)."""
        return re.sub(r"\s+", " ", (self.resume_text + "\n" + self.cards_text).lower())


class ProjectPick(BaseModel):
    project_id: int
    reason: str = ""
    name: str = ""  # filled in by code from the card heading, never by the model


class MatchedSkill(BaseModel):
    skill: str
    evidence: str = ""


class MatchResult(BaseModel):
    selected_projects: list[ProjectPick] = Field(default_factory=list)
    matched_skills: list[MatchedSkill] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    experience_note: str | None = None
    email_angle: str = ""

    @field_validator("matched_skills", mode="before")
    @classmethod
    def _accept_plain_strings(cls, v):
        # tolerate a model that returns ["Python"] instead of [{"skill": "Python", "evidence": ...}]
        return [{"skill": x} if isinstance(x, str) else x for x in v] if isinstance(v, list) else v


def _read_resume(context_dir: Path) -> str:
    pdfs = sorted(context_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)  # newest first
    if len(pdfs) > 1:
        log.warning(
            "%d PDFs in %s; using the most recently modified: %s (ignoring: %s)",
            len(pdfs),
            context_dir,
            pdfs[0].name,
            ", ".join(p.name for p in pdfs[1:]),
        )
    if pdfs:
        from pypdf import PdfReader

        reader = PdfReader(str(pdfs[0]))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(pdfs[0].stat().st_mtime))
        log.info("resume: %s (modified %s, %d pages, %d chars)", pdfs[0].name, modified, len(reader.pages), len(text))
    else:
        texts = sorted([*context_dir.glob("resume*.txt"), *context_dir.glob("resume*.md")])
        if not texts:
            raise FileNotFoundError(f"no resume PDF (or resume*.txt/.md) found in {context_dir}")
        text = texts[0].read_text(encoding="utf-8")
        log.info("resume: %s (%d chars)", texts[0].name, len(text))
    # Contact details are not needed for matching; keep them out of the prompt.
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not CONTACT_RE.search(ln)]
    return "\n".join(lines)


def load_candidate_context(context_dir: str | Path = "context") -> CandidateContext:
    d = Path(context_dir)
    cards_path = d / "project_cards.md"
    if not cards_path.exists():
        raise FileNotFoundError(f"{cards_path} not found")
    raw = cards_path.read_text(encoding="utf-8")
    m = RANKING_HEADING_RE.search(raw)
    cards, ranking = (raw[: m.start()].rstrip(), raw[m.start() :].strip()) if m else (raw, "")
    if cards.endswith("---"):
        cards = cards[:-3].rstrip()
    names = {int(n): title for n, title in CARD_HEADING_RE.findall(cards)}
    if not names:
        raise ValueError(f"no '## 1. Project name' headings found in {cards_path}")
    rank = _parse_rank(ranking, names)
    log.info("project cards: %d projects, %d chars; rank order: %s", len(names), len(cards), rank)
    return CandidateContext(
        resume_text=_read_resume(d),
        cards_text=cards,
        project_names=names,
        ranking_text=ranking,
        rank=rank,
    )


def _parse_rank(ranking_text: str, names: dict[int, str]) -> list[int]:
    """'Rank order (card numbers, best first): 1, 8, 3' -> [1, 8, 3, <any cards not listed, in number order>]."""
    m = RANK_LINE_RE.search(ranking_text)
    listed = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else []
    unknown = [i for i in listed if i not in names]
    if unknown:
        log.warning("rank order lists card numbers that do not exist: %s", unknown)
    rank = list(dict.fromkeys(i for i in listed if i in names))
    return rank + [i for i in sorted(names) if i not in rank]


def build_system_prompt(ctx: CandidateContext) -> str:
    """Must be byte-identical for every job so the provider's prefix cache can hit."""
    ranking = f"\n\n=== PROJECT RANKING ===\n{ctx.ranking_text}" if ctx.ranking_text else ""
    return f"{INSTRUCTIONS}\n\n=== CANDIDATE RESUME ===\n{ctx.resume_text}\n\n=== PROJECT CARDS ===\n{ctx.cards_text}{ranking}"


def build_job_message(job: JobAnalysis, today: date) -> str:
    payload = {
        "today": today.isoformat(),
        "company": job.company,
        "role_title": job.role_title,
        "seniority": job.seniority,
        "min_years_experience": job.min_years_experience,
        "required_skills": job.required_skills,
        "nice_to_have_skills": job.nice_to_have_skills,
        "special_requirements": job.special_requirements,
        "work_mode": job.work_mode,
        "summary": job.summary,
    }
    return "JOB:\n" + json.dumps(payload, ensure_ascii=False)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _evidenced(skill: str, ctx: CandidateContext) -> bool:
    s = _norm(skill)
    if not s:
        return False
    hay = ctx.searchable
    return s in hay or (s.endswith("s") and s[:-1] in hay)


def _quote_in_context(quote: str, ctx: CandidateContext) -> bool:
    q = _norm(quote)
    return len(q) >= 3 and q in ctx.searchable


def _ground(result: MatchResult, ctx: CandidateContext) -> MatchResult:
    picks, seen = [], set()
    for p in result.selected_projects:
        if p.project_id not in ctx.project_names:
            log.warning("model chose unknown project_id %s; discarding it", p.project_id)
            continue
        if p.project_id in seen:
            continue
        seen.add(p.project_id)
        p.name = ctx.project_names[p.project_id]
        picks.append(p)
    result.selected_projects = picks[:MAX_PROJECTS]

    matched, missing = [], list(result.missing_skills)
    for m in result.matched_skills:
        if _quote_in_context(m.evidence, ctx):
            matched.append(m)
        elif _evidenced(m.skill, ctx):
            log.info("skill %r: quote not verifiable, but the skill name is in the resume; keeping it", m.skill)
            matched.append(m)
        else:
            log.warning("skill %r has no verifiable evidence (quote: %r); moving it to missing", m.skill, m.evidence)
            if _norm(m.skill) not in {_norm(x) for x in missing}:
                missing.append(m.skill)
    result.matched_skills, result.missing_skills = matched, missing
    return result


def match_candidate(
    job: JobAnalysis,
    ctx: CandidateContext,
    client=None,
    model: str | None = None,
    max_attempts: int = 3,
    today: date | None = None,
) -> MatchResult:
    client = client or get_client()
    model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    messages = [
        {"role": "system", "content": build_system_prompt(ctx)},
        {"role": "user", "content": build_job_message(job, today or date.today())},
    ]
    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        log.info("matcher calling %s (attempt %d/%d)", model, attempt, max_attempts)
        started = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
        elapsed = time.perf_counter() - started
        usage = getattr(resp, "usage", None)
        if usage:
            hit = getattr(usage, "prompt_cache_hit_tokens", None)
            miss = getattr(usage, "prompt_cache_miss_tokens", None)
            cache = f", cache hit/miss {hit}/{miss}" if hit is not None else ""
            log.info(
                "matcher response in %.1fs, tokens in/out %d/%d%s",
                elapsed,
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
            result = MatchResult.model_validate(json.loads(content))
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:200]
            log.warning("invalid JSON or schema from model (%s); retrying", last_error)
            continue
        return _ground(result, ctx)
    raise MatcherError(f"matching failed after {max_attempts} attempts: {last_error}")