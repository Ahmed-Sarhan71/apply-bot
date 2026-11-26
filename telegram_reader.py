"""Collect job posts from Telegram channels into the inbox table. Nothing is analysed or sent here.

    uv run python telegram_reader.py            # save the recent posts, then keep listening for new ones
    uv run python telegram_reader.py --once     # save the recent posts and exit

The first run asks for your phone number and the code Telegram sends you; the login is cached in
credentials/telegram.session (gitignored). Treat that file like a password: it is your Telegram account.

.env:  TELEGRAM_API_ID, TELEGRAM_API_HASH (from my.telegram.org), TELEGRAM_CHANNELS=chan1,chan2
The same post in several channels is saved once, because the inbox is unique on the CLI's post_hash.
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from cli import post_hash
from database.connection import connect, save_inbox

log = logging.getLogger("jobbot.telegram")

MAX_AGE_DAYS = 90
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
MIN_CHARS = 40  # shorter than this cannot be a job post ("thanks!", a reaction, a join notice)
SESSION = Path(os.environ.get("GMAIL_CREDENTIALS", "credentials")) / "telegram"


def handle_message(con, channel: str, message_id: int, posted: datetime | None, text: str | None, max_age_days: int = MAX_AGE_DAYS, now: datetime | None = None) -> str:
    """Save one message. Returns 'saved', 'duplicate', 'old', 'short' or 'no_email'."""
    text = (text or "").strip()
    if len(text) < MIN_CHARS:
        return "short"
    if not EMAIL_RE.search(text):
        return "no_email"  # the bot applies by email only, so a post without an address is never worth a model call
    now = now or datetime.now(timezone.utc)
    if posted is not None:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if now - posted > timedelta(days=max_age_days):
            return "old"
    saved = save_inbox(
        con,
        post_hash=post_hash(text),
        text=text,
        channel=channel,
        message_id=message_id,
        link=f"https://t.me/{channel}/{message_id}",
        posted_at=posted.isoformat(timespec="seconds") if posted else None,
    )
    return "saved" if saved else "duplicate"


def parse_channels(raw: str) -> list[str]:
    out = []
    for c in raw.split(","):
        c = c.strip().removeprefix("https://t.me/").removeprefix("t.me/").removeprefix("@").strip("/")
        if c and c not in out:
            out.append(c)
    return out


async def run(channels: list[str], backfill: int, max_age_days: int, once: bool) -> None:
    from telethon import TelegramClient, events  # imported here so the tests do not need Telegram

    api_id, api_hash = os.environ["TELEGRAM_API_ID"], os.environ["TELEGRAM_API_HASH"]
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    con = connect()
    async with TelegramClient(str(SESSION), int(api_id), api_hash) as client:  # asks for phone + code the first time
        counts = {"saved": 0, "duplicate": 0, "old": 0, "short": 0, "no_email": 0}
        for ch in channels:
            ch_counts = dict.fromkeys(counts, 0)
            try:
                # newest first, so the first post past the cutoff means everything after it is older too
                async for m in client.iter_messages(ch, limit=backfill):
                    result = handle_message(con, ch, m.id, m.date, m.message, max_age_days)
                    ch_counts[result] += 1
                    if result == "old":
                        break
                else:
                    log.warning("%s: stopped at the --backfill limit (%d) before reaching %d days back", ch, backfill, max_age_days)
            except Exception as e:  # wrong username, private channel you have not joined, flood wait...
                log.error("%s: could not read (%s: %s)", ch, type(e).__name__, e)
                continue
            log.info("%s: %s", ch, ", ".join(f"{v} {k}" for k, v in ch_counts.items()))
            for k, v in ch_counts.items():
                counts[k] += v
        log.info("backfill done: %s", ", ".join(f"{v} {k}" for k, v in counts.items()))
        if once:
            return

        @client.on(events.NewMessage(chats=channels))
        async def on_new(event):
            username = getattr(event.chat, "username", None) or str(event.chat_id)
            result = handle_message(con, username, event.id, event.date, event.raw_text, max_age_days)
            log.info("new post in %s: %s", username, result)

        log.info("listening to %s (Ctrl-C to stop)", ", ".join(channels))
        await client.run_until_disconnected()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="save the recent posts and exit")
    parser.add_argument("--backfill", type=int, default=5000, help="most messages to read per channel (default 5000)")
    parser.add_argument("--days", type=int, default=MAX_AGE_DAYS, help="ignore posts older than this many days (default 90)")
    parser.add_argument("--channels", help="comma-separated usernames; default TELEGRAM_CHANNELS from .env")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("telethon", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    missing = [k for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH") if not os.environ.get(k)]
    channels = parse_channels(args.channels or os.environ.get("TELEGRAM_CHANNELS", ""))
    if missing or not channels:
        print(f"set {', '.join(missing) or 'TELEGRAM_CHANNELS'} in .env (see .env.example)")
        sys.exit(1)
    try:
        asyncio.run(run(channels, args.backfill, args.days, args.once))
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()