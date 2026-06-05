"""TraceGuardSpanExporter — wraps a downstream SpanExporter and redacts PII.

Productionized version of spike/redact_exporter_spike.py (mechanism verified in
ADR-001: ReadableSpan is read-only, so we build a NEW ReadableSpan with cleaned
attributes and forward that).

Behavior depends on policy (ADR + Week 4):
  strict   — drop content attributes (gen_ai.input/output.messages, ...).
  balanced — redact PII inside content (JSON-aware via redact_attribute_value).
  debug    — passthrough unchanged.

Redacted spans get audit attributes:
  traceguard.redaction.applied = True
  traceguard.redaction.policy  = "balanced"
  traceguard.redaction.patterns_matched = "email,us_phone"  (sorted, comma-join)
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from ..policy.modes import CONTENT_KEYS, Policy
from .redactor import redact_attribute_value


class TraceGuardSpanExporter(SpanExporter):
    def __init__(
        self,
        wrapped: SpanExporter,
        policy: Policy = Policy.BALANCED,
        content_keys: Sequence[str] = CONTENT_KEYS,
    ) -> None:
        self._wrapped = wrapped
        self._policy = policy
        self._content_keys = tuple(content_keys)

    # -- core ---------------------------------------------------------------

    def _sanitize_attributes(self, attrs: dict) -> tuple[dict, set[str], bool]:
        """Return (new_attrs, matched_patterns, changed)."""
        matched: set[str] = set()
        changed = False
        out = dict(attrs)
        for key in self._content_keys:
            if key not in out:
                continue
            if self._policy is Policy.STRICT:
                del out[key]
                changed = True
            elif self._policy is Policy.BALANCED:
                cleaned, found = redact_attribute_value(out[key])
                if cleaned != out[key]:
                    changed = True
                out[key] = cleaned
                matched |= found
            # DEBUG: leave untouched.
        return out, matched, changed

    def _rebuild(self, span: ReadableSpan) -> ReadableSpan:
        attrs = dict(span.attributes or {})
        new_attrs, matched, changed = self._sanitize_attributes(attrs)
        if changed or matched:
            new_attrs["traceguard.redaction.applied"] = True
            new_attrs["traceguard.redaction.policy"] = self._policy.value
            new_attrs["traceguard.redaction.patterns_matched"] = ",".join(
                sorted(matched)
            )
        # ReadableSpan is read-only; construct a fresh one (ADR-001). Use
        # instrumentation_scope only (instrumentation_info deprecated).
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=new_attrs,
            events=span.events,
            links=span.links,
            kind=span.kind,
            instrumentation_scope=span.instrumentation_scope,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
        )

    # -- SpanExporter interface ---------------------------------------------

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._policy is Policy.DEBUG:
            return self._wrapped.export(spans)
        return self._wrapped.export([self._rebuild(s) for s in spans])

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)
