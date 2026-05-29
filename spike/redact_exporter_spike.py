"""Architecture spike for TraceGuard.

Single question this spike answers:
    Can a custom SpanExporter wrapper redact a span attribute value before
    the wrapped (downstream) exporter sees it?

Approach (per research, verified against opentelemetry-sdk 1.42.1):
    ReadableSpan.attributes is a read-only MappingProxyType view, so we
    CANNOT mutate span._attributes. Instead we construct a NEW ReadableSpan
    with redacted attributes (its __init__ is public and accepts `attributes`)
    and forward that to the wrapped exporter.

This is a throwaway proof-of-concept. It uses a mock span (no real LLM, no
Jaeger) and the ConsoleSpanExporter so we can eyeball the output. Run with:

    uv run --python .venv-spike python spike/redact_exporter_spike.py

Exit code 0 = pipeline works (redacted value present, raw secret absent).
Exit code 1 = redaction failed (raw secret leaked to downstream).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

# Attribute keys whose values we treat as potentially PII-bearing. In the real
# library this becomes the GenAI content-carrying key set (gen_ai.input.messages,
# gen_ai.output.messages, legacy gen_ai.prompt / gen_ai.completion, ...).
PII_PRONE_KEYS = {"gen_ai.prompt", "gen_ai.completion"}

# Minimal email regex — just enough for the spike. The real patterns module
# (Week 3) will have email / SSN / phone / card / api-key / JWT.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _redact_value(value: object) -> object:
    """Replace any email found in a string value with [REDACTED]."""
    if isinstance(value, str):
        return _EMAIL_RE.sub("[REDACTED]", value)
    return value


class RedactingSpanExporter(SpanExporter):
    """Wraps another SpanExporter and redacts PII-prone attributes first.

    Because ReadableSpan is read-only, we rebuild each span as a fresh
    ReadableSpan with sanitized attributes, then delegate to the wrapped
    exporter.
    """

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        sanitized: list[ReadableSpan] = []
        for span in spans:
            attrs = dict(span.attributes or {})
            for key in list(attrs):
                if key in PII_PRONE_KEYS:
                    attrs[key] = _redact_value(attrs[key])
            # Rebuild the span with redacted attributes. Use
            # instrumentation_scope only (instrumentation_info is deprecated
            # since opentelemetry-sdk 1.11.1).
            sanitized.append(
                ReadableSpan(
                    name=span.name,
                    context=span.context,
                    parent=span.parent,
                    resource=span.resource,
                    attributes=attrs,
                    events=span.events,
                    links=span.links,
                    kind=span.kind,
                    instrumentation_scope=span.instrumentation_scope,
                    status=span.status,
                    start_time=span.start_time,
                    end_time=span.end_time,
                )
            )
        return self._wrapped.export(sanitized)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def main() -> int:
    secret = "my email is leak@test.com please redact"

    # Capture the console exporter's output so we can assert on it.
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()

    provider = TracerProvider()
    provider.add_span_processor(
        SimpleSpanProcessor(RedactingSpanExporter(ConsoleSpanExporter(out=buffer)))
    )
    tracer = provider.get_tracer("traceguard.spike")

    with tracer.start_as_current_span("gen_ai.chat") as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.prompt", secret)
        span.set_attribute("gen_ai.usage.input_tokens", 42)

    provider.shutdown()

    output = buffer.getvalue()
    # Mirror the (redacted) console output to the real stdout for the human.
    print(output)

    leaked = "leak@test.com" in output
    redacted = "[REDACTED]" in output
    metadata_preserved = '"gen_ai.system": "anthropic"' in output

    print("=" * 60)
    print(f"raw secret leaked?      {leaked}   (want: False)")
    print(f"[REDACTED] present?     {redacted}   (want: True)")
    print(f"metadata preserved?     {metadata_preserved}   (want: True)")
    print("=" * 60)

    if leaked or not redacted or not metadata_preserved:
        print("SPIKE FAILED")
        return 1
    print("SPIKE PASSED — SpanExporter wrapper can redact via ReadableSpan rebuild")
    return 0


if __name__ == "__main__":
    sys.exit(main())
