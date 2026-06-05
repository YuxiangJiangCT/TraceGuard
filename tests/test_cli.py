"""CLI tests — mock Jaeger HTTP responses with httpx MockTransport.

We exercise: trace-not-found error, table render, json render, report
aggregation, Jaeger unreachable.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
from click.testing import CliRunner

from traceguard.cli import jaeger as jmod
from traceguard.cli.main import main

# Fixture: one Jaeger span carrying a redacted gen_ai.input.messages payload
# and the audit attributes TraceGuardSpanExporter writes.
_REDACTED_CONTENT = json.dumps(
    [{"role": "user", "parts": [{"type": "text", "content": "hi [REDACTED]"}]}]
)

_SPAN = {
    "operationName": "anthropic.chat",
    "spanID": "abc123",
    "tags": [
        {"key": "gen_ai.input.messages", "type": "string", "value": _REDACTED_CONTENT},
        {"key": "gen_ai.request.model", "type": "string", "value": "claude-haiku-4-5"},
        {"key": "gen_ai.usage.input_tokens", "type": "int64", "value": 27},
        {"key": "traceguard.redaction.applied", "type": "bool", "value": True},
        {"key": "traceguard.redaction.policy", "type": "string", "value": "balanced"},
        {"key": "traceguard.redaction.patterns_matched", "type": "string", "value": "email"},
    ],
}


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Pretend to be Jaeger's query API."""
    url = str(request.url)
    if url.endswith("/api/traces/notfound"):
        return httpx.Response(200, json={"data": []})
    if "/api/traces/" in url:
        return httpx.Response(200, json={"data": [{"spans": [_SPAN]}]})
    if "/api/traces" in url:
        return httpx.Response(200, json={"data": [{"spans": [_SPAN]}]})
    return httpx.Response(404)


def _install_mock():
    transport = httpx.MockTransport(_mock_handler)
    real_get = jmod.httpx.get

    def fake_get(url, params=None, timeout=None):
        client = httpx.Client(transport=transport)
        try:
            return client.get(url, params=params)
        finally:
            client.close()

    return patch.object(jmod.httpx, "get", side_effect=fake_get), real_get


# ---------- diff ----------------------------------------------------------


def test_diff_table_render_shows_redacted_and_policy():
    p, _ = _install_mock()
    with p:
        result = CliRunner().invoke(main, ["diff", "trace-1"])
    assert result.exit_code == 0, result.output
    assert "anthropic.chat" in result.output
    assert "balanced" in result.output
    assert "email" in result.output
    # the JSON content should show the redacted marker
    assert "[REDACTED]" in result.output


def test_diff_json_format():
    p, _ = _install_mock()
    with p:
        result = CliRunner().invoke(main, ["diff", "trace-1", "--format", "json"])
    assert result.exit_code == 0
    # the json output should parse and have our content key
    data = json.loads(result.output)
    assert data[0]["redacted"] is True
    assert data[0]["policy"] == "balanced"
    assert "email" in data[0]["patterns_matched"]
    assert "gen_ai.input.messages" in data[0]["content"]


def test_diff_missing_trace_is_clickexception():
    p, _ = _install_mock()
    with p:
        result = CliRunner().invoke(main, ["diff", "notfound"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_diff_jaeger_unreachable():
    def explode(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(explode)

    def fake_get(url, params=None, timeout=None):
        with httpx.Client(transport=transport) as c:
            return c.get(url, params=params)

    with patch.object(jmod.httpx, "get", side_effect=fake_get):
        result = CliRunner().invoke(main, ["diff", "trace-1"])
    assert result.exit_code != 0
    assert "Jaeger request failed" in result.output


# ---------- report --------------------------------------------------------


def test_report_aggregates_audit_attrs():
    p, _ = _install_mock()
    with p:
        result = CliRunner().invoke(main, ["report", "--service", "demo", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["spans_with_redaction"] == 1
    assert data["by_policy"] == {"balanced": 1}
    assert data["by_pattern"] == {"email": 1}


def test_report_table_render():
    p, _ = _install_mock()
    with p:
        result = CliRunner().invoke(main, ["report", "--service", "demo"])
    assert result.exit_code == 0
    assert "demo" in result.output
    assert "balanced" in result.output
    assert "email" in result.output
