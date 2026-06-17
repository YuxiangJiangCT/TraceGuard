"""Render benchmark results as a markdown table for README injection.

Reads JSON on stdin (from `python -m benchmark.run`), writes markdown to
stdout. Usage:
    python -m benchmark.run > /tmp/bench.json
    python -m benchmark.report < /tmp/bench.json
"""

from __future__ import annotations

import json
import sys


def render(summary: dict) -> str:
    rows = []
    rows.append(
        "| task | planted | caught | recall | precision | completeness | "
        "matched patterns |"
    )
    rows.append("|---|---:|---:|---:|---:|---:|---|")
    for t in summary["tasks"]:
        rows.append(
            f"| `{t['task']}` | {t['planted_pii_count']} | {t['caught_pii_count']} "
            f"| {t['recall']:.2f} | {t['precision']:.2f} | {t['completeness']:.2f} "
            f"| {', '.join(t['matched_patterns']) or '—'} |"
        )
    rows.append("")
    rows.append(
        f"Macro averages: **recall {summary['macro_recall']:.2f}**, "
        f"**precision {summary['macro_precision']:.2f}**, "
        f"**completeness {summary['macro_completeness']:.2f}** "
        f"(3 tasks, Claude `claude-haiku-4-5-20251001` via OpenLLMetry, "
        f"SpanRedact policy=balanced)."
    )
    return "\n".join(rows)


def main() -> None:
    summary = json.load(sys.stdin)
    print(render(summary))


if __name__ == "__main__":
    main()
