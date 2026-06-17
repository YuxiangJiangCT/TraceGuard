# SpanRedact — Project Requirements & Technical Design Doc

**SpanRedact: A Privacy-First Layer for OpenTelemetry-Based AI Agent Traces**

> Status: **Draft v0.2** (revised after 3-round AI cross-review)
> Created: 2026-05-24
> Last updated: 2026-05-26
> Previous name: `otel-genai` (deprecated — see §12 Decision Log)

---

## 0. How to read this doc

This PRD went through 3 rounds of AI cross-review (2 independent reviewers
flagged the same directional concerns; a 3rd corrected specific
over-claims). **Writing principles: honesty > polish, citation > inference,
narrow > broad.**

Three intended uses:
1. **Before coding** — the "we've thought it through" version
2. **During development** — when stuck, come back and check; don't relitigate
   decisions already made
3. **As OSS deliverable material** — at launch, sections become README / RFC
   / SOP content

---

## 1. Executive Summary

**SpanRedact** is a **privacy-first observability layer** that sits on top of
[OpenLLMetry](https://github.com/traceloop/openllmetry) (a leading OSS
GenAI instrumentation toolkit, 7.1k stars, YC-backed). It does **not**
re-implement instrumentation — instead, it ships:

1. **PII redaction processor** for prompts, completions, and tool call
   arguments before they reach any OTel exporter
2. **Policy modes** (`strict` / `balanced` / `debug`) controlling what
   content is captured
3. **Before/after trace diff CLI** for auditing redaction effectiveness
4. **Minimal self-validation benchmark** (v0.1) → cross-framework benchmark
   (v0.2)

**Why SpanRedact, not "another OpenLLMetry"**: OpenLLMetry has 7.1k stars,
40+ instrumentations, 257 releases, and contributed its semantic conventions
to upstream OpenTelemetry. Competing head-on as a "vendor-neutral
instrumentation toolkit" is not viable in 8 weeks solo. But **OpenLLMetry's
default behavior captures full prompt/completion content in spans** — which
is exactly what regulated industries (fintech, healthtech, legal-tech)
**cannot ship to production**. SpanRedact fills this specific gap.

**Strategic positioning** (after Round-3 review correction):
- OpenLLMetry is one of the most mature OTel-based GenAI instrumentation
  projects; its semantic convention work has been incorporated into the
  official OpenTelemetry GenAI semconv (currently at v1.41.0, Status:
  Development)
- SpanRedact treats OpenLLMetry as a dependency and adds the
  privacy/policy/audit layer that production deployments in regulated
  industries need

