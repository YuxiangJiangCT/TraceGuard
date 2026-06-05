"""Default PII regex patterns, compiled once at import.

Each pattern is (name, compiled_regex). The name is what we report in audit
metadata (traceguard.redaction.patterns_matched). Patterns are intentionally
conservative — better to occasionally miss an exotic format than to over-redact
useful debugging content. Users can extend this list (Week 4+).
"""

from __future__ import annotations

import re

# More specific patterns (api keys, JWT) before generic ones so their matches
# aren't partially eaten by a looser pattern.
_RAW_PATTERNS: list[tuple[str, str]] = [
    # API keys: prefix + long token body (sk-, pk-, ghp-, etc.).
    ("api_key", r"\b(?:sk|pk|ghp|gho|ghs|ghu|rk)[-_][A-Za-z0-9\-_]{16,}\b"),
    # Google API key.
    ("google_api_key", r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    # JWT: three base64url segments separated by dots.
    ("jwt", r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b"),
    # Email.
    ("email", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    # US SSN: 3-2-4 digits with dashes.
    ("us_ssn", r"\b\d{3}-\d{2}-\d{4}\b"),
    # Credit card: 13-16 digits with optional spaces/dashes.
    ("credit_card", r"\b(?:\d[ -]?){13,16}\b"),
    # US phone.
    ("us_phone", r"(?:\+?1[ \-.]?)?\(?\d{3}\)?[ \-.]?\d{3}[ \-.]?\d{4}\b"),
]

# Compile once at import (PRD §6.5: per-span redaction < 1ms; don't recompile
# on every call). This is the live list the redactor reads; add_pattern() and
# the env loader append to it.
DEFAULT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rx)) for name, rx in _RAW_PATTERNS
]


def add_pattern(name: str, regex: str) -> None:
    """Register a custom PII pattern (compiled and appended to DEFAULT_PATTERNS).

    Example:
        from traceguard import add_pattern
        add_pattern("internal_id", r"INT-\\d{6}")
    """
    DEFAULT_PATTERNS.append((name, re.compile(regex)))

