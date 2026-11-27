"""Interactive CLI to test the pipeline without WhatsApp.

    uv run python cli.py              # paste posts interactively
    uv run python cli.py -f posts.txt # read posts from a file
    uv run python cli.py --json       # also print the full JSON for each post

Paste one or many posts. Put a line containing only --- between posts.
Finish the paste with a line containing only END (or press Ctrl-D).
Type quit on its own line to exit.

Right now this is a dry run unless you pass --send.
"""

import argparse
import hashlib
import logging
import sys
import time
from collections.abc import Callable

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
from ai.email_sender import Pacer, SendError, get_service, send_email
from ai.email_writer import EmailDraft, WriterError, load_style_examples, write_email
from ai.job_analyzer import AnalyzerError, JobAnalysis, analyze_job
from database.connection import already_sent, connect, inbox_new, mark_inbox, record, record_failure

DEFAULT_LIST_FROM = "2026-10-01"  # older posts are still sent and recorded, just hidden from All Applications

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
            if not lines:  # stdin is done: quit instead of spinning forever
                return None
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


def show_email(d: EmailDraft, to: str | None, as_json: bool, send: bool = False) -> None:
    head = f"[bold]To:[/] {to or '-'}\n[bold]Subject:[/] {d.subject}\n\n"
    from rich.markup import escape  # so [brackets] inside the email are not read as styling

    title = f"email draft: {d.word_count()} words" + ("" if send else " — NOT SENT, no --send")
    console.print(Panel(head + escape(d.text()), title=title, border_style="magenta"))
    if as_json:
        console.print_json(d.model_dump_json())


