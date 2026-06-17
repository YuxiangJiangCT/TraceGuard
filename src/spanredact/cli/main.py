"""`spanredact` CLI entry point.

Subcommands:
  diff <trace_id>   Inspect a Jaeger trace SpanRedact touched — shows the
                    sanitized GenAI content JSON pretty-printed, the patterns
                    that matched, and the audit attributes. NOT a real
                    before/after diff: the original PII never reaches Jaeger
                    by design, so we render the "what was redacted" picture
                    instead, sourced from `spanredact.redaction.*` audit
                    attributes left on the span.

  report --service S [--since 1h] [--limit 20]
                    Pull recent traces for a service and aggregate audit
                    stats: how many spans had redaction applied, by policy,
                    by which patterns matched.

Both honor --jaeger URL (default http://localhost:16686) and --format.
"""

from __future__ import annotations

import json
from collections import Counter

import click
from rich.console import Console
from rich.table import Table

from .jaeger import DEFAULT_JAEGER_QUERY, JaegerError, fetch_recent_traces, fetch_trace, tags_to_dict

CONTENT_KEYS = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.prompt",
    "gen_ai.completion",
)
AUDIT_KEYS = (
    "spanredact.redaction.applied",
    "spanredact.redaction.policy",
    "spanredact.redaction.patterns_matched",
)

console = Console()


@click.group()
@click.version_option(package_name="spanredact")
def main() -> None:
    """SpanRedact — inspect redacted GenAI traces in Jaeger."""


# ---------- diff ----------------------------------------------------------


@main.command("diff")
@click.argument("trace_id")
@click.option("--jaeger", default=DEFAULT_JAEGER_QUERY, show_default=True, help="Jaeger query URL.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "raw"]),
    default="table",
    show_default=True,
)
def cmd_diff(trace_id: str, jaeger: str, fmt: str) -> None:
    """Show the redaction state of one Jaeger trace.

    Renders, per span: name, the parsed JSON of `gen_ai.input/output.messages`
    (so the [REDACTED] markers are visible inside the messages structure), the
    matched pattern names, and the SpanRedact policy that was applied.
    """
    try:
        spans = fetch_trace(trace_id, base=jaeger)
    except JaegerError as exc:
        raise click.ClickException(str(exc)) from exc

    summaries = [_summarize_span(s) for s in spans]

    if fmt == "raw":
        console.print_json(data=spans)
        return
    if fmt == "json":
        console.print_json(data=summaries)
        return

    # table (default)
    for s in summaries:
        _render_summary(s)


# ---------- report --------------------------------------------------------


@main.command("report")
@click.option("--service", required=True, help="OTel service.name to aggregate over.")
@click.option("--limit", default=20, show_default=True, help="Max traces to look at.")
@click.option("--jaeger", default=DEFAULT_JAEGER_QUERY, show_default=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def cmd_report(service: str, limit: int, jaeger: str, fmt: str) -> None:
    """Aggregate redaction stats across recent traces of a service."""
    try:
        traces = fetch_recent_traces(service, limit=limit, base=jaeger)
    except JaegerError as exc:
        raise click.ClickException(str(exc)) from exc

    total_spans = 0
    redacted_spans = 0
    policy_counter: Counter[str] = Counter()
    pattern_counter: Counter[str] = Counter()

    for tr in traces:
        for sp in tr.get("spans", []):
            total_spans += 1
            tags = tags_to_dict(sp)
            if tags.get("spanredact.redaction.applied") is True:
                redacted_spans += 1
                policy = str(tags.get("spanredact.redaction.policy") or "?")
                policy_counter[policy] += 1
                matched = str(tags.get("spanredact.redaction.patterns_matched") or "")
                for name in filter(None, matched.split(",")):
                    pattern_counter[name] += 1

    report = {
        "service": service,
        "traces_examined": len(traces),
        "total_spans": total_spans,
        "spans_with_redaction": redacted_spans,
        "by_policy": dict(policy_counter),
        "by_pattern": dict(pattern_counter),
    }

    if fmt == "json":
        console.print_json(data=report)
        return

    console.rule(f"[bold]SpanRedact report — service={service}[/bold]")
    console.print(
        f"traces examined: {report['traces_examined']}    "
        f"spans: {report['total_spans']}    "
        f"with redaction: [bold]{report['spans_with_redaction']}[/bold]"
    )
    if policy_counter:
        t = Table(title="By policy", show_header=True)
        t.add_column("policy")
        t.add_column("spans", justify="right")
        for k, v in policy_counter.most_common():
            t.add_row(k, str(v))
        console.print(t)
    if pattern_counter:
        t = Table(title="By pattern matched", show_header=True)
        t.add_column("pattern")
        t.add_column("hits", justify="right")
        for k, v in pattern_counter.most_common():
            t.add_row(k, str(v))
        console.print(t)


# ---------- helpers -------------------------------------------------------


def _summarize_span(span: dict) -> dict:
    tags = tags_to_dict(span)
    out: dict = {
        "span": span.get("operationName"),
        "span_id": span.get("spanID"),
        "redacted": tags.get("spanredact.redaction.applied") is True,
        "policy": tags.get("spanredact.redaction.policy"),
        "patterns_matched": _split_csv(tags.get("spanredact.redaction.patterns_matched")),
        "content": {},
        "metadata": {},
    }
    for k in CONTENT_KEYS:
        if k in tags:
            out["content"][k] = _maybe_parse_json(tags[k])
    for k, v in tags.items():
        if (
            k.startswith("gen_ai.")
            and k not in CONTENT_KEYS
        ) or k.startswith("spanredact."):
            out["metadata"][k] = v
    return out


def _render_summary(s: dict) -> None:
    head = (
        f"[bold]{s['span']}[/bold]  ({s['span_id']})  "
        f"redacted=[{'green' if s['redacted'] else 'yellow'}]{s['redacted']}[/]"
    )
    console.rule(head, style="dim")
    if s["redacted"]:
        console.print(
            f"  policy: [cyan]{s['policy']}[/cyan]    "
            f"patterns_matched: [magenta]{', '.join(s['patterns_matched']) or '-'}[/magenta]"
        )
    if s["content"]:
        console.print("[bold]content (after redaction)[/bold]")
        for k, v in s["content"].items():
            console.print(f"  [dim]{k}:[/dim]")
            console.print_json(data=v, indent=2)
    if s["metadata"]:
        console.print("[bold]metadata[/bold]")
        for k, v in s["metadata"].items():
            if k.startswith("spanredact."):
                continue  # already shown above
            console.print(f"  {k} = {v}")


def _maybe_parse_json(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _split_csv(value: object) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return [v for v in value.split(",") if v]


if __name__ == "__main__":
    main()
