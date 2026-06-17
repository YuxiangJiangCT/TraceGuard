# Contributing to SpanRedact

Thanks for your interest. SpanRedact is a small, opinionated layer; the
goal is to keep the core narrow and stable, not grow features for their
own sake.

## Setup

```bash
git clone https://github.com/YuxiangJiangCT/SpanRedact.git
cd SpanRedact
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,examples]"
pytest -v        # 18 tests, ~0.1s
ruff check src tests
```

## What's most useful right now

In order of impact:

1. **Real-world PII pattern misses.** If your team uses SpanRedact and
   something obvious (e.g., IBAN, AWS access key) leaked through, open a
   GitHub issue with a redacted sample so we can extend the default set
   or document the gap. This is feedback we can't generate ourselves.
2. **Integration reports.** Tried it with a non-Anthropic OpenLLMetry
   instrumentation? Tell us whether the attribute names matched
   ADR-002's assumptions; if not, we may need a fallback set.
3. **Documentation fixes.** README, ADRs, docstrings — clarity beats
   completeness.

## What's NOT helpful right now

- New PII patterns invented from scratch with no real source — adds
  false-positive risk for no real-world benefit.
- Refactors of the core for "cleanliness" — see PRD's "do not over-build"
  rule.
- Adding new providers / frameworks before v0.1 stabilizes.

## Pull requests

- One logical change per PR.
- Tests for new behavior. We don't enforce a coverage threshold but
  every PR should leave `pytest` and `ruff check` clean.
- For non-trivial changes, please open an issue first to discuss; saves
  both of us time.

## Reporting security issues

See [SECURITY.md](SECURITY.md) — do not file public issues for security
problems.

## Architecture context

Before touching the redaction core, please read:

- [docs/PRD.md](docs/PRD.md) — what the project is for and is not.
- [docs/DECISIONS.md](docs/DECISIONS.md) — ADRs with evidence behind each
  choice (especially ADR-001 on why we use a `SpanExporter` wrapper
  instead of a `SpanProcessor`).

## License

By contributing you agree your work is licensed under Apache 2.0, the
same as the rest of the repo.
