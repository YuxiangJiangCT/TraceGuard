"""Each default pattern: >=3 positive (should match) and >=3 negative."""

from __future__ import annotations

import pytest

from traceguard.redaction.redactor import REDACTED, redact_text

POSITIVES = {
    "email": ["a@b.com", "ryan.jiang@cornell.edu", "x_y+z@sub.domain.io"],
    "us_ssn": ["123-45-6789", "001-01-0001", "999-99-9999"],
    "jwt": [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dozjgNryP4J3jVmNHl0w",
        "eyJ0eXAiOiJKV1QifQ.eyJpZCI6Mn0.abcDEF123_-",
        "eyJraWQiOiJrIn0.eyJyb2xlIjoiYSJ9.ZZZ999aaa",
    ],
    "us_phone": ["(212) 555-0173", "212-555-0173", "+1 212 555 0173"],
    "google_api_key": [
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",
        "AIzaBCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "AIza00000000000000000000000000000000000",
    ],
}

NEGATIVES = {
    "email": ["not an email", "plainword", "@nodomain", "missing.at.sign"],
    "us_ssn": ["12-345-6789", "1234-56-789", "no ssn here"],
    "jwt": ["eyJonly", "regular.text.here", "abc.def"],
    "google_api_key": ["AIza-too-short", "BIzaSyA...", "no key"],
}


@pytest.mark.parametrize("name", POSITIVES.keys())
def test_positives_get_redacted(name):
    for sample in POSITIVES[name]:
        out, matched = redact_text(sample)
        assert REDACTED in out, f"{name}: {sample!r} not redacted"


@pytest.mark.parametrize("name", NEGATIVES.keys())
def test_negatives_untouched(name):
    for sample in NEGATIVES[name]:
        out, matched = redact_text(sample)
        assert out == sample, f"{name}: {sample!r} wrongly redacted -> {out!r}"


def test_api_key_prefixes():
    for sample in ["sk-ant-api03-abcdefghij1234567890XYZ", "ghp_abcdefghij1234567890abcd"]:
        out, _ = redact_text(sample)
        assert REDACTED in out
