"""One-off backfills for the applications table.

    uv run python -m scripts.backfill_bodies            # report posts that were sent but never recorded
    uv run python -m scripts.backfill_bodies --apply    # write those rows (hidden from All Applications)
    uv run python -m scripts.backfill_bodies --bodies   # also fill missing email bodies from Gmail's Sent folder

The Gmail part is read-only, with its own token (credentials/token_read.json) so the sender's token stays untouched.
"""

import argparse
import base64

from database.connection import already_sent, connect

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def extract_text(payload: dict) -> str:
    """First text/plain body, walking multipart payloads depth-first."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts") or []:
        found = extract_text(part)
        if found:
            return found
    return ""


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    from ai.email_sender import CRED_DIR

    token, secret = CRED_DIR / "token_read.json", CRED_DIR / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
            token.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def sent_without_row(con):
    """Inbox posts marked 'sent' that never got an applications row (the old RECORD_FROM gap)."""
    return con.execute(
        "SELECT * FROM inbox i WHERE i.result = 'sent'"
        " AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.post_hash = i.post_hash)"
        " ORDER BY i.id"
    ).fetchall()


def backfill_sent_rows(con, apply: bool = False) -> None:
    """Give every already-sent inbox post a row, hidden from All Applications (listed = 0).

    One address in the post: that address is used. None or several: reported only, never guessed — check Gmail by hand.
    """
    from telegram_reader import EMAIL_RE

    added, unclear, taken = [], [], []
    for row in sent_without_row(con):
        found = sorted({e.lower().rstrip(".") for e in EMAIL_RE.findall(row["text"])})
        if len(found) != 1:
            unclear.append(f"  id={row['id']}  {row['channel']}  {row['link'] or '-'}  -> {', '.join(found) or 'no address'}")
            continue
        to = found[0]
        if already_sent(con, to_email=to):
            taken.append(f"  id={row['id']}  {to}  (address already in applications)")
            continue
        if apply:
            con.execute(
                "INSERT INTO applications"
                " (applied_at, to_email, company, role_title, subject, body, post_text, post_hash, listed, status, updated_at)"
                " VALUES (?, ?, '', '', '', '', ?, ?, 0, 'sent', ?)",
                (row["saved_at"], to, row["text"], row["post_hash"], row["saved_at"]),
            )
            con.commit()
        added.append(f"  id={row['id']}  {to}  {row['post_hash']}")
    verb = "added" if apply else "would add"
    print(f"{verb} {len(added)} row(s):")
    for line in added:
        print(line)
    if taken:
        print(f"\nalready recorded, nothing to do ({len(taken)}):")
        for line in taken:
            print(line)
    if unclear:
        print(f"\nskipped, cannot tell which address was used ({len(unclear)}) — check Gmail Sent for these:")
        for line in unclear:
            print(line)
    if not apply and added:
        print("\ndry run: nothing written. Re-run with --apply.")


def backfill_bodies(con) -> None:
    """Fill applications.body from Gmail Sent for rows that predate body storage."""
    rows = con.execute("SELECT id, to_email FROM applications WHERE body IS NULL ORDER BY id").fetchall()
    if not rows:
        print("\nevery row already has a body")
        return
    svc = service()
    filled, missing = 0, []
    for row in rows:
        hits = (
            svc.users()
            .messages()
            .list(userId="me", q=f"in:sent to:{row['to_email']}", maxResults=1)
            .execute()
            .get("messages", [])
        )
        body = ""
        if hits:
            msg = svc.users().messages().get(userId="me", id=hits[0]["id"], format="full").execute()
            body = extract_text(msg["payload"]).strip()
        if not body:
            missing.append(row["to_email"])
            continue
        con.execute("UPDATE applications SET body = ? WHERE id = ?", (body, row["id"]))
        con.commit()
        filled += 1
        print(f"{row['id']:>3}  {row['to_email']}  {len(body)} chars")
    print(f"\nfilled {filled}, no sent copy for {len(missing)}")
    for email in missing:
        print("  ", email)


def main() -> None:
    parser = argparse.ArgumentParser(description="One-off backfills for the applications table")
    parser.add_argument("--apply", action="store_true", help="write the missing rows (default: report only)")
    parser.add_argument("--bodies", action="store_true", help="also fill missing email bodies from Gmail Sent")
    args = parser.parse_args()

    con = connect()
    backfill_sent_rows(con, apply=args.apply)
    if args.bodies:
        backfill_bodies(con)


if __name__ == "__main__":
    main()