def run_batch(
    raw: str,
    seen: set[str],
    as_json: bool,
    ctx: CandidateContext | None = None,
    style: str | None = None,
    send: bool = False,
    con=None,
    posts: list[str] | None = None,
    on_result: Callable[[str, str], None] | None = None,
    list_from: str = DEFAULT_LIST_FROM,
) -> dict[str, str]:
    """Run the pipeline on every post, sending each email as soon as it is written.

    Outcomes: sent, drafted, analyzed, no email, already applied, duplicate, failed.
    on_result(post_hash, outcome) fires once per post, whatever the outcome, so a caller can persist progress.
    """
    outcomes: dict[str, str] = {}
    posts = posts if posts is not None else split_posts(raw)
    if not posts:
        log.warning("nothing pasted")
        return outcomes
    log.info("received %d post(s)", len(posts))
    rows = []
    pacer = Pacer()
    service = None
    stop = False  # set when the failure would hit every later send (bad token, quota)
    for i, text in enumerate(posts, 1):
        if stop:
            break
        h = post_hash(text)
        first_line = text.splitlines()[0][:60]
        log.info("--- post %d/%d  id=%s  %d chars  %r", i, len(posts), h, len(text), first_line)
        try:
            if h in seen:
                log.warning("duplicate of a post already processed in this session; skipping")
                rows.append((i, first_line, "duplicate", "-", "-"))
                outcomes.setdefault(h, "duplicate")  # keep the real outcome of the first copy
                continue
            seen.add(h)
            if con is not None and already_sent(con, post_hash=h):
                log.warning("post %d was already applied to; skipping", i)
                rows.append((i, first_line, "already applied", "-", "-", "-", "-"))
                outcomes[h] = "already applied"
                continue
            started = time.perf_counter()
            try:
                a = analyze_job(text)
            except AnalyzerError as e:
                log.error("analysis FAILED: %s", e)
                record_failure(con, post_text=text, post_hash=h, reason=f"analysis: {e}")
                rows.append((i, first_line, "[red]failed[/]", "-", "-"))
                outcomes[h] = "failed"
                continue
            except Exception as e:  # network, auth, bad key...
                log.error("unexpected error: %s: %s", type(e).__name__, e)
                record_failure(con, post_text=text, post_hash=h, reason=f"{type(e).__name__}: {e}")
                rows.append((i, first_line, "[red]error[/]", "-", "-"))
                outcomes[h] = "failed"
                continue
            log.info("post %d done in %.1fs", i, time.perf_counter() - started)
            show_result(a, as_json)
            if con is not None and a.apply_email and already_sent(con, to_email=a.apply_email):
                log.warning("%s was already emailed; skipping", a.apply_email)
                rows.append((i, f"{a.role_title or '?'} / {a.company or '?'}", "already emailed", a.apply_method, a.apply_email, "-", "-"))
                outcomes[h] = "already applied"
                continue
            projects, drafted = "-", "-"
            if ctx is not None:
                try:
                    m = match_candidate(a, ctx)
                    show_match(m, as_json)
                    projects = ", ".join(str(p.project_id) for p in m.selected_projects) or "-"
                    if style is not None:
                        try:
                            draft = write_email(a, m, ctx, style)
                            show_email(draft, a.apply_email, as_json, send)
                            drafted = "[green]drafted[/]"
                            outcomes[h] = "drafted"
                            if send and a.can_auto_apply and a.apply_email:
                                try:
                                    if ctx.resume_path is None:
                                        raise SendError("no CV file: cannot send")
                                    service = service or get_service()
                                    pacer.wait()  # drafting time already ate into the gap
                                    message_id = send_email(draft, a.apply_email, ctx.resume_path, service)
                                    pacer.sent()
                                except SendError as e:  # auth, token, quota: every later send fails too
                                    log.error("sending FAILED, stopping the run: %s", e)
                                    record_failure(con, post_text=text, post_hash=h, reason=f"sending: {e}", company=a.company, role_title=a.role_title, to_email=a.apply_email)
                                    drafted = "[red]failed[/]"
                                    outcomes[h] = "failed"
                                    stop = True
                                except Exception as e:  # this one broke, the next may still go out
                                    log.error("send FAILED for %s: %s: %s", a.apply_email, type(e).__name__, e)
                                    record_failure(con, post_text=text, post_hash=h, reason=f"sending: {type(e).__name__}: {e}", company=a.company, role_title=a.role_title, to_email=a.apply_email)
                                    drafted = "[red]failed[/]"
                                    outcomes[h] = "failed"
                                else:
                                    _record_sent(con, text, h, a, draft, message_id, a.apply_email, list_from)
                                    drafted = "[green]sent[/]"
                                    outcomes[h] = "sent"
                        except WriterError as e:
                            log.error("writing FAILED: %s", e)
                            record_failure(con, post_text=text, post_hash=h, reason=f"writing: {e}", company=a.company, role_title=a.role_title, to_email=a.apply_email)
                            drafted = "[red]failed[/]"
                            outcomes[h] = "failed"
                except MatcherError as e:
                    log.error("matching FAILED: %s", e)
                    record_failure(con, post_text=text, post_hash=h, reason=f"matching: {e}", company=a.company, role_title=a.role_title, to_email=a.apply_email)
                    projects = "[red]failed[/]"
                    outcomes[h] = "failed"
                except Exception as e:
                    log.error("unexpected matcher/writer error: %s: %s", type(e).__name__, e)
                    record_failure(con, post_text=text, post_hash=h, reason=f"{type(e).__name__}: {e}", company=a.company, role_title=a.role_title, to_email=a.apply_email)
                    projects = "[red]error[/]"
                    outcomes[h] = "failed"
            if not a.can_auto_apply and outcomes.get(h) != "failed":
                outcomes[h] = "no email"
            outcomes.setdefault(h, "analyzed")
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
        finally:
            if on_result is not None:
                on_result(h, outcomes.get(h, "analyzed"))

    table = Table(title="batch summary")
    for col in ("#", "job", "result", "apply via", "email", "projects", "draft"):
        table.add_column(col)
    for r in rows:
        table.add_row(*[str(x) for x in r])
    console.print(table)
    return outcomes


