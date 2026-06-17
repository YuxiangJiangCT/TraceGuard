# Architecture Decision Records

Lightweight ADRs for SpanRedact. Each records context, the decision, the
evidence behind it, and the consequences. Newest first.

---

## ADR-002: Redaction targets `gen_ai.input.messages` / `gen_ai.output.messages`, which are JSON

**Status**: Accepted
**Context date**: Week 1, after running real OpenLLMetry + Anthropic end-to-end

### Context

Every attribute key in the spike and early hello examples (`gen_ai.prompt`,
`gen_ai.completion`) was a hand-typed guess. We ran a real Claude call through
OpenLLMetry and inspected the actual span in Jaeger to replace guesses with
ground truth.

### What we found (ground truth, verified in Jaeger)

Running `traceloop-sdk==0.61.0` /
`opentelemetry-instrumentation-anthropic==0.61.0`, a real
`client.messages.create()` produced span `anthropic.chat` with:

- **Prompt content** → `gen_ai.input.messages` (NOT `gen_ai.prompt`)
- **Completion content** → `gen_ai.output.messages` (NOT `gen_ai.completion`)
- Both values are **JSON strings**, not plain text:
  ```json
  [{"role": "user", "parts": [{"type": "text", "content": "Say hello..."}]}]
  ```
- Other keys present: `gen_ai.provider.name=anthropic`,
  `gen_ai.request.model`, `gen_ai.usage.{input,output,total}_tokens`,
  `gen_ai.response.id`, `gen_ai.operation.name=chat`. Scope:
  `opentelemetry.instrumentation.anthropic`.

### Decision / consequences for redaction (Week 3)

1. **Target the new-semconv keys** `gen_ai.input.messages` /
   `gen_ai.output.messages` as the primary PII-bearing attributes. Keep the
   legacy `gen_ai.prompt` / `gen_ai.completion` as fallbacks (older
   instrumentation versions / `use_legacy_attributes` mode may still emit
   them — Traceloop.init exposes `use_legacy_attributes` / `use_attributes`).
2. **PII lives inside JSON**, at `messages[].parts[].content`. Redaction must
   parse the JSON, walk to each `content` string, redact, and re-serialize —
   NOT just regex the whole attribute value blindly (though a regex pass over
   the serialized string is a safe backstop). This is more involved than the
   spike's plain-string redaction and is the key design input for Week 3.
3. Spike/hello placeholder keys (`gen_ai.prompt`) are now known to be wrong
   for current OpenLLMetry; do not treat them as the only target.

### Evidence
`examples/hello_openllmetry.py` + Jaeger trace for service
`spanredact-openllmetry-demo`, inspected via the Jaeger HTTP API
(`/api/traces?service=...`).

---

## ADR-001: Implement redaction as a SpanExporter wrapper (not a SpanProcessor)

**Status**: Accepted
**Context date**: project pre-development phase (architecture spike)

### Context

PRD §6 originally described SpanRedact as an OTel `SpanProcessor`. Research
showed this is not viable on the current OpenTelemetry Python SDK path:
`SpanProcessor.on_end()` receives a `ReadableSpan`, and the OTel spec states
that even if the passed span is technically writable, modifying it after the
span has ended is not allowed.

- [opentelemetry-specification#2990](https://github.com/open-telemetry/opentelemetry-specification/issues/2990) (closed) — spec confirms `onEnd` receives a read-only span
- [opentelemetry-python#4424](https://github.com/open-telemetry/opentelemetry-python/issues/4424) (open) — community asks for hooks before `ReadableSpan` conversion
- The spec defines an `OnEnding` callback (span still mutable) but it is in
  **Development** status — not a stable foundation for v0.1.

We needed an approach that:
1. modifies span content before it reaches the OTLP exporter, and
2. relies only on stable, public SDK API.

### Decision

Implement redaction as a **`SpanExporter` wrapper**. The wrapper receives
`Sequence[ReadableSpan]` in `export()`, builds a NEW `ReadableSpan` per span
with sanitized attributes, and forwards the sanitized spans to the wrapped
(downstream) exporter.

Key mechanism: `ReadableSpan.__init__` is public and accepts an `attributes`
mapping, so we can construct a faithful redacted copy. We do NOT mutate
`span._attributes` — `.attributes` is a read-only `MappingProxyType` view.

### Evidence (architecture spike)

Verified against `opentelemetry-sdk==1.42.1` on Python 3.12.11.

- `ReadableSpan.__init__` signature confirmed to accept `attributes`,
  `context`, `parent`, `resource`, `events`, `links`, `kind`,
  `instrumentation_scope`, `status`, `start_time`, `end_time`.
- `SpanExportResult` = `{SUCCESS=0, FAILURE=1}`.
- Spike script: `spike/redact_exporter_spike.py` — a `RedactingSpanExporter`
  wrapping `ConsoleSpanExporter`. A mock span with
  `gen_ai.prompt = "my email is leak@test.com please redact"` was exported.

Result (exit code 0):
```
"gen_ai.prompt": "my email is [REDACTED] please redact"
raw secret leaked?   False   (want False)
[REDACTED] present?  True    (want True)
metadata preserved?  True    (want True)   # gen_ai.system, input_tokens, trace_id intact
```

The raw email never reached the downstream exporter; non-PII metadata and
trace/span IDs were preserved.

### Consequences

- **Positive**: stable public API; SpanRedact upgrades independently of
  OpenLLMetry; resolves the PRD §8 "SpanProcessor won't work" risk; also the
  natural place to handle streaming responses (export-time, after the span is
  final).
- **Negative / to watch**:
  - We rebuild every span object — small per-span allocation cost. Must stay
    within the PRD §6.5 budget (< 1 ms p50). Measure in Week 3.
  - `instrumentation_info` constructor arg is deprecated since SDK 1.11.1 —
    use `instrumentation_scope` only.
  - Redaction must target content-carrying keys wherever they appear: span
    attributes AND GenAI event attributes (e.g.
    `gen_ai.client.inference.operation.details`). The spike only covered span
    attributes; event coverage is a Week 3 task.
  - The spike used raw OTel SDK + a mock span. The real attribute keys and
    injection timing for OpenLLMetry's Anthropic instrumentation still need
    to be verified against a live trace (Week 1 / Week 3).

### Rejected alternatives

- **Plan B — custom span-buffering processor upstream of BatchSpanProcessor**:
  more moving parts, would duplicate batching logic. Held in reserve only if
  the wrapper approach hits a wall with a specific exporter.
- **Plan C — fork OTLP serialization**: brittle, couples us to exporter
  internals. Avoided.
