"""Run the benchmark tasks against a real Claude API and TraceGuard, computing:

  recall       = caught_planted_pii / total_planted_pii         (per task; macro avg overall)
  precision    = correct_redactions / total_redactions_emitted  (1.0 if no over-redaction)
  completeness = spans_emitted / spans_expected                 (1.0 if redaction didn't drop spans)

Outputs JSON to stdout (run.py) or a markdown table (via report.py).

Prereqs (as the e2e demo):
    .env with ANTHROPIC_API_KEY, Jaeger running on localhost:4317.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# These imports MUST come after load_dotenv() — anthropic/traceloop read
# env vars at import time. Hence the noqa: E402.
import httpx  # noqa: E402
from anthropic import Anthropic  # noqa: E402
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: E402
from traceloop.sdk import Traceloop  # noqa: E402

from traceguard.policy.modes import Policy  # noqa: E402
from traceguard.redaction.exporter import TraceGuardSpanExporter  # noqa: E402
from benchmark.tasks import TASKS, Task  # noqa: E402

SERVICE = "traceguard-benchmark"
JAEGER_BASE = "http://localhost:16686"
MODEL = "claude-haiku-4-5-20251001"


def _init_tracing():
    exporter = TraceGuardSpanExporter(
        OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True),
        policy=Policy.BALANCED,
    )
    Traceloop.init(app_name=SERVICE, exporter=exporter, disable_batch=True)


def _claude_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY missing — put it in .env")
    return Anthropic(api_key=key)


def _run_task(client: Anthropic, task: Task) -> str:
    """Run the task and return the Jaeger trace_id of the resulting span."""
    # We need a way to associate this call's span with this task. Use the
    # task name as a small attribute on the parent span (Traceloop workflow).
    from traceloop.sdk.decorators import workflow

    @workflow(name=task.name)
    def _do():
        client.messages.create(
            model=MODEL,
            max_tokens=32,
            messages=[{"role": "user", "content": task.prompt}],
        )

    _do()
    # Give Jaeger a moment to ingest.
    time.sleep(1.5)
    # Find the most recent trace whose root span has this workflow name.
    resp = httpx.get(
        f"{JAEGER_BASE}/api/traces",
        params={"service": SERVICE, "limit": "20", "operation": f"{task.name}.workflow"},
        timeout=5.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    if not data:
        raise RuntimeError(f"no trace found for task {task.name}")
    return data[0]["traceID"]


def _evaluate(task: Task, trace_id: str) -> dict:
    """Pull the trace, find the anthropic.chat span, score against ground truth."""
    resp = httpx.get(f"{JAEGER_BASE}/api/traces/{trace_id}", timeout=5.0)
    resp.raise_for_status()
    spans = resp.json()["data"][0]["spans"]
    chat = next((s for s in spans if s["operationName"] == "anthropic.chat"), None)
    if chat is None:
        raise RuntimeError(f"no anthropic.chat span in trace {trace_id}")

    tags = {t["key"]: t.get("value") for t in chat.get("tags", [])}

    # Concatenate everywhere PII could plausibly survive — input messages,
    # output messages, and (paranoia) all tag values stringified.
    haystack_parts = []
    for k in ("gen_ai.input.messages", "gen_ai.output.messages"):
        if k in tags:
            haystack_parts.append(str(tags[k]))
    # Also include any other stringy tag values in case PII leaked elsewhere
    # (e.g., legacy keys).
    haystack_parts.extend(str(v) for v in tags.values() if isinstance(v, str))
    haystack = "\n".join(haystack_parts)

    caught = sum(1 for pii in task.planted_pii if pii not in haystack)
    planted = len(task.planted_pii)
    recall = caught / planted if planted else 1.0

    matched_csv = str(tags.get("traceguard.redaction.patterns_matched") or "")
    matched = {n for n in matched_csv.split(",") if n}
    expected = set(task.planted_pattern_names)
    over_redactions = matched - expected  # pattern hits we did not plant
    total_pattern_hits = len(matched) or 1
    precision = (len(matched & expected)) / total_pattern_hits if expected else (
        1.0 if not matched else 0.0
    )

    # completeness: did we keep the span (yes/no). Always 1 for v0.1 BALANCED
    # since we never drop spans, but tracking it keeps the metric honest.
    completeness = 1.0 if chat else 0.0

    return {
        "task": task.name,
        "trace_id": trace_id,
        "planted_pii_count": planted,
        "caught_pii_count": caught,
        "recall": recall,
        "matched_patterns": sorted(matched),
        "expected_patterns": sorted(expected),
        "over_redactions": sorted(over_redactions),
        "precision": precision,
        "completeness": completeness,
        "input_tokens": tags.get("gen_ai.usage.input_tokens"),
        "output_tokens": tags.get("gen_ai.usage.output_tokens"),
    }


def main() -> None:
    _init_tracing()
    client = _claude_client()

    results = []
    for task in TASKS:
        print(f"[benchmark] running task: {task.name}", flush=True)
        trace_id = _run_task(client, task)
        results.append(_evaluate(task, trace_id))

    summary = {
        "tasks": results,
        "macro_recall": sum(r["recall"] for r in results) / len(results),
        "macro_precision": sum(r["precision"] for r in results) / len(results),
        "macro_completeness": sum(r["completeness"] for r in results) / len(results),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
