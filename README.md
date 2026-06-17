# SpanRedact

**A privacy-first observability layer for OpenLLMetry / OpenTelemetry GenAI traces.**

OpenLLMetry captures full prompt and completion content as span attributes by
default. Its only toggle is `TRACELOOP_TRACE_CONTENT=true|false` — binary. For
teams in regulated industries (fintech, healthtech, legaltech), that means a
choice between "leak user PII into the tracing backend" and "lose the debug
value of LLM observability." Neither is acceptable.

SpanRedact sits between OpenLLMetry and your OTLP exporter. It rewrites
PII out of span content **before any data leaves the process**, keeps the
non-PII metadata your operators actually need, and stamps each touched span
with an audit trail so compliance can verify what was redacted.

> **Status: v0.1 core works locally** — `pip install -e .`, real Claude calls
> through OpenLLMetry land in Jaeger with planted PII replaced by
> `[REDACTED]`. The `spanredact` CLI (`diff` / `report`) and a self-validation
> benchmark are included; not on PyPI yet, and formal launch (PyPI publish,
> demo video) is deferred. See [docs/ROADMAP.md](docs/ROADMAP.md) for the
> remaining deferred items.

---

## What it does today

- **PII redaction** on the GenAI content attributes (`gen_ai.input.messages`,
  `gen_ai.output.messages`, plus legacy `gen_ai.prompt` / `gen_ai.completion`)
  before they leave your process. Six default patterns (email, US SSN, US
  phone, credit card, API keys, JWT); custom patterns via `add_pattern()`.
- **JSON-aware redaction.** Real GenAI content is JSON (`messages[].parts[].content`);
  SpanRedact parses the JSON, redacts only string leaves, and re-serializes —
  structure (`role`, `type`) and non-PII metadata stay intact.
- **Three policy modes** controlling content capture:
  - `strict` — drop content attributes entirely (keep model / token counts).
  - `balanced` — redact PII inside content (default).
  - `debug` — passthrough, no redaction (local dev only).
- **Audit attributes.** Every modified span carries
  `spanredact.redaction.applied`, `.policy`, and `.patterns_matched`
  so compliance can query "what got redacted, by which policy."
- **One-line integration.** Pass `SpanRedactExporter` to
  `Traceloop.init(exporter=...)` — the rest of your OpenLLMetry / OTel setup
  is unchanged.
- **CLI for inspection.** `spanredact diff <trace_id>` renders the redaction
  state of one Jaeger trace (parsed content with `[REDACTED]` markers, matched
  patterns, policy); `spanredact report --service <name>` aggregates audit
  stats (spans redacted, by policy, by pattern) across recent traces.

---

## Architecture (1 paragraph)

OpenTelemetry's `SpanProcessor.on_end()` receives a read-only `ReadableSpan`
([spec](https://opentelemetry.io/docs/specs/otel/trace/sdk/),
[issue #2990](https://github.com/open-telemetry/opentelemetry-specification/issues/2990)),
so a span processor cannot mutate attributes after the span ends. SpanRedact
is instead a **`SpanExporter` wrapper**: it intercepts `export(spans)`,
builds new `ReadableSpan` instances with sanitized attributes via the public
constructor, and forwards them to the wrapped (downstream) exporter. Rationale
and a tested spike are recorded in
[ADR-001](docs/DECISIONS.md#adr-001-implement-redaction-as-a-spanexporter-wrapper-not-a-spanprocessor).
The real GenAI attribute names and JSON shape used by current OpenLLMetry are
documented in
[ADR-002](docs/DECISIONS.md#adr-002-redaction-targets-gen_aiinputmessages--gen_aioutputmessages-which-are-json).

```
your code  ─►  OpenLLMetry  ─►  SpanRedactExporter  ─►  OTLP  ─►  Jaeger
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
git clone https://github.com/YuxiangJiangCT/SpanRedact.git
cd SpanRedact

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

# 5. open http://localhost:16686, service = spanredact-redaction-demo,
#    inspect gen_ai.input.messages — the planted email is now [REDACTED].

# clean up
docker compose -f examples/docker-compose.yml down
```

### Using it in your own code

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from traceloop.sdk import Traceloop

from spanredact.redaction.exporter import SpanRedactExporter
from spanredact.policy.modes import Policy

# Wrap your OTLP exporter once at startup. Everything else stays standard
# OpenLLMetry — your application code does not change.
otlp = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
Traceloop.init(
    app_name="my-llm-app",
    exporter=SpanRedactExporter(otlp, policy=Policy.BALANCED),
)

# ...now call the LLM provider as usual; spans are redacted before export.
```

Switching policies: `SPANREDACT_POLICY=strict|balanced|debug` env var, or
pass `Policy.STRICT` / `Policy.DEBUG` to `SpanRedactExporter`.

Adding a custom pattern:

```python
from spanredact import add_pattern
add_pattern("internal_id", r"INT-\d{6}")
```

---

## What's verified

- **End-to-end on real Claude.** Commit
  [db3c74c](https://github.com/YuxiangJiangCT/SpanRedact/commits/main)
  shipped a demo that runs a real `client.messages.create()` through
  OpenLLMetry + `SpanRedactExporter` and confirmed via the Jaeger HTTP
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
OpenLLMetry with `SpanRedactExporter` (`policy=balanced`). Spans
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
guarantee for arbitrary PII formats. The patterns are regex, not ML.
`credit_card` matches 13–16 digit runs but only redacts those that pass a
Luhn checksum, so most random numbers are left alone. `us_phone`, by
contrast, matches any 10-digit sequence (favoring recall), so unrelated
values (order IDs, Unix timestamps, long numeric tokens) can still be
over-redacted. That is the intended privacy-first failure mode — over-redact
rather than leak — but it means redaction can touch non-PII. See
[docs/PRD.md](docs/PRD.md) §3.2 NG4 for what SpanRedact does *not* claim to
catch. Expand `benchmark/tasks.py` and rerun to re-evaluate on your own data.

---

## What's deferred (not in v0.1 core)

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

SpanRedact is a thin layer; the heavy lifting is done by
[OpenLLMetry / Traceloop](https://github.com/traceloop/openllmetry) and
[OpenTelemetry](https://opentelemetry.io/). If SpanRedact's pattern of
"pre-export PII rewriting" eventually lands upstream as a first-class
feature, this project will redirect users there.

## License

Apache 2.0 — see [LICENSE](LICENSE).
