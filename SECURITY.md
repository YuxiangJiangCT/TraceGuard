# Security Policy

## Reporting a vulnerability

If you believe you've found a security issue in TraceGuard — including, but
not limited to, a way that PII redaction can be bypassed or that the
exporter can leak content it shouldn't — **please do NOT open a public
GitHub issue**.

Instead, email the maintainer directly: **yj548@cornell.edu**.

If you prefer encrypted reporting, request a PGP key in your first email
and we'll exchange one.

Please include:

- A clear description of the issue and its impact.
- Minimum versions of `traceguard`, `opentelemetry-sdk`, and (if relevant)
  `traceloop-sdk` that reproduce it.
- A minimal reproduction (script or test).
- Whether the issue is already public anywhere.

I aim to acknowledge reports within **72 hours** and will keep you informed
of progress. Fixes will be released as patch versions; coordinated
disclosure timing can be discussed case-by-case.

## Scope

In-scope:

- The `traceguard` package and its examples.
- Default PII patterns failing to redact what they document.
- Audit attributes being inaccurate or missing on changed spans.
- TraceGuard's `SpanExporter` wrapper accidentally forwarding non-redacted
  content downstream.

Out-of-scope (please report to the relevant project instead):

- Bugs in `opentelemetry-sdk`, `opentelemetry-instrumentation-anthropic`,
  or `traceloop-sdk`.
- Issues in the user's downstream backend (Jaeger, Datadog, etc.).
- PII regex false negatives that fall outside the documented pattern
  guarantees — please open a regular GitHub issue with the sample.

## Known limitations

- **Regex-based detection is not ML-based.** TraceGuard v0.1 will miss
  exotic PII formats and obfuscated content by design. This is documented
  in [docs/PRD.md](docs/PRD.md) §3.2 NG4 and §8 risk table.
- **Beta software.** v0.1 should be evaluated against your own data before
  any production use in regulated workloads.
