"""SpanRedact — privacy-first redaction for OpenTelemetry GenAI traces.

Public API:
    from spanredact import init
    init(policy="balanced")        # wraps the OTLP exporter with redaction

    from spanredact import attach
    attach(tracer_provider, ...)   # add redaction to an existing provider

    from spanredact import add_pattern
    add_pattern("internal_id", r"INT-\\d{6}")
"""

from __future__ import annotations

from .init import attach, init
from .redaction.patterns import add_pattern

__version__ = "0.1.0"

__all__ = ["init", "attach", "add_pattern", "__version__"]