**Target outcomes (8 weeks)**:
- v0.1 launched on PyPI under Apache 2.0
- Live demo: OpenLLMetry + SpanRedact + Jaeger working with Anthropic
- README with redaction effectiveness validation
- 1+ PR proposed (or merged) to upstream OpenLLMetry (e.g., responding to
  open issues such as A2A propagation #3683 or cost metrics #1042)

---

## 2. Problem Statement

### 2.1 The user pain

You're building an AI agent application for a regulated industry. You want
LLM observability — trace each Claude/OpenAI call, see token costs, debug
agent decisions. You evaluate options:

**Option A — Roll your own logging**: tedious, no standardization.

**Option B — Vendor SaaS** (Langfuse Cloud / Helicone / LangSmith): prompt
data goes to their cloud. Compliance blocks it (HIPAA, PCI-DSS, GDPR, EU AI
Act, internal policies).

**Option C — Vendor SaaS, self-hosted** (Langfuse self-hosted, Phoenix
self-hosted): requires running Postgres + ClickHouse + web app. Compliance
audits the entire stack. Heavy.

**Option D — OpenLLMetry** (the OSS toolkit, 7.1k stars): your team installs
it, traces flow to your existing Jaeger / Datadog / Honeycomb. Compliance is
happy with the data locality.

**But there's a catch with Option D**: OpenLLMetry's default behavior is to
capture **full prompt and completion content** as span attributes. From
OpenLLMetry's own docs:

> "Traceloop automatically tracks the inputs and outputs of every prompt
> to LLMs. If you want to disable this behavior, you can set the
> `TRACELOOP_TRACE_CONTENT` env variable to `false`."

This is a **binary switch**: full content OR no content. There is no middle
ground for:
- Redacting PII (email, SSN, credit card, API keys) but keeping the rest
- Capturing structure (operation type, token usage) but not raw text
- Different policies for different environments (debug vs prod)
- Auditing what was redacted vs what made it through

For a regulated industry team, **binary content capture is unworkable**:
- Disabling content loses debug value
- Enabling content risks PII leakage into observability tools
- The team needs **selective redaction with audit trail**, not on/off

### 2.2 The opportunity

Build a **thin privacy layer above OpenLLMetry** that:
- Defaults to redacting common PII patterns
- Lets teams configure policy modes (strict/balanced/debug)
- Provides a CLI to verify "what's actually in my traces" (before/after diff)

This isn't competing with OpenLLMetry — it's making OpenLLMetry **safer to
turn on in production for regulated workloads**.

### 2.3 Why the timing works

- OpenLLMetry has reached production maturity (257 releases, latest 0.60.0
  on Apr 19, 2026)
- OTel GenAI semconv is at v1.41.0 (Status: Development; transition plan
  from v1.36-or-prior is documented)
- EU AI Act enforcement (2026) and Colorado AI Act (2026) explicitly require
  audit trails for AI systems — making "auditable observability with PII
  controls" a regulatory necessity, not a nice-to-have
- No dominant OSS project currently fills the "privacy layer on top of
  OpenLLMetry" niche

---

## 3. Goals & Non-Goals

### 3.1 Goals

**G1 — PII redaction is the default**
- Out-of-the-box patterns: email, US SSN, US phone, credit card,
  API keys (sk-/pk-/ghp-/gh*p-/AIza... prefixes), JWT tokens
- Configurable: add custom patterns via env or programmatic API
- Allowlist: explicitly mark some fields as "safe to capture"

**G2 — Policy modes for different environments**
- `strict`: only metadata (model name, token counts, latency), no content
- `balanced`: redacted content (default for production)
- `debug`: full content, no redaction (default for local dev, never
  recommended for prod)
- Switch via env var: `SPANREDACT_POLICY=balanced`

**G3 — Audit visibility (diff utility)**
- CLI: `spanredact diff <trace_id>` shows before/after redaction for a
  specific trace
- Useful for: validating redaction effectiveness, debugging "why is this
  field missing", compliance audits

**G4 — Minimum self-validation (v0.1 only)**
- A small benchmark that runs 5-8 representative agent tasks (different
  prompts containing planted PII), measures: redaction recall (did we catch
  all PII), redaction precision (did we over-redact useful content), trace
  completeness (did redaction break OTel semconv compliance)
- Output: a markdown table in README
- This is NOT cross-framework benchmark; that's v0.2

**G5 — Drop-in replacement for OpenLLMetry usage**
- User changes one import: `from spanredact import init` (instead of
  `from traceloop.sdk import Traceloop`)
- All other application code unchanged
- Behind the scenes: SpanRedact initializes OpenLLMetry + installs the
  redaction span processor

**G6 — Standards compliance**
- Emit OTel GenAI semconv-compliant spans (delegate to OpenLLMetry)
- Follow v1.36-or-prior compatibility with
  `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` opt-in for
  latest experimental conventions
- Compatible with any OTLP-compliant backend

### 3.2 Non-Goals (v0.x)

**NG1 — Not re-implementing instrumentation**
- We depend on OpenLLMetry's instrumentation for Anthropic, OpenAI,
  LangChain, etc. We don't fork or replace.

**NG2 — Not a hosted SaaS** (v0.x)
- 100% local Python library + your existing OTel backend

**NG3 — Not cross-framework benchmark in v0.1**
- v0.1 only does self-validation of SpanRedact's redaction
- Cross-framework comparison (OpenLLMetry vs OpenInference vs LangSmith
  native) is v0.2 work

**NG4 — Not ML-based PII detection** (v0.1)
- v0.1 uses regex patterns
- v0.2 adds optional Microsoft Presidio integration for ML detection

**NG5 — Not a billing / cost tool**
- We emit OTel token usage metrics (via OpenLLMetry)
- Cost analysis is downstream (Grafana dashboard / vendor product)

**NG6 — Not multi-language**
- Python only for v0.x. TypeScript / Go are out of scope until v1.0+

**NG7 — Not A2A trace propagation** (v0.1)
- This is a real gap (OpenLLMetry issue #3683 acknowledges it)
- v0.3+ candidate, not v0.1 commitment

### 3.3 Scope discipline rule

If a feature request doesn't fit G1-G6, it goes to a `FUTURE.md` file, not
v0.x. This is the anti-overthink guardrail. When tempted to add "just one
more cool thing", ask: does it strengthen one of G1-G6? If no, defer.

---

## 4. Users & Personas

### 4.1 Primary persona: Platform engineer at regulated mid-size SaaS

- **Title**: Senior / Staff Engineer or Platform Engineer
- **Company**: 300-5000 employees, regulated industry
  (fintech / healthtech / legaltech / govtech / B2B SaaS handling PII)
- **Pain**: Their team built an LLM feature. They want observability for
  agent debugging. They evaluated OpenLLMetry, liked it, but their security
  team flagged content capture as a blocker. They tried `TRACELOOP_TRACE_CONTENT=false`
  but lost too much debug value. They started looking for "redaction
  middleware for OpenLLMetry" — found nothing dominant in OSS.
- **What they want from SpanRedact**:
  - Drop-in install: change one import
  - Audit ability: prove to compliance that PII is being redacted
  - Their existing OpenLLMetry knowledge transfers
  - Apache 2.0 license (their legal team approves quickly)

### 4.2 Secondary persona: Founder/CTO of early-stage AI startup

- **Title**: CTO or founding engineer, 2-15 person team
- **Company**: Pre-series-A AI startup building agent products
- **Pain**: They're moving fast, integrated OpenLLMetry for visibility, but
  customer success calls reveal Slack screenshots of their team's traces
  contain customer emails / API keys. They don't have time to build
  redaction themselves.
- **What they want from SpanRedact**:
  - Quick install, sensible defaults
  - Low/zero overhead so it doesn't break their startup-quality codebase
  - Doesn't require buying yet another SaaS

### 4.3 Tertiary persona: OSS contributor / agent framework maintainer

- **Title**: Maintainer of an agent framework or related OSS project
- **Pain**: They want to recommend OpenLLMetry to their users but worry
  about the PII default behavior
- **What they want from SpanRedact**:
  - A reference for how a privacy layer should look
  - Ability to recommend "use OpenLLMetry + SpanRedact together"
  - Documentation that links the two

### 4.4 Anti-personas (we don't design for)

- Solo developers without PII concerns → use OpenLLMetry directly
- Enterprise procurement needing SSO/SOC2/ticketing → buy from Datadog or
  Langfuse Enterprise
- Teams wanting prompt engineering features (A/B testing, eval) →
  LangSmith / Braintrust / Phoenix

---

## 5. Competitive Landscape

### 5.1 Direct + Adjacent competitors

| Project | Approach | Stars (May 2026) | Relation to SpanRedact |
|---------|---------|-----------------|----------------------|
| **OpenLLMetry (Traceloop)** | OSS, OTel-based, ~40 instrumentations | **7.1k** | **Dependency**, not competitor. We build on top. |
| **OpenInference (Arize)** | OSS, multi-language OTel instrumentation, has per-field masking | (~3k+ est) | Adjacent. Has some redaction but no policy modes or audit CLI. |
| **Langfuse** | OSS + Cloud SaaS, full platform | (~8k+ est) | Heavier deployment. Compete on lightness, not features. |
| **Helicone** | SaaS proxy + observability | N/A (SaaS) | Different deployment model (proxy vs library). |
| **LangSmith** | LangChain-coupled SaaS | N/A (SaaS) | LangChain ecosystem coupling. |
| **Phoenix (Arize)** | OSS + Arize Cloud | (~3k+ est) | Eval-focused. Different use case. |
| **MLflow tracing** | Added LLM tracing recently | N/A (different scope) | Adjacent. ML-Ops origin. |
| **Braintrust** | SaaS for LLM eval + observability | N/A (SaaS) | Eval-focused, premium pricing. |

### 5.2 The honest assessment

**OpenLLMetry is the elephant in the room and we are NOT competing with it.**

OpenLLMetry is mature: 7.1k stars, 960 forks, 1385 commits, 257 releases.
YC-backed (Traceloop). Active maintenance. Their semantic convention work
has been incorporated into the official OpenTelemetry GenAI semconv (now at
v1.41.0).

**SpanRedact's bet**: There's a real gap between "OpenLLMetry's binary
content capture" and "what regulated industry teams actually need." This gap
shows up in OpenLLMetry's own GitHub issues (e.g., users asking for finer
control). The gap is real, narrow, and underserved.

**Differentiation argument (in order of strength)**:

1. **OpenLLMetry's content capture is binary; production needs nuance**.
   `TRACELOOP_TRACE_CONTENT=true|false` doesn't satisfy regulated industry
   compliance teams.

2. **No dominant OSS project for "redaction middleware for OpenLLMetry"**.
   OpenInference has some per-field masking but no policy modes or audit
   CLI. The niche is open.

3. **Drop-in install lowers adoption friction**. Change one import; if you
   already have OpenLLMetry, you can try SpanRedact in 5 minutes.

4. **Pure Apache 2.0, no telemetry, no cloud account**. Some teams' legal
   approval cycles are faster for tools that have zero external dependencies.

### 5.3 What if OpenLLMetry adds first-class redaction

**Scenario**: Traceloop ships configurable redaction in OpenLLMetry, making
SpanRedact redundant.

**Response**:
- If their implementation is good → **deprecate SpanRedact, redirect users
  to OpenLLMetry**. No ego protection.
- The existence of SpanRedact may have prompted Traceloop to act. That's
  a community contribution.

This is the correct mindset for infrastructure-tier OSS work.

### 5.4 Why SpanRedact's niche is defensible (for 6-18 months)

Three reasons:

1. **Regulated industry has slow adoption cycles** — even if Traceloop ships
   redaction, regulated teams take 6-12 months to evaluate + deploy. SpanRedact
   can be the bridge tool in the meantime.

2. **SpanRedact can be more opinionated** — Traceloop sells to all users
   including dev/test. They can't make `strict` the default. SpanRedact
   makes `balanced` the default explicitly because it's targeted at
   regulated use cases.

3. **Audit CLI is a category of its own** — `spanredact diff` isn't really
   about redaction config, it's about giving compliance teams a tool. This
   feature wouldn't naturally fit inside OpenLLMetry; it's a separate
   workflow.

---

## 6. Technical Architecture

### 6.1 High-level diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  User's Application Code                                          │
│                                                                    │
│   from spanredact import init                                      │
│   init(policy="balanced")  # ← Only change from OpenLLMetry usage │
│                                                                    │
│   # Rest of code is standard OpenLLMetry / OTel:                  │
│   from anthropic import Anthropic                                  │
│   client = Anthropic()                                             │
│   response = client.messages.create(...)                           │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  SpanRedact (this project)                                        │
│                                                                    │
│  init() does:                                                      │
│   1. Call OpenLLMetry's Traceloop.init()                           │
│   2. Register PII Span Processor on tracer provider                │
│   3. Apply policy mode (strict/balanced/debug)                     │
│                                                                    │
│   ┌──────────────────────────────────────┐                        │
│   │  PII Span Processor                  │                        │
│   │  (OTel SpanProcessor interface)      │                        │
│   │                                       │                        │
│   │  - intercepts each span before export│                        │
│   │  - applies redaction patterns        │                        │
│   │  - keeps audit metadata              │                        │
│   └────────────┬─────────────────────────┘                        │
│                │                                                    │
│   ┌────────────▼─────────────────────────┐                        │
│   │  Policy Engine                       │                        │
│   │  - strict: drop content              │                        │
│   │  - balanced: redact PII              │                        │
│   │  - debug: passthrough                │                        │
│   └────────────┬─────────────────────────┘                        │
└────────────────┼───────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenLLMetry (dependency, unmodified)                            │
│   - Anthropic / OpenAI / LangChain instrumentations               │
│   - Emits standard OTel GenAI spans                               │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenTelemetry SDK                                                │
│  (BatchSpanProcessor → OTLP Exporter → user's backend)            │
└───────────────────────────┬───────────────────────────────────────┘
                            │ OTLP
                            ▼
                ┌───────────────────────┐
                │ User's Backend:        │
                │ Jaeger / Datadog /     │
                │ Honeycomb / etc.       │
                └───────────────────────┘
```

**Key design choice**: SpanRedact is an **OTel SpanProcessor**, not a fork
of OpenLLMetry. SpanProcessor is the standard OTel extension point. This
means:
- Zero changes to OpenLLMetry code
- SpanRedact upgrades independently of OpenLLMetry releases
- If user already initialized OpenLLMetry, they can add SpanRedact
  separately (via API, not import)

### 6.2 Component breakdown

**Code structure**:
```
src/spanredact/
├── __init__.py
├── init.py               # init() entry point
├── policy/
│   ├── __init__.py
│   ├── modes.py          # strict / balanced / debug
│   └── engine.py         # apply policy to spans
├── redaction/
│   ├── __init__.py
│   ├── patterns.py       # default regex patterns
│   ├── processor.py      # OTel SpanProcessor implementation
│   └── audit.py          # what got redacted (for diff CLI)
├── cli/
│   ├── __init__.py
│   ├── main.py           # click-based CLI
│   └── diff.py           # diff command
└── benchmark/
    ├── __init__.py
    ├── tasks.py          # validation tasks
    └── report.py         # markdown report generator
```

### 6.3 API design

**Zero-config (most common)**:
```python
from spanredact import init
init()  # policy=balanced by default
```

**Explicit policy**:
```python
from spanredact import init
init(policy="strict")
```

**Add custom patterns**:
```python
from spanredact import init, add_pattern
init()
add_pattern("internal_id", r"INT-\d{6}")
```

**Programmatic init (already using OpenLLMetry directly)**:
```python
# User already has:
from traceloop.sdk import Traceloop
Traceloop.init()

# Add SpanRedact:
from spanredact import attach
attach(policy="balanced")
```

**Environment variables**:
```bash
SPANREDACT_POLICY=balanced              # strict | balanced | debug
SPANREDACT_PATTERNS=/path/to/patterns.json
SPANREDACT_AUDIT_LOG=/var/log/spanredact.log  # optional, what was redacted
```

### 6.4 Span hierarchy (delegated to OpenLLMetry)

We don't define span hierarchy — OpenLLMetry does. We just process whatever
OpenLLMetry emits, applying redaction before OTLP export.

Typical span hierarchy (from OpenLLMetry):
```
[gen_ai.chat (Anthropic)]
  attrs: gen_ai.system=anthropic, gen_ai.request.model=claude-opus-4-7,
         gen_ai.usage.input_tokens=150
  events: gen_ai.content.prompt=[REDACTED by SpanRedact:balanced]
          gen_ai.content.completion=[REDACTED by SpanRedact:balanced]
```

Note: SpanRedact adds an audit attribute to redacted spans:
- `spanredact.redaction.applied=true`
- `spanredact.redaction.policy=balanced`
- `spanredact.redaction.patterns_matched=[email, phone]`

This lets compliance teams query "show me all spans where redaction was
applied" or "show me all spans containing matched email patterns".

### 6.5 Performance budget

- **Overhead per span**: < 1ms p50, < 5ms p99 (redaction is regex over
  small strings)
- **Memory**: < 30MB at idle
- **No throughput impact**: redaction happens in BatchSpanProcessor's worker
  thread, doesn't block application code

These are tight because:
- Redaction is pure CPU work (no I/O)
- Patterns are pre-compiled
- Realistic OTel instrumentation is typically < 1ms p50

---

## 7. Milestones & Roadmap

### 7.1 v0.1 — 8 weeks total (June 1 – July 27, 2026)

Realistic timeline accounting for 8-12 hours/week.

**Weeks 1-2 (June 1-14): Learning + Hello World**

Not coding the project yet. Focus is **fundamentals**:

- Week 1: 7-day onboarding plan
  - Day 1: OTel videos
  - Day 2: Hello world (Docker Jaeger + OpenLLMetry + Anthropic)
  - Day 3-4: Modify hello world, understand span hierarchy
  - Day 5: Read OpenLLMetry source code (Anthropic instrumentor)
  - Day 6: Slack lurking, read open issues
  - Day 7: Write learning notes (becomes SOP draft material)

- Week 2: Deeper dive
  - Read OTel SpanProcessor docs + examples
  - Read OTel GenAI semconv (now you'll understand 70%)
  - Sketch SpanRedact architecture on paper
  - Set up project skeleton (pyproject.toml, ruff, pytest, GH Actions)

**Deliverable end of Week 2**: working hello world + project skeleton + 1-2
page architecture doc. No SpanRedact-specific code yet.

**Weeks 3-4 (June 15-28): Core redaction**

- Week 3: PII Span Processor
  - Implement SpanProcessor interface
  - Default patterns: email, US SSN, US phone, credit card, API keys, JWT
  - Apply to span events (where OpenLLMetry stores prompt/completion)
  - Unit tests (target: 10-15 tests for critical paths)
- Week 4: Policy modes
  - Implement strict / balanced / debug
  - Environment variable + programmatic API
  - Integration with `spanredact.init()`

**Deliverable end of Week 4**: working `pip install -e . && python examples/anthropic_redaction.py`
shows redacted traces in Jaeger.

**Weeks 5-6 (June 29 – July 12): Diff CLI + audit**

- Week 5: `spanredact diff` CLI
  - Query OTLP backend (start with Jaeger HTTP API)
  - Show before/after for a specific trace
  - Click-based, with `--format=table|json` options
- Week 6: Audit metadata
  - Add `spanredact.redaction.*` attributes to redacted spans
  - CLI command `spanredact report --since=1h` shows aggregated redaction stats

**Deliverable end of Week 6**: working CLI demonstrating audit capabilities.

**Week 7 (July 13-19): Self-validation benchmark + polish**

- Define 5-8 validation tasks (different agent scenarios with planted PII)
- Run tasks, measure: redaction recall, precision, trace completeness
- Generate markdown table for README
- Bug fixes, integration tests

**Week 7 deliverable**: README has a "Validation Results" section with
concrete numbers.

**Week 8 (July 20-27): Launch**

- README.md (5-min quickstart, architecture, validation results,
  comparison-to-OpenLLMetry section)
- Blog post: **"Why I built SpanRedact: making OpenLLMetry safe for
  regulated production"**
- 5-7 min demo video
- Push to GitHub (Apache 2.0)
- Publish to PyPI as `spanredact==0.1.0`
- Launch posts: HN (Show HN), r/MachineLearning, Twitter,
  CNCF Slack #opentelemetry-genai-wg, Traceloop Slack

### 7.2 v0.2 — 4 weeks (August 2026)

Backlog (prioritize after v0.1 community feedback):

- Cross-framework benchmark (OpenLLMetry vs OpenInference vs LangSmith
  native): 5-8 tasks × 3 frameworks
- Microsoft Presidio integration (optional ML-based PII)
- Trace quality validator (`spanredact validate <trace_id>`)
- AWS Bedrock support (if user-requested)
- First PR submitted to OpenLLMetry (likely responding to #3683 or similar
  open issue)

### 7.3 v0.3+ — TBD by community traction (Sep 2026 onwards)

Possible directions:
- Anomaly detection (sliding window alerts for sensitive content patterns)
- A2A trace context propagation (response to OpenLLMetry #3683)
- Continued upstream contributions to OpenLLMetry / Jaeger

### 7.4 Hard discipline rules

1. **Ship early > ship complete**. Once Week 4 (core redaction) is working,
   the project is technically launchable. Weeks 5-7 add value but aren't
   blocking.
2. **Cut features before extending timeline**. If Week 5 falls behind, cut
   Week 7 benchmark first.
3. **Stuck > 30 min on design → pick simpler, log decision in DECISIONS.md**.
4. **No new feature in Week 8**. That week is purely launch prep + docs.

---

## 8. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|-----------|
| OpenLLMetry ships first-class redaction, makes SpanRedact redundant | Medium-High | High | Frame as feature: "SpanRedact prototype influenced upstream". |
| OpenLLMetry breaking API change between v0.1 and v0.2 | Medium | Medium | Pin compatible OpenLLMetry version range. CI runs against latest + pinned. |
| PII pattern false-positive causes user complaint | Medium | Medium | Conservative defaults. Allowlist mechanism. Clear docs on tuning patterns. |
| PII pattern false-negative (leak) reported as security issue | Low | Very High | Conservative defaults, explicit "this is regex, not ML" caveat in docs. Beta testers told "evaluate before production". `SECURITY.md` with responsible disclosure path. |
| OTel SpanProcessor approach doesn't work for streaming responses | Medium | Medium | Pre-investigate Week 2. Fallback: process at OTLP export time (different OTel extension point). |
| Solo maintainer burnout | Medium | High | Hard 12hr/week max. Week off between v0.1 and v0.2 start. |
| Community feedback after Week 8 launch suggests wrong direction | Possible | High | If signal is clear (e.g., "users want X feature you don't have"), pivot v0.2 plan. Don't ego-defend the PRD. |

---

## 9. Success Metrics

### 9.1 v0.1 launch metrics (end of Week 8)

**Engagement signals**:
- GitHub stars: target **30-50** week 1, **100-200** by end of August
- HN Show HN: target **front page (>50 points)** as stretch goal; "any HN
  attention" as baseline
- Twitter impressions on launch tweet: **1000+**

**Quality signals**:
- PyPI downloads: target **50** week 1 (realistic for niche tool), **200** by
  end of August
- 1+ external PR (any size) within 2 weeks of launch
- 1+ external user reports actual usage via GitHub issue or Twitter

**Strategic signals (most important)**:
- **1+ inbound DM from someone at a regulated company** (fintech /
  healthtech / legaltech / etc.) — validates the primary persona
- Mention by Traceloop / OpenLLMetry community (retweet, "see also" in their
  Slack, comment on a GitHub issue) — this validates the differentiation
- Mention in 1+ industry newsletter (TLDR, Bytecast, Latent Space, AlphaSignal)

### 9.2 Realistic expectations

Calibrated:
- **30-100 stars** = healthy reception for an OSS infra niche tool in 8 weeks
- **100-300 stars** = strong reception, indicates real adoption interest
- **300+ stars** = exceptional, indicates breakout potential (rare)

Stars are vanity metric. The real signal is **inbound from regulated
companies**, even if star count is modest.

---

## 10. Open Questions Log

Decisions to make as the project develops. Track here.

| ID | Question | Status | Notes |
|----|---------|--------|-------|
| Q1 | Repo name: `spanredact` confirmed | DECIDED | PyPI verified available 2026-05-26. |
| Q2 | License: Apache 2.0 confirmed | DECIDED | Same as OpenLLMetry + OTel ecosystem. Never change. |
| Q3 | Use Microsoft Presidio in v0.1? | DECIDED | No. Regex in v0.1, Presidio optional in v0.2. |
| Q4 | Should v0.1 support OpenAI in addition to Anthropic? | OPEN | Realistically yes — OpenLLMetry handles both, redaction is content-agnostic. Decide Week 3. |
| Q5 | Capture-content default: balanced or strict? | OPEN | Lean balanced (redacted content > no content for debug). Validate with 3-5 user conversations. |
| Q6 | Streaming response handling | OPEN | Investigate Week 2 during OpenLLMetry source code reading. May force SpanProcessor → OTLP exporter pipeline change. |
| Q7 | Audit log destination | OPEN | v0.1: optional file. v0.2: maybe ship to OTel as separate signal stream? |
| Q8 | Docker compose with Jaeger + example agent for instant demo | OPEN | High-value for adoption. Defer to Week 8 if time. |
| Q9 | What's SpanRedact's relationship with OpenInference's existing per-field masking? | OPEN | Research Week 1. May want to support OpenInference as alternative dependency, not just OpenLLMetry. |
| Q10 | Should we instrument tool call arguments separately from prompt content? | OPEN | Tool args often contain less PII but more sensitive data (API endpoints, IDs). May want different default policy. |

---

## 11. Appendix

### 11.1 Reference materials

- **OpenLLMetry** (primary dependency): github.com/traceloop/openllmetry
- **OpenTelemetry GenAI semconv**: opentelemetry.io/docs/specs/semconv/gen-ai/
- **OpenInference** (adjacent project): github.com/Arize-ai/openinference
- **OTel SpanProcessor docs**: opentelemetry.io/docs/specs/otel/trace/sdk/#span-processor
- **OpenLLMetry A2A propagation issue**: github.com/traceloop/openllmetry/issues/3683
- **OpenLLMetry cost metrics issue**: github.com/traceloop/openllmetry/issues/1042
- **Microsoft Presidio** (v0.2 candidate): github.com/microsoft/presidio
- **EU AI Act**: digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai

### 11.2 Glossary

| Term | Meaning |
|------|--------|
| OTel | OpenTelemetry — observability framework |
| Span | A unit of work in a trace with start/end time + attributes |
| SpanProcessor | OTel extension point that intercepts spans before export |
| OTLP | OpenTelemetry Protocol — for sending traces over gRPC/HTTP |
| Exporter | Component that sends spans to a backend (Jaeger, Datadog, etc.) |
| gen_ai.* | Namespace for OTel GenAI-specific attributes |
| PII | Personally Identifiable Information — emails, SSN, etc. |
| Redaction | Removing or replacing PII before data leaves user's infrastructure |
| Policy mode | SpanRedact concept — preset of redaction behavior (strict/balanced/debug) |
| Audit metadata | Span attributes showing what redaction was applied |

---

## 12. Decision log

| Date | Decision | Rationale |
|------|---------|-----------|
| 2026-05-24 | Project pivot: otel-genai → SpanRedact | 3-round AI cross-review revealed otel-genai positioning competed head-on with OpenLLMetry (7.1k stars, mature). SpanRedact builds on top instead. |
| 2026-05-24 | Apache 2.0 license | Aligns with OpenLLMetry + OTel ecosystem. Patent grant matters for enterprise users. Never change. |
| 2026-05-24 | Python only for v0.x | Solo maintainer time constraint. Python is dominant LLM agent language. |
| 2026-05-24 | Default policy = balanced | Strict loses debug value; debug loses safety. Balanced (redacted content) is the right default for primary persona. |
| 2026-05-24 | Build as SpanProcessor, not OpenLLMetry fork | Standard OTel extension point. Lets SpanRedact evolve independently of OpenLLMetry releases. |
| 2026-05-24 | v0.1 ships with self-validation only, not cross-framework benchmark | Cross-framework benchmark is a 1-2 week project on its own. Defer to v0.2. |
| 2026-05-26 | Name `spanredact` confirmed available on PyPI | curl pypi.org/pypi/spanredact/json → 404 |

### 12.1 Adversarial review (preempting hostile critique)

Hypothetical hostile reviewer: a Traceloop engineer or LangSmith advocate.

**Critique 1**: "Why doesn't OpenLLMetry just add this as a config flag?"

**Response**: It might. SpanRedact's job is to demonstrate the gap and
provide a working prototype until upstream adopts a similar pattern. If
upstream adopts, SpanRedact deprecates gracefully.

**Critique 2**: "Regex-based PII detection is unreliable. Why not Presidio
or LLM-based?"

**Response**: Regex is the v0.1 baseline because it's deterministic, fast,
and auditable (compliance teams can read patterns). v0.2 adds optional
Presidio for ML-based detection. LLM-based is rejected for v0.x because
it adds cost + latency + dependency on the same LLM we're trying to observe.

**Critique 3**: "Three policy modes is a half-baked taxonomy. Real production
needs per-field rules."

**Response**: True, and v0.2 will support per-field rules. The three modes
are v0.1 simplicity — they cover 80% of cases. Per-field rules are an
escape hatch for the 20%.

**Critique 4**: "This is just OpenInference's masking with extra steps."

**Response**: OpenInference's masking is a per-field utility within their
SDK. SpanRedact is a project-level layer: policy modes + audit CLI + diff
tooling. Different products. We can potentially support OpenInference as
an alternative dependency (Q9 in open questions).

### 12.2 "What if we're wrong" — invalidation scenarios

If these assumptions break, the project needs to repivot:

1. **"Regulated industry doesn't actually use OpenLLMetry"**: They use
   Langfuse self-hosted or Phoenix instead. Then SpanRedact becomes a
   redaction layer for those tools. → Pivot work: ~1 week to add Langfuse
   adapter.

2. **"PII isn't the main blocker; cost / quality is"**: Then SpanRedact
   becomes cost-attribution + quality-validation layer. → Pivot work: ~2-3
   weeks to switch focus.

3. **"OpenLLMetry adds first-class redaction in v0.6x"**: SpanRedact
   deprecates gracefully. Portfolio value still preserved through the PRD,
   blog post, and PRs submitted upstream.

4. **"No regulated industry adopters; only solo dev users"**: SpanRedact's
   real value isn't PII; it's audit tooling. Pivot toward dev-focused
   "what's actually in my LLM traces" CLI tool.

---

**End of document.**
