"""Send a drafted application email through the Gmail API, paced so Gmail doesn't see a burst.

One-time setup: put the OAuth desktop-app client at credentials/client_secret.json.
The first send opens a browser; the token is cached in credentials/token.json after that.
Both files are gitignored. Sends stay local until a caller passes --send.

The sender is the OAuth account itself (userId="me"), so no From address is configured.
"""

import base64
import logging
import os
import random
import time
from email.message import EmailMessage
from pathlib import Path

from ai.email_writer import EmailDraft

log = logging.getLogger("jobbot.sender")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CRED_DIR = Path(os.environ.get("GMAIL_CREDENTIALS", "credentials"))
# Gmail flags bursts and copies; a human-ish gap plus a varied body (the writer's) is what keeps it clean.
MIN_DELAY, MAX_DELAY = 60, 180


class SendError(RuntimeError):
    pass


class Pacer:
    """Holds the earliest moment the next email may go out, so drafting time counts toward the gap.

    The first send never waits. Call sent() right after a successful send.
    """

    def __init__(self, delay: tuple[float, float] = (MIN_DELAY, MAX_DELAY)):
        self.delay = delay
        self.next_send_at: float | None = None

    def wait(self) -> None:
        if self.next_send_at is None:
            return
        remaining = self.next_send_at - time.monotonic()
        if remaining > 0:
            log.info("waiting %.0fs before the next send", remaining)
            time.sleep(remaining)

    def sent(self) -> None:
        self.next_send_at = time.monotonic() + random.uniform(*self.delay)


def build_message(draft: EmailDraft, to: str, attachment: str | Path) -> EmailMessage:
    """Plain + HTML alternative plus the CV. The draft's CV line promises the attachment, so it is required."""
    path = Path(attachment)
    if not path.is_file():
        raise SendError(f"CV attachment not found: {path}")
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = draft.subject
    msg.set_content(draft.text())
    msg.add_alternative(draft.html(), subtype="html")
    msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    return msg


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token, secret = CRED_DIR / "token.json", CRED_DIR / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                raise SendError(
                    f"{secret} not found: create an OAuth desktop-app client in Google Cloud, "
                    "enable the Gmail API, and download the JSON there"
                )
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json())
    log.info("gmail service ready as %s", getattr(creds, "client_id", "?"))
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_email(draft: EmailDraft, to: str, attachment: str | Path, service) -> str:
    """Send one email; returns the Gmail message id."""
    raw = base64.urlsafe_b64encode(build_message(draft, to, attachment).as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info("sent to %s (id %s)", to, sent["id"])
    return sent["id"]
