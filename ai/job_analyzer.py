"""Job Analyzer: raw job post text in, structured JobAnalysis out (DeepSeek, JSON mode).

The LLM only extracts facts. Whether we apply is decided by code (`can_auto_apply`),
and every extracted email is checked against the original post so a hallucinated
address can never be used.
"""

import json
import logging
import os
import re
import time
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("jobbot.analyzer")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

SYSTEM_PROMPT = """You extract structured data from job posts. Posts come from a WhatsApp channel, may be in English, Arabic or a mix, and are often messy (emojis, hashtags, duplicated text, several roles in one post).

Return ONLY a JSON object with exactly these keys:

{
  "company": string or null,
  "role_title": string or null,
  "apply_method": "email" | "link" | "dm" | "none",
  "apply_email": string or null,
  "required_subject": string or null,
  "seniority": "intern" | "junior" | "mid" | "senior" | "lead" | "unspecified",
  "min_years_experience": integer or null,
  "required_skills": [string],
  "nice_to_have_skills": [string],
  "responsibilities": [string],
  "location": string or null,
  "work_mode": "remote" | "hybrid" | "onsite" | "unspecified",
  "post_language": "en" | "ar" | "mixed",
  "multiple_roles": boolean,
  "special_requirements": [string],
  "summary": string,
  "business_need": string or null
}

Rules:
- Never invent anything. If the post does not say it, use null, [] or "unspecified".
- apply_email: copy the exact address written in the post. If several emails appear, pick the one for sending applications or CVs. If there is none, null.
- apply_method: "email" if candidates are asked to email a CV; "link" if they must apply through a URL; "dm" if they must message a person; "none" if the post gives no way to apply. If both an email and a link are given, use "email".
- required_subject: only if the post demands a specific email subject line; copy it exactly, without the surrounding quotes. Otherwise null.
- multiple_roles: true when the post advertises more than one distinct job.
- role_title: for multiple roles, use the first role listed.
- required_skills: concrete technologies or skills the post requires, short items, no sentences. nice_to_have_skills: those marked preferred or a plus.
- responsibilities: what the employer needs this person to do or achieve for the business, as at most 4 short phrases copied or tightly paraphrased from the post (for example "build data pipelines for document and image processing"). Empty list if the post does not say.
- special_requirements: hard conditions that are not skills (notice period, language, location, certifications, degree), one short string each.
- summary: one plain English sentence describing the job.
- business_need: what the employer is trying to achieve with this hire, in business terms (the problem the role exists to solve, such as turning raw data into reliable reports or cutting manual work). One short sentence in your own words, based only on the post's description of the work and its goals; null if the post gives no clue.
- Output JSON only, no commentary.

EXAMPLE JSON OUTPUT:
{
  "company": "Acme",
  "role_title": "Backend Engineer",
  "apply_method": "email",
  "apply_email": "jobs@acme.com",
  "required_subject": "Backend Engineer",
  "seniority": "mid",
  "min_years_experience": 3,
  "required_skills": ["Python", "FastAPI", "PostgreSQL"],
  "nice_to_have_skills": ["Docker"],
  "responsibilities": ["build and maintain Python APIs", "keep services reliable in production"],
  "location": "Cairo, Egypt",
  "work_mode": "hybrid",
  "post_language": "en",
  "multiple_roles": false,
  "special_requirements": ["Notice period under 30 days"],
  "summary": "Acme is hiring a mid-level backend engineer to build Python APIs.",
  "business_need": "Acme needs reliable APIs so its customer-facing apps can scale without outages."
}"""


class JobAnalysis(BaseModel):
    company: str | None = None
    role_title: str | None = None
    apply_method: Literal["email", "link", "dm", "none"] = "none"
    apply_email: str | None = None
    required_subject: str | None = None
    seniority: Literal["intern", "junior", "mid", "senior", "lead", "unspecified"] = "unspecified"
    min_years_experience: int | None = None
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    location: str | None = None
    work_mode: Literal["remote", "hybrid", "onsite", "unspecified"] = "unspecified"
    post_language: Literal["en", "ar", "mixed"] = "en"
    multiple_roles: bool = False
    special_requirements: list[str] = Field(default_factory=list)
    summary: str = ""
    business_need: str | None = None

    @property
    def can_auto_apply(self) -> bool:
        """Only a verified email address allows automatic sending."""
        return self.apply_method == "email" and bool(self.apply_email)


class AnalyzerError(RuntimeError):
    pass


def _normalize(s: str) -> str:
    return (
        s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").lower().strip()
    )


def _ground(a: JobAnalysis, post_text: str) -> JobAnalysis:
    """Drop anything the model claims that is not literally in the post."""
    found = {e.lower().rstrip(".") for e in EMAIL_RE.findall(post_text)}

    log.info("emails literally found in post: %s", sorted(found) or "none")
    claimed = (a.apply_email or "").strip().rstrip(".").lower()
    email = claimed
    if email not in found:
        if email:
            log.warning("model returned %r which is NOT in the post; discarding it", email)
        email = ""
    if not email and a.apply_method == "email" and len(found) == 1:
        email = next(iter(found))  # model said "email" but forgot the address; only one candidate exists
        log.info("model returned no email; recovered the only one in the post: %s", email)
    a.apply_email = email or None
    if a.apply_method == "email" and not a.apply_email:
        log.warning("apply_method was 'email' but no verified address; downgrading to 'none'")
        a.apply_method = "none"

    if a.required_subject and _normalize(a.required_subject) not in _normalize(post_text):
        log.warning("required_subject %r is not in the post; discarding it", a.required_subject)
        a.required_subject = None
    return a


def get_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def analyze_job(post_text: str, client=None, model: str | None = None, max_attempts: int = 3) -> JobAnalysis:
    client = client or get_client()
    model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": post_text.strip()},
    ]
    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        log.info("calling %s (attempt %d/%d, post %d chars)", model, attempt, max_attempts, len(post_text))
        started = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0,
        )
        elapsed = time.perf_counter() - started
        usage = getattr(resp, "usage", None)
        tokens = f", tokens in/out {usage.prompt_tokens}/{usage.completion_tokens}" if usage else ""
        log.info("response received in %.1fs%s", elapsed, tokens)
        content = (resp.choices[0].message.content or "").strip()
        if not content:  # DeepSeek returns blank content when it fails to produce valid JSON
            last_error = "empty response"
            log.warning("empty response from model; retrying")
            continue
        try:
            analysis = JobAnalysis.model_validate(json.loads(content))
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:200]
            log.warning("invalid JSON or schema from model (%s); retrying", last_error)
            continue
        return _ground(analysis, post_text)
    raise AnalyzerError(f"analysis failed after {max_attempts} attempts: {last_error}")