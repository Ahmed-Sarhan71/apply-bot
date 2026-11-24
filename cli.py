"""Interactive CLI to test the pipeline without WhatsApp.

    uv run python cli.py              # paste posts interactively
    uv run python cli.py -f posts.txt # read posts from a file
    uv run python cli.py --json       # also print the full JSON for each post

Paste one or many posts. Put a line containing only --- between posts.
Finish the paste with a line containing only END (or press Ctrl-D).
Type quit on its own line to exit.

Right now this is a dry run: nothing is sent anywhere.
"""

import argparse
import hashlib
import logging
import sys
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from ai.candidate_matcher import (
    CandidateContext,
    MatcherError,
    MatchResult,
    load_candidate_context,
    match_candidate,
)
from ai.email_writer import EmailDraft, WriterError, load_style_examples, write_email
from ai.job_analyzer import AnalyzerError, JobAnalysis, analyze_job

console = Console()
log = logging.getLogger("jobbot.cli")

SEPARATOR = "---"
END = "END"


def split_posts(raw: str) -> list[str]:
    """Split pasted text into posts on lines that contain only '---'."""
    posts, current = [], []
    for line in raw.splitlines():
        if line.strip() == SEPARATOR:
            posts.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    posts.append("\n".join(current).strip())
    return [p for p in posts if p]


def post_hash(text: str) -> str:
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:10]


def read_paste() -> str | None:
    """Read lines until END or Ctrl-D. Returns None when the user wants to quit."""
    console.print(
        f"\n[bold cyan]Paste job post(s).[/] Separate posts with a line [bold]{SEPARATOR}[/], "
        f"finish with a line [bold]{END}[/] (or Ctrl-D). [dim]Type quit to exit.[/]"
    )
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not lines and line.strip().lower() in {"quit", "exit", "q"}:
            return None
        if line.strip() == END:
            break
        lines.append(line)
    return "\n".join(lines)


def show_result(a: JobAnalysis, as_json: bool) -> None:
    status = "[green]READY to apply[/]" if a.can_auto_apply else "[yellow]CANNOT auto-apply (no verified email)[/]"
    body = (
        f"[bold]{a.role_title or '?'}[/] at [bold]{a.company or '?'}[/]   {status}\n"
        f"apply via: {a.apply_method}   email: {a.apply_email or '-'}   required subject: {a.required_subject or '-'}\n"
        f"seniority: {a.seniority}   years: {a.min_years_experience or '-'}   {a.work_mode}   {a.location or ''}\n"
        f"skills: {', '.join(a.required_skills[:12]) or '-'}\n"
        f"extra: {'; '.join(a.special_requirements) or '-'}\n"
        f"business need: {a.business_need or '-'}\n"
        f"[dim]{a.summary}[/]"
    )
    console.print(Panel(body, title="analysis", border_style="green" if a.can_auto_apply else "yellow"))
    if as_json:
        console.print_json(a.model_dump_json())


def show_match(m: MatchResult, as_json: bool) -> None:
    picks = "\n".join(f"  {i}. [bold]{p.name}[/]\n     [dim]{p.reason}[/]" for i, p in enumerate(m.selected_projects, 1))
    body = (
        f"[bold]projects to feature:[/]\n{picks or '  -'}\n"
        f"[green]matched skills:[/] {', '.join(s.skill for s in m.matched_skills) or '-'}\n"
        f"[red]missing skills (never claim):[/] {', '.join(m.missing_skills) or '-'}\n"
        f"experience: {m.experience_note or '-'}\n"
        f"[bold]email angle:[/] {m.email_angle or '-'}"
    )
    console.print(Panel(body, title="match", border_style="blue"))
    if as_json:
        console.print_json(m.model_dump_json())


def show_email(d: EmailDraft, to: str | None, as_json: bool) -> None:
    head = f"[bold]To:[/] {to or '-'}\n[bold]Subject:[/] {d.subject}\n\n"
    from rich.markup import escape  # so [brackets] inside the email are not read as styling

    console.print(Panel(head + escape(d.text()), title=f"email draft: {d.word_count()} words (dry run, nothing is sent)", border_style="magenta"))
    if as_json:
        console.print_json(d.model_dump_json())


