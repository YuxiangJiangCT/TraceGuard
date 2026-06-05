"""Policy modes controlling what happens to PII-bearing content attributes.

  strict   — drop content attributes entirely (keep only metadata).
  balanced — redact PII inside content (default for production).
  debug    — passthrough, no redaction (local dev only, never for prod).
"""

from __future__ import annotations

from enum import Enum

# Span attribute keys that carry prompt/completion content. Verified in ADR-002:
# current OpenLLMetry uses gen_ai.input/output.messages; legacy versions emit
# gen_ai.prompt/completion. We target all of them.
CONTENT_KEYS: tuple[str, ...] = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.prompt",
    "gen_ai.completion",
)


class Policy(str, Enum):
    STRICT = "strict"
    BALANCED = "balanced"
    DEBUG = "debug"

    @classmethod
    def from_str(cls, value: str | None, default: "Policy" = None) -> "Policy":
        if value is None:
            return default or cls.BALANCED
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            raise ValueError(
                f"Unknown TraceGuard policy {value!r}; expected one of "
                f"{[p.value for p in cls]}"
            ) from exc
