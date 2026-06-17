"""redact_text + redact_attribute_value, incl. the real GenAI JSON shape (ADR-002)."""

from __future__ import annotations

import json

from spanredact.redaction.redactor import (
    REDACTED,
    redact_attribute_value,
    redact_text,
)


def test_redact_text_returns_matched_names():
    out, matched = redact_text("mail a@b.com and ssn 123-45-6789")
    assert REDACTED in out
    assert "a@b.com" not in out and "123-45-6789" not in out
    assert {"email", "us_ssn"} <= matched


def test_real_genai_json_shape_redacts_content_keeps_structure():
    # Exact shape verified in ADR-002.
    value = json.dumps(
        [{"role": "user", "parts": [{"type": "text", "content": "my email is a@b.com"}]}]
    )
    out, matched = redact_attribute_value(value)
    parsed = json.loads(out)
    # structure preserved
    assert parsed[0]["role"] == "user"
    assert parsed[0]["parts"][0]["type"] == "text"
    # content redacted
    assert "a@b.com" not in out
    assert parsed[0]["parts"][0]["content"] == "my email is [REDACTED]"
    assert "email" in matched


def test_non_json_falls_back_to_regex():
    out, matched = redact_attribute_value("plain text with a@b.com inside")
    assert "a@b.com" not in out
    assert REDACTED in out
    assert "email" in matched


def test_clean_json_unchanged_content_but_valid():
    value = json.dumps([{"role": "user", "parts": [{"type": "text", "content": "hello"}]}])
    out, matched = redact_attribute_value(value)
    assert json.loads(out)[0]["parts"][0]["content"] == "hello"
    assert matched == set()


def test_nested_strings_all_redacted():
    value = json.dumps({"a": ["x@y.com", {"b": "p@q.com"}], "c": "ok"})
    out, matched = redact_attribute_value(value)
    assert "x@y.com" not in out and "p@q.com" not in out
    assert json.loads(out)["c"] == "ok"
