"""Public init/attach entry points.

    from spanredact import init
    init(policy="balanced")

init() builds a TracerProvider whose exporter is SpanRedactExporter wrapping
an OTLP exporter (or a caller-supplied downstream exporter), then registers it
globally. attach() adds redaction to an existing provider by wrapping a
downstream exporter the caller already has.

WARNING: init() registers a global TracerProvider via
trace.set_tracer_provider(). OpenLLMetry's Traceloop.init() registers its own
global provider too, and only one global provider can win — combining them
means one is silently ignored (which one depends on init order), so redaction
may not run. Do NOT use spanredact.init() together with Traceloop.init(). If
you use OpenLLMetry, prefer the documented path: wrap your exporter with
SpanRedactExporter and pass it to Traceloop.init(exporter=...).
spanredact.init() / attach() are for plain-OTel setups that do NOT use Traceloop.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from .policy.modes import Policy
from .redaction.exporter import SpanRedactExporter


def _resolve_policy(policy: str | Policy | None) -> Policy:
    if isinstance(policy, Policy):
        return policy
    # explicit arg wins; else env var; else balanced.
    return Policy.from_str(policy if policy is not None else os.getenv("SPANREDACT_POLICY"))


def _default_otlp_exporter() -> SpanExporter:
    # Imported lazily so the OTLP exporter isn't a hard dependency of the core.
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    return OTLPSpanExporter(endpoint=endpoint, insecure=True)


def init(
    policy: str | Policy | None = None,
    exporter: SpanExporter | None = None,
    *,
    set_global: bool = True,
) -> TracerProvider:
    """Initialize a TracerProvider with SpanRedact redaction.

    Args:
        policy: "strict" | "balanced" | "debug". Defaults to env SPANREDACT_POLICY
            or "balanced".
        exporter: downstream SpanExporter to wrap. Defaults to an OTLP gRPC
            exporter at OTEL_EXPORTER_OTLP_ENDPOINT (or localhost:4317).
        set_global: register as the global tracer provider.
    """
    resolved = _resolve_policy(policy)
    downstream = exporter or _default_otlp_exporter()
    guarded = SpanRedactExporter(downstream, policy=resolved)

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(guarded))
    if set_global:
        trace.set_tracer_provider(provider)
    return provider


def attach(
    provider: TracerProvider,
    exporter: SpanExporter,
    policy: str | Policy | None = None,
) -> TracerProvider:
    """Add SpanRedact redaction to an EXISTING provider by wrapping `exporter`.

    For users who already set up OpenLLMetry/OTel themselves and just want the
    redaction layer in front of their exporter.
    """
    resolved = _resolve_policy(policy)
    guarded = SpanRedactExporter(exporter, policy=resolved)
    provider.add_span_processor(BatchSpanProcessor(guarded))
    return provider
