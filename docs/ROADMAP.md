# SpanRedact v0.1 Roadmap

> 8-week implementation plan, June 1 – July 27, 2026.
> Companion to the [design doc](PRD.md). Decisions made along the way land
> in `docs/DECISIONS.md` (added Week 2+).

---

## ⚠️ Architecture correction (vs PRD v0.2)

PRD §6 originally describes SpanRedact as an **OTel `SpanProcessor`**.
Pre-implementation research shows this is not viable for the current
OpenTelemetry Python SDK path: `SpanProcessor.on_end()` receives a
`ReadableSpan`, and the OTel specification states that "even if the passed
Span may be technically writable, since it's already ended at this point,
modifying it is not allowed."

- Evidence: [opentelemetry-specification#2990](https://github.com/open-telemetry/opentelemetry-specification/issues/2990) (closed; spec confirms the limitation),
  [opentelemetry-python#4424](https://github.com/open-telemetry/opentelemetry-python/issues/4424) (open; community asks for hooks before conversion into `ReadableSpan`)
- The spec also defines an `OnEnding` callback during which the Span is
  still mutable, but `OnEnding` is currently in **Development** status and
  is not a stable foundation for v0.1.

**Revised approach**: SpanRedact v0.1 implements redaction as a
**`SpanExporter` wrapper**. It wraps the user's OTLP exporter, intercepts
`export(spans)`, builds sanitized span payloads (or sanitized
`ReadableSpan`-compatible snapshots) before forwarding only the redacted
data to the wrapped exporter. The Week 2 architecture spike will validate
the safest implementation path — whether sanitized snapshots can be
constructed safely, or whether redaction should happen during OTLP
serialization instead.

The user-facing API (`from spanredact import init`) is unchanged. PRD §6
diagrams and prose will be updated after the Week 2 spike.

**Second correction**: prompt/completion content should be treated as known
GenAI content-carrying fields. Current OTel GenAI semantic conventions
include `gen_ai.input.messages` and `gen_ai.output.messages`; older
instrumentations may still emit deprecated `gen_ai.prompt` /
`gen_ai.completion`. Per the GenAI events spec, instrumentations **MAY also
capture user inputs and responses as events** (e.g., the
`gen_ai.client.inference.operation.details` event with the same
`gen_ai.input.messages` / `gen_ai.output.messages` attributes). Redaction
must therefore target these known content-carrying keys wherever they
appear — span attributes first, and event attributes when the
instrumentation records content via GenAI events — and should not blindly
rewrite arbitrary events without matching known keys/patterns.

**Third correction**: Jaeger v1 reached EOL on 2025-12-31. Jaeger v2 is the
current major line and v2 container images are published on Docker Hub
(`jaegertracing/jaeger:2.x`). v0.1's `examples/docker-compose.yml` still
pins `jaegertracing/all-in-one:1.76.0` with `COLLECTOR_OTLP_ENABLED=true`
exposing 4317 (OTLP gRPC), 4318 (OTLP HTTP), 16686 (UI), because the v1
all-in-one setup is a simpler, well-documented, known-good local demo.
**This pin is for local development only, not a production
recommendation.**

---

## Timeline overview

| Week | Calendar | Focus | Headline deliverable |
|------|---------|-------|---------------------|
| 1 | Jun 1 – Jun 7 | Onboarding + Hello World | docker-compose Jaeger + hello_anthropic.py emitting gen_ai spans |
| 2 | Jun 8 – Jun 14 | Architecture spike + project scaffolding | DECISIONS.md ADR; `pip install -e .` works; redaction spike demo |
| 3 | Jun 15 – Jun 21 | Core PII redaction (regex patterns + Exporter wrapper) | 15+ passing tests; planted PII redacted end-to-end in Jaeger |
| 4 | Jun 22 – Jun 28 | Policy modes + `init()` API | `SPANREDACT_POLICY=strict\|balanced\|debug` works; **v0.1-alpha milestone** |
| 5 | Jun 29 – Jul 5 | `spanredact diff` CLI | `spanredact diff <trace_id>` shows before/after via Jaeger HTTP API |
| 6 | Jul 6 – Jul 12 | Audit metadata + `spanredact report` | Per-span `spanredact.redaction.*` attrs; aggregated report subcommand |
| 7 | Jul 13 – Jul 19 | Self-validation benchmark + polish | Validation table in README with concrete recall/precision numbers |
| 8 | Jul 20 – Jul 26 | Launch | PyPI 0.1.0 published; README + demo video + blog + Show HN |

Hard rule (per PRD §7.4): if a week falls behind, cut Week 7 benchmark
before extending Week 8.

---

## Week 1 (Jun 1 – Jun 7): Onboarding + Hello World

| Day | Task | Acceptance |
|-----|------|-----------|
| Mon | OTel concepts deep-dive: video + 1-page notes | Notes explain Trace / Span / Attribute / Event / SpanProcessor vs SpanExporter / OTLP |
| Tue | Hello World #1 — plain OTel + Jaeger via Docker | Jaeger UI (port 16686) shows a manually-created trace |
| Wed | Hello World #2 — OpenLLMetry + Anthropic | `Traceloop.init()` + `client.messages.create()` produces a `gen_ai.*` span in Jaeger |
| Thu | Build `examples/docker-compose.yml` + `examples/hello_anthropic.py` | `docker compose up -d && python examples/hello_anthropic.py` is a one-command demo |
| Fri | Read OpenLLMetry Anthropic instrumentor source | Notes record: which attribute key holds the prompt, when it's set, whether it's opt-in |
| Sat | Lurk in Traceloop Slack + CNCF #opentelemetry-genai-wg; skim OpenLLMetry open issues (especially #3683, #1042) | Know what the community is currently debating |
| Sun | Synthesize Week 1 learning notes | One-page markdown ready to recycle into the launch blog post |

**Week 1 Definition of Done**:
- [ ] `docker compose up` brings Jaeger up
- [ ] hello_anthropic.py runs; Jaeger shows the full gen_ai trace
- [ ] Can explain (verbally) why `SpanProcessor.on_end()` is read-only — this
      sets up the Week 2 architecture decision

---

## Week 2 (Jun 8 – Jun 14): Architecture spike + project scaffolding

Two parallel threads.

### Thread A — Architecture spike (highest priority)

**Question to settle**: can a `SpanExporter` wrapper actually rewrite span
attributes before forwarding to the underlying OTLP exporter?

1. Write a minimal demo: a custom `SpanExporter` that wraps
   `OTLPSpanExporter`, in `export(spans)` copies each `ReadableSpan`,
   mutates a known attribute, and forwards to the wrapped exporter.
2. If `ReadableSpan` cannot be reconstructed (private constructor), evaluate
   fallbacks:
   - Plan B: insert a custom span-buffering processor upstream of
     `BatchSpanProcessor` that holds mutable copies.
   - Plan C: fork OTLP exporter serialization (avoided unless A and B fail).
3. Record the decision in `docs/DECISIONS.md` as an ADR.

**Acceptance**: planted email `leak@test.com` in a hello_anthropic prompt
appears as `[REDACTED]` in Jaeger.

### Thread B — Project scaffolding

1. `pyproject.toml` (PEP 621, hatchling or setuptools backend)
2. `src/spanredact/__init__.py` with version string
3. `tests/` directory with one placeholder test
4. `ruff.toml` (lint + format)
5. `.github/workflows/ci.yml`: pytest + ruff on Python 3.11 and 3.12
6. `CONTRIBUTING.md` (stub)
7. `SECURITY.md` (responsible disclosure path — committed to in PRD §8)

**Week 2 Definition of Done**:
- [ ] DECISIONS.md records the chosen architecture (SpanExporter wrapper or
      fallback)
- [ ] `pip install -e .` succeeds
- [ ] GH Actions runs the placeholder test
- [ ] Redaction spike demo shows `[REDACTED]` locally

---

## Week 3 (Jun 15 – Jun 21): Core PII redaction

Goal: turn the Week 2 spike into library code.

1. `src/spanredact/redaction/patterns.py`: six default regexes
   (email, US SSN, US phone, credit card, API key prefixes, JWT). Compile
   at module load. Each pattern has ≥3 positive and ≥3 negative test cases.
2. `src/spanredact/redaction/exporter.py`: `SpanRedactExporter` wrapper
   - `__init__(self, wrapped_exporter, patterns)`
   - `export(self, spans)`: redact known PII-prone attributes
     (`gen_ai.input.messages`, `gen_ai.output.messages`, plus legacy keys),
     then delegate to `wrapped_exporter.export()`
3. `src/spanredact/redaction/audit.py`: track `patterns_matched`,
   `redacted_count`
4. Test coverage: every pattern in isolation + one end-to-end span test

**Definition of Done**:
- [ ] `pytest tests/redaction/` passes ≥ 15 tests
- [ ] hello_anthropic.py with planted PII shows `[REDACTED]` in Jaeger
- [ ] Per-span redaction overhead < 1 ms p50 (measured with `timeit`)

---

## Week 4 (Jun 22 – Jun 28): Policy modes + init API

1. `src/spanredact/policy/modes.py`: three modes (strict / balanced / debug)
   as an enum + per-mode policy table
2. `src/spanredact/policy/engine.py`: for each attribute, decide drop /
   redact / passthrough based on policy
3. `src/spanredact/init.py`: `init(policy="balanced")` entry point
   - Calls `Traceloop.init()` internally
   - Registers the SpanRedact exporter on the tracer provider
   - Reads `SPANREDACT_POLICY` env var
4. `src/spanredact/attach.py`: escape hatch for users who already initialized
   OpenLLMetry themselves
5. Integration tests covering all three modes

**Definition of Done**:
- [ ] All three policy modes are visually distinguishable in Jaeger
- [ ] `SPANREDACT_POLICY=strict python examples/hello_anthropic.py` works
- [ ] **🚀 v0.1-alpha milestone**: project is technically launchable from
      this point forward

---

## Week 5 (Jun 29 – Jul 5): Diff CLI v0

1. `src/spanredact/cli/main.py`: a `click` application with subcommands
   (`diff`, `report`, `validate`)
2. `src/spanredact/cli/diff.py`: `spanredact diff <trace_id>`
   - Queries the Jaeger HTTP API at
     `http://localhost:16686/api/traces/<id>`
   - Shows before/after attributes per span
   - `--format=table` (default, via `rich`) or `--format=json`
3. Handle errors: missing trace, Jaeger unreachable, malformed ID

**Definition of Done**:
- [ ] `spanredact diff <real_id>` produces readable diff output
- [ ] ≥ 5 CLI tests (including error cases)

---

## Week 6 (Jul 6 – Jul 12): Audit metadata + report subcommand

1. Exporter writes `spanredact.redaction.applied=true`,
   `spanredact.redaction.policy`, and
   `spanredact.redaction.patterns_matched` on every modified span
2. `spanredact report --since=1h`: aggregated stats by policy and pattern
3. `docs/AUDIT.md`: how compliance teams use these attributes for queries

**Definition of Done**:
- [ ] Jaeger UI can filter spans by `spanredact.redaction.applied`
- [ ] `spanredact report` outputs ≥ 3 aggregated columns

---

## Week 7 (Jul 13 – Jul 19): Self-validation benchmark

Goal: deliver on PRD §3.1 G4.

1. `benchmark/tasks.py`: 5-8 tasks, each a prompt with planted PII and an
   expected redacted output
2. `benchmark/run.py`: run all tasks, measure
   - Recall = caught_pii / total_planted_pii
   - Precision = correct_redactions / total_redactions
   - Trace completeness = valid_spans / total_spans
3. `benchmark/report.py`: emit a markdown table for the README
4. Reserve half the week for bug fixes and missing tests

**Definition of Done**:
- [ ] README "Validation Results" section contains real numbers
- [ ] Total test coverage ≥ 60%

---

## Week 8 (Jul 20 – Jul 26): Launch

**Hard rule (PRD §7.4 #4)**: no new features this week, only release work.

| Day | Task |
|-----|------|
| Mon | README final pass (quickstart, architecture diagram, validation table, comparison vs OpenLLMetry) |
| Tue | Record 5-7 minute demo video (screen recording + subtitles) |
| Wed | Draft launch blog post "Why I built SpanRedact" |
| Thu | TestPyPI dry-run → publish `spanredact==0.1.0` to PyPI |
| Fri | Prepare launch posts: Show HN, Twitter thread, Slack messages (Traceloop, CNCF #opentelemetry-genai-wg) |
| Sat | **🚀 Launch day** — Show HN + Twitter + Slack |
| Sun | Monitor HN comments, GitHub issues, Twitter replies — respond within 48 hours |

**Launch Definition of Done** (against PRD §9 metrics):
- [ ] `pip install spanredact` works from PyPI
- [ ] README renders fully on GitHub, includes demo gif
- [ ] Show HN post is live (front page not required, posting is)

---

## Per-week rituals

Every Sunday, 30 minutes:
- Self-review of the week's code
- Update `docs/DECISIONS.md` with new ADRs
- Revisit [open questions Q1-Q10](PRD.md#10-open-questions-log); update
  status for any touched this week
- Commit cadence: at least 2 pushes per week, no more than 3 days of
  unpushed work

---

## Risk monitoring (extends PRD §8)

| Risk | When checked | Trigger | Response |
|------|-------------|---------|---------|
| SpanExporter wrapper path infeasible (ReadableSpan cannot be reconstructed) | Week 2 Day 1-2 spike | Spike fails | Switch to Plan B (custom span-buffering processor) |
| Jaeger 1.x EOL leaves CVEs in the demo image | Any time | `docker scan` flags critical | Switch demo to SigNoz or Tempo |
| OpenLLMetry v0.61+ breaks compatibility | Week 4 onward | New OpenLLMetry release fails our test suite | Pin version range in `pyproject.toml`, file an issue |
| Week 5 slip squeezes Week 7 benchmark | End of Week 5 | Diff CLI incomplete | Cut benchmark to 3 data points, ship anyway |

---

## End-to-end verification (Week 8 final pass)

Run this checklist on Jul 24 before posting:

1. `pip install spanredact` from PyPI succeeds
2. Following only the README quickstart, a fresh machine sees a redacted
   trace in Jaeger within 5 minutes
3. `spanredact diff <trace_id>` returns a readable diff
4. `spanredact report --since=1h` produces a sane aggregated table
5. Switching between the three policy modes is visibly different in Jaeger
6. README benchmark numbers are reproducible by re-running
   `benchmark/run.py`
7. One external person (classmate, mentor) completes the README quickstart
   in under 5 minutes
