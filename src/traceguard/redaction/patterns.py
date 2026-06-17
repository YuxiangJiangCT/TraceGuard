"""Default PII regex patterns, compiled once at import.

Each pattern is (name, compiled_regex). The name is what we report in audit
metadata (traceguard.redaction.patterns_matched). us_phone favors recall over
precision — it matches any 10-digit run and can over-match non-PII such as
order IDs or timestamps (the intended privacy-first failure mode: over-redact
rather than leak). credit_card matches 13-16 digit runs but is Luhn-validated
(see VALIDATORS below) so it skips most random numbers. Users can extend this
list via add_pattern().
"""

from __future__ import annotations

import re
from collections.abc import Callable

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


def _luhn_ok(candidate: str) -> bool:
    """True if the digit run in `candidate` passes the Luhn checksum.

    Genuine credit-card numbers satisfy Luhn; a random 13-16 digit string
    passes only ~1 in 10, so validating drops most false positives with no
    recall loss on real cards.
    """
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for pos, d in enumerate(reversed(digits)):
        if pos % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Optional per-pattern validators. A regex match for `name` is only redacted
# when VALIDATORS[name](match_text) is True — letting a permissive regex stay
# permissive while dropping obvious false positives (credit_card: valid Luhn).
VALIDATORS: dict[str, Callable[[str], bool]] = {
    "credit_card": _luhn_ok,
}


def add_pattern(name: str, regex: str) -> None:
    """Register a custom PII pattern (compiled and appended to DEFAULT_PATTERNS).

    Example:
        from traceguard import add_pattern
        add_pattern("internal_id", r"INT-\\d{6}")
    """
    DEFAULT_PATTERNS.append((name, re.compile(regex)))

