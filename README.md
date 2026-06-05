# TraceGuard

**A privacy-first observability layer for OpenLLMetry / OpenTelemetry GenAI traces.**

OpenLLMetry captures full prompt and completion content as span attributes by
default. Its only toggle is `TRACELOOP_TRACE_CONTENT=true|false` — binary. For
teams in regulated industries (fintech, healthtech, legaltech), that means a
choice between "leak user PII into the tracing backend" and "lose the debug
value of LLM observability." Neither is acceptable.

TraceGuard sits between OpenLLMetry and your OTLP exporter. It rewrites
PII out of span content **before any data leaves the process**, keeps the
non-PII metadata your operators actually need, and stamps each touched span
with an audit trail so compliance can verify what was redacted.

> **Status: v0.1 core works locally** — `pip install -e .`, real Claude calls
> through OpenLLMetry land in Jaeger with planted PII replaced by
> `[REDACTED]`. Not on PyPI yet; CLI / benchmark / formal launch deferred.
> See [docs/ROADMAP.md](docs/ROADMAP.md) for the deferred items.

---

## What it does today

- **PII redaction** on the GenAI content attributes (`gen_ai.input.messages`,
  `gen_ai.output.messages`, plus legacy `gen_ai.prompt` / `gen_ai.completion`)
  before they leave your process. Six default patterns (email, US SSN, US
  phone, credit card, API keys, JWT); custom patterns via `add_pattern()`.
- **JSON-aware redaction.** Real GenAI content is JSON (`messages[].parts[].content`);
  TraceGuard parses the JSON, redacts only string leaves, and re-serializes —
  structure (`role`, `type`) and non-PII metadata stay intact.
- **Three policy modes** controlling content capture:
  - `strict` — drop content attributes entirely (keep model / token counts).
  - `balanced` — redact PII inside content (default).
  - `debug` — passthrough, no redaction (local dev only).
- **Audit attributes.** Every modified span carries
  `traceguard.redaction.applied`, `.policy`, and `.patterns_matched`
  so compliance can query "what got redacted, by which policy."
- **One-line integration.** Pass `TraceGuardSpanExporter` to
  `Traceloop.init(exporter=...)` — the rest of your OpenLLMetry / OTel setup
  is unchanged.

---

## Architecture (1 paragraph)

