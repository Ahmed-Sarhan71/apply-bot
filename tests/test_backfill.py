import base64

from scripts.backfill_bodies import extract_text


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_text_prefers_the_plain_part_and_decodes_it():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html copy</p>")}},
            {
                "mimeType": "multipart/related",
                "parts": [{"mimeType": "text/plain", "body": {"data": _b64("Dear team,\n\nplain copy")}}],
            },
        ],
    }
    assert extract_text(payload) == "Dear team,\n\nplain copy"
    assert extract_text({"mimeType": "text/html", "body": {"data": _b64("<p>x</p>")}}) == ""
