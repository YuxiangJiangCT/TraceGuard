"""Each default pattern: >=3 positive (should match) and >=3 negative."""

from __future__ import annotations

import pytest

from spanredact.redaction.patterns import DEFAULT_PATTERNS
from spanredact.redaction.redactor import REDACTED, redact_text

POSITIVES = {
    "email": ["a@b.com", "ryan.jiang@cornell.edu", "x_y+z@sub.domain.io"],
    "us_ssn": ["123-45-6789", "001-01-0001", "999-99-9999"],
    "jwt": [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dozjgNryP4J3jVmNHl0w",
        "eyJ0eXAiOiJKV1QifQ.eyJpZCI6Mn0.abcDEF123_-",
        "eyJraWQiOiJrIn0.eyJyb2xlIjoiYSJ9.ZZZ999aaa",
    ],
    "us_phone": ["(212) 555-0173", "212-555-0173", "+1 212 555 0173"],
    # NOTE: these are obvious dummy strings (all-X, all-0). Realistic-looking
    # samples trigger GitHub secret-scanning false positives even when they're
    # made up — see https://docs.github.com/en/code-security/secret-scanning.
    "google_api_key": [
        "AIza" + "X" * 35,
        "AIza" + "0" * 35,
        "AIza" + "_" * 35,
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


def test_credit_card_requires_valid_luhn():
    """credit_card redacts only digit runs that pass the Luhn checksum, so a
    random 13-16 digit string isn't treated as a card. Tested in isolation
    from us_phone (which would otherwise grab 10 digits of any long run).

    Valid samples: all-zeros is an obvious dummy that still passes (sum 0);
    4111... and 3782... are the canonical published test-card numbers."""
    cc = [(name, rx) for name, rx in DEFAULT_PATTERNS if name == "credit_card"]
    for valid in ["0000000000000000", "4111 1111 1111 1111", "378282246310005"]:
        out, matched = redact_text(valid, patterns=cc)
        assert REDACTED in out, f"valid card {valid!r} not redacted"
        assert "credit_card" in matched
    for invalid in ["1234567890123456", "1111111111111111", "1234567890123"]:
        out, matched = redact_text(invalid, patterns=cc)
        assert out == invalid, f"invalid {invalid!r} wrongly redacted -> {out!r}"
        assert "credit_card" not in matched
