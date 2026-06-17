"""Thin Jaeger HTTP API client — only the bits the CLI needs.

We deliberately don't depend on a Jaeger SDK; the v1 query API is stable and
documented (https://www.jaegertracing.io/docs/1.76/apis/) and we only call:
  GET /api/traces/{trace_id}      -> one trace's spans
  GET /api/traces?service=&limit= -> recent traces by service

Returns plain dicts. Higher layers (cli/main.py) parse them.
"""

from __future__ import annotations

import httpx

DEFAULT_JAEGER_QUERY = "http://localhost:16686"


class JaegerError(RuntimeError):
    """Raised when Jaeger is unreachable or returns an unexpected shape."""


def _get(url: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(url, params=params, timeout=5.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise JaegerError(f"Jaeger request failed ({url}): {exc}") from exc


def fetch_trace(trace_id: str, base: str = DEFAULT_JAEGER_QUERY) -> list[dict]:
    """Return the spans of a single trace, or raise JaegerError."""
    data = _get(f"{base.rstrip('/')}/api/traces/{trace_id}")
    traces = data.get("data") or []
    if not traces:
        raise JaegerError(f"trace {trace_id} not found in Jaeger at {base}")
    return traces[0].get("spans", [])


def fetch_recent_traces(
    service: str, limit: int = 20, base: str = DEFAULT_JAEGER_QUERY
) -> list[dict]:
    """Return up to `limit` recent traces for a service (each a dict with spans)."""
    data = _get(
        f"{base.rstrip('/')}/api/traces",
        params={"service": service, "limit": str(limit)},
    )
    return data.get("data") or []


def tags_to_dict(span: dict) -> dict[str, object]:
    """Jaeger spans store attributes as a list of {key, type, value}. Flatten."""
    return {t["key"]: t.get("value") for t in span.get("tags", [])}
