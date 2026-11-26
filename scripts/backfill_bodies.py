"""One-off: fill applications.body from Gmail's Sent folder for rows that predate body storage.

Read-only scope, its own token (credentials/token_read.json) so the sender's token stays untouched.
"""

import base64

from database.connection import connect

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


def main() -> None:
    con = connect()
    rows = con.execute("SELECT id, to_email FROM applications WHERE body IS NULL ORDER BY id").fetchall()
    if not rows:
        print("every row already has a body")
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


if __name__ == "__main__":
    main()
