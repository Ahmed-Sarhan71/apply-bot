import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai.job_analyzer import AnalyzerError, analyze_job

SAMPLES = Path(__file__).parent / "samples"


class FakeClient:
    """Returns queued replies so the parsing and safety logic can be tested offline."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        content = self.replies.pop(0)
        if not isinstance(content, str):
            content = json.dumps(content)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def sample(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


def test_valid_email_kept_and_auto_apply():
    reply = {
        "company": "Omnix",
        "role_title": "Senior AI/ML Engineer",
        "apply_method": "email",
        "apply_email": "omnix.career@omnix.com",
        "required_subject": "Senior AI/ML Engineer",
    }
    a = analyze_job(sample("omnix.txt"), client=FakeClient(reply))
    assert a.apply_email == "omnix.career@omnix.com"
    assert a.required_subject == "Senior AI/ML Engineer"
    assert a.can_auto_apply


def test_hallucinated_email_is_dropped():
    reply = {"apply_method": "email", "apply_email": "hr@made-up.com"}
    a = analyze_job(sample("data_analyst_links.txt"), client=FakeClient(reply))
    assert a.apply_email is None
    assert a.apply_method == "none"
    assert not a.can_auto_apply


def test_hallucinated_subject_is_dropped():
    reply = {"apply_method": "email", "apply_email": "shaymaa.basiuny@flairstech.com", "required_subject": "Apply now"}
    a = analyze_job(sample("aws_data_engineer.txt"), client=FakeClient(reply))
    assert a.required_subject is None
    assert a.can_auto_apply


def test_missing_email_recovered_when_only_one_in_post():
    a = analyze_job(sample("aws_data_engineer.txt"), client=FakeClient({"apply_method": "email", "apply_email": None}))
    assert a.apply_email == "shaymaa.basiuny@flairstech.com"


def test_link_only_post_cannot_auto_apply():
    a = analyze_job(sample("data_analyst_links.txt"), client=FakeClient({"apply_method": "link", "multiple_roles": True}))
    assert not a.can_auto_apply


def test_blank_then_invalid_then_valid_retries():
    client = FakeClient("   ", "not json", {"apply_method": "link"})
    a = analyze_job("post", client=client)
    assert client.calls == 3 and a.apply_method == "link"


def test_gives_up_after_max_attempts():
    with pytest.raises(AnalyzerError):
        analyze_job("post", client=FakeClient("", "", ""))


def test_bad_enum_value_triggers_retry():
    client = FakeClient({"apply_method": "carrier pigeon"}, {"apply_method": "none"})
    assert analyze_job("post", client=client).apply_method == "none"


# ---- Live checks against the real model: run only when a key is set ----
live = pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set")


@live
def test_live_omnix():
    a = analyze_job(sample("omnix.txt"))
    assert a.apply_email == "omnix.career@omnix.com"
    assert a.required_subject == "Senior AI/ML Engineer"
    assert a.seniority == "senior" and a.min_years_experience == 5
    assert a.can_auto_apply


@live
def test_live_aws():
    a = analyze_job(sample("aws_data_engineer.txt"))
    assert a.apply_email == "shaymaa.basiuny@flairstech.com"
    assert a.required_subject is None
    assert a.work_mode == "hybrid"
    assert a.can_auto_apply


@live
def test_live_arabic_links():
    a = analyze_job(sample("data_analyst_links.txt"))
    assert a.apply_email is None and not a.can_auto_apply
    assert a.multiple_roles and a.post_language == "mixed"