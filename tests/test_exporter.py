"""End-to-end exporter behavior using InMemorySpanExporter as the downstream."""

from __future__ import annotations

import json

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from spanredact.policy.modes import Policy
from spanredact.redaction.exporter import SpanRedactExporter

GENAI_VALUE = json.dumps(
    [{"role": "user", "parts": [{"type": "text", "content": "email a@b.com"}]}]
)


def _run(policy: Policy):
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(
        SimpleSpanProcessor(SpanRedactExporter(memory, policy=policy))
    )
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("anthropic.chat") as span:
        span.set_attribute("gen_ai.input.messages", GENAI_VALUE)
        span.set_attribute("gen_ai.request.model", "claude-haiku-4-5")
        span.set_attribute("gen_ai.usage.input_tokens", 42)
    provider.shutdown()
    return memory.get_finished_spans()[0]


def test_balanced_redacts_content_keeps_metadata():
    span = _run(Policy.BALANCED)
    attrs = dict(span.attributes)
    assert "a@b.com" not in attrs["gen_ai.input.messages"]
    assert "[REDACTED]" in attrs["gen_ai.input.messages"]
    # metadata untouched
    assert attrs["gen_ai.request.model"] == "claude-haiku-4-5"
    assert attrs["gen_ai.usage.input_tokens"] == 42
    # JSON structure preserved
    assert json.loads(attrs["gen_ai.input.messages"])[0]["role"] == "user"
    # audit attrs
    assert attrs["spanredact.redaction.applied"] is True
    assert attrs["spanredact.redaction.policy"] == "balanced"
    assert "email" in attrs["spanredact.redaction.patterns_matched"]


def test_strict_drops_content():
    span = _run(Policy.STRICT)
    attrs = dict(span.attributes)
    assert "gen_ai.input.messages" not in attrs
    assert attrs["gen_ai.usage.input_tokens"] == 42
    assert attrs["spanredact.redaction.applied"] is True


def test_debug_passthrough():
    span = _run(Policy.DEBUG)
    attrs = dict(span.attributes)
    assert "a@b.com" in attrs["gen_ai.input.messages"]
    assert "spanredact.redaction.applied" not in attrs
