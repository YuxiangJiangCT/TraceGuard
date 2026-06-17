"""Core redaction logic — no OpenTelemetry dependency, so it's trivially testable.

Two layers (ADR-002):
  redact_text(s)            -> plain regex pass over a string.
  redact_attribute_value(s) -> JSON-aware: parse the GenAI messages JSON, redact
                               only the string leaves, re-serialize. Falls back
                               to redact_text if the value isn't list/dict JSON.
"""

from __future__ import annotations

import json
import re

from .patterns import DEFAULT_PATTERNS, VALIDATORS

REDACTED = "[REDACTED]"

# Guard against pathological inputs (deep nesting / huge blobs). Beyond these we
# skip JSON walking and just regex the raw string — safe and fast.
_MAX_JSON_DEPTH = 50
_MAX_VALUE_LEN = 1_000_000


def redact_text(
    text: str,
    patterns: list[tuple[str, re.Pattern[str]]] | None = None,
) -> tuple[str, set[str]]:
    """Replace every PII match in `text` with [REDACTED].

    Returns (redacted_text, set_of_pattern_names_that_matched).
    """
    if patterns is None:
        patterns = DEFAULT_PATTERNS
    matched: set[str] = set()
    for name, rx in patterns:
        validator = VALIDATORS.get(name)
        if validator is None:
            if rx.search(text):
                matched.add(name)
                text = rx.sub(REDACTED, text)
        else:
            # Pattern has a validator: only redact matches that pass it.
            def _replace(m: re.Match[str], _name: str = name, _ok=validator) -> str:
                if _ok(m.group(0)):
                    matched.add(_name)
                    return REDACTED
                return m.group(0)

            text = rx.sub(_replace, text)
    return text, matched


def _redact_json_node(node: object, matched: set[str], depth: int) -> object:
    """Recursively redact string leaves in parsed JSON, preserving structure."""
    if depth > _MAX_JSON_DEPTH:
        # Too deep — serialize and regex this subtree as a backstop.
        cleaned, found = redact_text(json.dumps(node, ensure_ascii=False))
        matched |= found
        return cleaned
    if isinstance(node, str):
        redacted, found = redact_text(node)
        matched |= found
        return redacted
    if isinstance(node, list):
        return [_redact_json_node(item, matched, depth + 1) for item in node]
    if isinstance(node, dict):
        # Redact values only; keys like "role"/"type" are structure, leave them.
        return {k: _redact_json_node(v, matched, depth + 1) for k, v in node.items()}
    # int/float/bool/None — not PII-bearing.
    return node


def redact_attribute_value(value: str) -> tuple[str, set[str]]:
    """Redact a span attribute value that may be a GenAI messages JSON string.

    1. Try JSON; if list/dict, redact string leaves and re-serialize.
    2. Otherwise (not JSON, bare scalar, too large) regex the whole value.
    """
    if not isinstance(value, str):
        return value, set()
    if len(value) > _MAX_VALUE_LEN:
        return redact_text(value)
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return redact_text(value)

    if not isinstance(parsed, (list, dict)):
        # Bare JSON scalar — regex the original string so we keep the backstop.
        return redact_text(value)

    matched: set[str] = set()
    cleaned = _redact_json_node(parsed, matched, depth=0)
    return json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False), matched