def _record_sent(con, post_text: str, h: str, job: JobAnalysis, draft: EmailDraft, message_id: str, to: str, list_from: str) -> None:
    """Record every send so the address is never emailed twice. Posts older than list_from are just hidden."""
    if con is None:
        return
    row = con.execute("SELECT posted_at FROM inbox WHERE post_hash = ?", (h,)).fetchone()
    posted = row["posted_at"] if row else None
    listed = posted is None or posted >= list_from
    record(
        con,
        post_text=post_text,
        post_hash=h,
        to_email=to,
        company=job.company,
        role_title=job.role_title,
        subject=draft.subject,
        body=draft.text(),
        listed=listed,
    )
    when = f"posted {posted[:10]}" if posted else "pasted by hand"
    log.info("recorded %s, %s%s (gmail id %s)", to, when, "" if listed else ": hidden from All Applications", message_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", help="read posts from a file instead of pasting")
    parser.add_argument("--json", action="store_true", help="print the full JSON for each post")
    parser.add_argument("-q", "--quiet", action="store_true", help="hide step-by-step logs")
    parser.add_argument("--context", default="context", help="folder with the resume PDF and project_cards.md")
    parser.add_argument("--no-match", action="store_true", help="skip the candidate matcher (and the writer)")
    parser.add_argument("--no-write", action="store_true", help="skip the email writer")
    parser.add_argument("--send", action="store_true", help="actually send the drafts through Gmail (60-180s apart)")
    parser.add_argument("--inbox", action="store_true", help="process the saved Telegram posts (newest first) instead of pasting")
    parser.add_argument("--days", type=int, default=90, help="with --inbox: only posts from the last N days (default 90)")
    parser.add_argument("--retry-failed", action="store_true", help="with --inbox: also try the posts that failed last time")
    parser.add_argument("--limit", type=int, default=None, help="with --inbox: at most N posts per run (default: the whole inbox)")
    parser.add_argument(
        "--list-from",
        default=DEFAULT_LIST_FROM,
        help=f"posts older than this date (YYYY-MM-DD) are sent and recorded but hidden from All Applications (default {DEFAULT_LIST_FROM})",
    )
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

    if args.send and (ctx is None or style is None):
        console.print("[red]--send needs the matcher and the writer: fix the context folder first[/]")
        sys.exit(1)

    con = connect()
    log.info("db: %s", con.execute("PRAGMA database_list").fetchone()[2])
    seen: set[str] = set()
    if args.inbox:
        waiting = inbox_new(con, args.days, args.limit, args.retry_failed)
        log.info("inbox: %d new post(s) from the last %d days (limit: %s)", len(waiting), args.days, args.limit or "none")
        if not waiting:
            console.print("[yellow]nothing new in the inbox. Run telegram_reader.py first.[/]")
            return
        outcomes = run_batch(
            "",
            seen,
            args.json,
            ctx,
            style,
            args.send,
            con,
            posts=[r["text"] for r in waiting],
            # saved as it happens, so a Ctrl-C loses nothing; a dry run leaves the inbox untouched
            on_result=(lambda h, result: mark_inbox(con, h, result)) if args.send else None,
            list_from=args.list_from,
        )
        if args.send:
            failed = sum(1 for r in waiting if outcomes.get(r["post_hash"]) == "failed")
            console.print(
                f"[green]{len(waiting) - failed} done[/]"
                + (f", [red]{failed} failed[/] (kept; reason in the failures table, retry with --retry-failed)" if failed else "")
            )
        else:
            console.print("[dim]dry run: the posts stay in the inbox so you can run them again with --send[/]")
        return
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            run_batch(f.read(), seen, args.json, ctx, style, args.send, con, list_from=args.list_from)
        return
    while True:
        raw = read_paste()
        if raw is None:
            console.print("bye")
            return
        run_batch(raw, seen, args.json, ctx, style, args.send, con, list_from=args.list_from)


if __name__ == "__main__":
    main()