def run_batch(
    raw: str,
    seen: set[str],
    as_json: bool,
    ctx: CandidateContext | None = None,
    style: str | None = None,
) -> None:
    posts = split_posts(raw)
    if not posts:
        log.warning("nothing pasted")
        return
    log.info("received %d post(s)", len(posts))
    rows = []
    for i, text in enumerate(posts, 1):
        h = post_hash(text)
        first_line = text.splitlines()[0][:60]
        log.info("--- post %d/%d  id=%s  %d chars  %r", i, len(posts), h, len(text), first_line)
        if h in seen:
            log.warning("duplicate of a post already processed in this session; skipping")
            rows.append((i, first_line, "duplicate", "-", "-"))
            continue
        seen.add(h)
        started = time.perf_counter()
        try:
            a = analyze_job(text)
        except AnalyzerError as e:
            log.error("analysis FAILED: %s", e)
            rows.append((i, first_line, "[red]failed[/]", "-", "-"))
            continue
        except Exception as e:  # network, auth, bad key...
            log.error("unexpected error: %s: %s", type(e).__name__, e)
            rows.append((i, first_line, "[red]error[/]", "-", "-"))
            continue
        log.info("post %d done in %.1fs", i, time.perf_counter() - started)
        show_result(a, as_json)
        projects, drafted = "-", "-"
        if ctx is not None:
            try:
                m = match_candidate(a, ctx)
                show_match(m, as_json)
                projects = ", ".join(str(p.project_id) for p in m.selected_projects) or "-"
                if style is not None:
                    try:
                        draft = write_email(a, m, ctx, style)
                        show_email(draft, a.apply_email, as_json)
                        drafted = "[green]drafted[/]"
                    except WriterError as e:
                        log.error("writing FAILED: %s", e)
                        drafted = "[red]failed[/]"
            except MatcherError as e:
                log.error("matching FAILED: %s", e)
                projects = "[red]failed[/]"
            except Exception as e:
                log.error("unexpected matcher/writer error: %s: %s", type(e).__name__, e)
                projects = "[red]error[/]"
        verdict = "[green]ready[/]" if a.can_auto_apply else "[yellow]no email[/]"
        rows.append(
            (
                i,
                f"{a.role_title or '?'} / {a.company or '?'}",
                verdict,
                a.apply_method,
                a.apply_email or "-",
                projects,
                drafted,
            )
        )

    table = Table(title="batch summary")
    for col in ("#", "job", "result", "apply via", "email", "projects", "draft"):
        table.add_column(col)
    for r in rows:
        table.add_row(*[str(x) for x in r])
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", help="read posts from a file instead of pasting")
    parser.add_argument("--json", action="store_true", help="print the full JSON for each post")
    parser.add_argument("-q", "--quiet", action="store_true", help="hide step-by-step logs")
    parser.add_argument("--context", default="context", help="folder with the resume PDF and project_cards.md")
    parser.add_argument("--no-match", action="store_true", help="skip the candidate matcher (and the writer)")
    parser.add_argument("--no-write", action="store_true", help="skip the email writer")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False, markup=False)],
    )
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print("[red]DEEPSEEK_API_KEY is not set. Put it in .env[/]")
        sys.exit(1)
    log.info("model: %s", os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"))

    ctx = None
    if not args.no_match:
        try:
            ctx = load_candidate_context(args.context)
        except (FileNotFoundError, ValueError) as e:
            log.error("matcher disabled: %s", e)

    style = None
    if ctx is not None and not args.no_write:
        try:
            style = load_style_examples(args.context)
        except FileNotFoundError as e:
            log.error("writer disabled: %s", e)

    seen: set[str] = set()
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            run_batch(f.read(), seen, args.json, ctx, style)
        return
    while True:
        raw = read_paste()
        if raw is None:
            console.print("bye")
            return
        run_batch(raw, seen, args.json, ctx, style)


if __name__ == "__main__":
    main()