OpenTelemetry's `SpanProcessor.on_end()` receives a read-only `ReadableSpan`
([spec](https://opentelemetry.io/docs/specs/otel/trace/sdk/),
[issue #2990](https://github.com/open-telemetry/opentelemetry-specification/issues/2990)),
so a span processor cannot mutate attributes after the span ends. TraceGuard
is instead a **`SpanExporter` wrapper**: it intercepts `export(spans)`,
builds new `ReadableSpan` instances with sanitized attributes via the public
constructor, and forwards them to the wrapped (downstream) exporter. Rationale
and a tested spike are recorded in
[ADR-001](docs/DECISIONS.md#adr-001-implement-redaction-as-a-spanexporter-wrapper-not-a-spanprocessor).
The real GenAI attribute names and JSON shape used by current OpenLLMetry are
documented in
[ADR-002](docs/DECISIONS.md#adr-002-redaction-targets-gen_aiinputmessages--gen_aioutputmessages-which-are-json).

```
your code  ─►  OpenLLMetry  ─►  TraceGuardSpanExporter  ─►  OTLP  ─►  Jaeger
                                  │
                                  ├─ parses JSON in gen_ai.input/output.messages
                                  ├─ runs PII regexes on string leaves only
                                  ├─ rebuilds the ReadableSpan with sanitized attrs
                                  └─ stamps audit attributes (applied/policy/matched)
```

---

## Quickstart (5 min, local)

Requires Python 3.10+ and Docker (for the Jaeger demo).

```bash
git clone https://github.com/YuxiangJiangCT/TraceGuard.git
cd TraceGuard

# 1. venv + install (editable, with the examples extras)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,examples]"

# 2. config: copy the env template and put your real Anthropic key in .env
cp .env.example .env
# edit .env -> set ANTHROPIC_API_KEY=sk-ant-...

# 3. start Jaeger (Jaeger UI on http://localhost:16686)
docker compose -f examples/docker-compose.yml up -d

# 4. run the end-to-end demo: a real Claude call whose prompt contains a
#    planted email. The span lands in Jaeger with the email REDACTED.
python examples/redaction_demo.py

# 5. open http://localhost:16686, service = traceguard-redaction-demo,
#    inspect gen_ai.input.messages — the planted email is now [REDACTED].

# clean up
docker compose -f examples/docker-compose.yml down
```

### Using it in your own code

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from traceloop.sdk import Traceloop

from traceguard.redaction.exporter import TraceGuardSpanExporter
from traceguard.policy.modes import Policy

# Wrap your OTLP exporter once at startup. Everything else stays standard
# OpenLLMetry — your application code does not change.
otlp = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
Traceloop.init(
    app_name="my-llm-app",
    exporter=TraceGuardSpanExporter(otlp, policy=Policy.BALANCED),
)

# ...now call the LLM provider as usual; spans are redacted before export.
```

Switching policies: `TRACEGUARD_POLICY=strict|balanced|debug` env var, or
pass `Policy.STRICT` / `Policy.DEBUG` to `TraceGuardSpanExporter`.

Adding a custom pattern:

```python
from traceguard import add_pattern
add_pattern("internal_id", r"INT-\d{6}")
```

---

## What's verified

- **End-to-end on real Claude.** Commit
  [db3c74c](https://github.com/YuxiangJiangCT/TraceGuard/commits/main)
  shipped a demo that runs a real `client.messages.create()` through
  OpenLLMetry + `TraceGuardSpanExporter` and confirmed via the Jaeger HTTP
  API that a planted `leak@example.com` is **absent** from
  `gen_ai.input.messages` while `[REDACTED]` is present and
  `gen_ai.usage.input_tokens` / `gen_ai.request.model` survive unchanged.
- **24 unit tests pass** (`pytest`), **`ruff check` clean**, **CI green**
  on Python 3.10 / 3.11 / 3.12. Test split: per-pattern positives/negatives,
  JSON-aware redactor (the ADR-002 shape), three-policy behavior through
  an in-memory exporter, CLI commands against a mocked Jaeger.

---

## Validation results

3 tasks, each sent to Claude (`claude-haiku-4-5-20251001`) through
OpenLLMetry with `TraceGuardSpanExporter` (`policy=balanced`). Spans
inspected via the Jaeger HTTP API; "caught" = the planted string is not
present in the post-export span content. Reproduce with
`python -m benchmark.run | python -m benchmark.report`.

| task | planted | caught | recall | precision | completeness | matched patterns |
|---|---:|---:|---:|---:|---:|---|
| `email_only` | 1 | 1 | 1.00 | 1.00 | 1.00 | email |
| `mixed_pii` | 4 | 4 | 1.00 | 1.00 | 1.00 | api_key, email, us_phone, us_ssn |
| `no_pii_control` | 0 | 0 | 1.00 | 1.00 | 1.00 | — |

Macro averages: **recall 1.00**, **precision 1.00**, **completeness 1.00**.

These numbers reflect *this small, well-defined task set* — they are NOT a
guarantee for arbitrary PII formats. Regex coverage is intentionally
conservative; see [docs/PRD.md](docs/PRD.md) §3.2 NG4 for what TraceGuard
does *not* claim to catch. Expand `benchmark/tasks.py` and rerun to
re-evaluate on your own data.

---

## What's deferred (not in v0.1 core)

- `traceguard diff <trace_id>` and `traceguard report` CLI subcommands
  (ROADMAP Weeks 5–6).
- Self-validation benchmark with recall/precision numbers (ROADMAP Week 7).
- PyPI publish, demo video, Show HN (ROADMAP Week 8).
- ML-based PII detection (Presidio integration), non-Anthropic providers,
  streaming response coverage, A2A trace context propagation.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full deferred list and
[docs/PRD.md](docs/PRD.md) for the design rationale.

---

## Documentation

- [docs/PRD.md](docs/PRD.md) — design doc, competitive analysis,
  open questions, invalidation scenarios.
- [docs/ROADMAP.md](docs/ROADMAP.md) — 8-week v0.1 implementation plan
  and what's deferred.
- [docs/DECISIONS.md](docs/DECISIONS.md) — ADRs with the evidence behind
  each architectural choice.

---

## Credits

TraceGuard is a thin layer; the heavy lifting is done by
[OpenLLMetry / Traceloop](https://github.com/traceloop/openllmetry) and
[OpenTelemetry](https://opentelemetry.io/). If TraceGuard's pattern of
"pre-export PII rewriting" eventually lands upstream as a first-class
feature, this project will redirect users there.

## License

Apache 2.0 — see [LICENSE](LICENSE).
