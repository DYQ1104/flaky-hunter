"""Heuristic root-cause labels for failure clusters."""

from __future__ import annotations

import re

# Order matters: the first match wins. Specific infrastructure failures are
# checked before the generic AssertionError bucket.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "timeout",
        re.compile(
            r"TimeoutError|timed out|deadline exceeded|pytest-timeout", re.IGNORECASE
        ),
    ),
    (
        "network",
        re.compile(
            r"ConnectionError|Connection refused|Connection reset"
            r"|Name or service not known|Temporary failure in name resolution"
            r"|ECONNREFUSED|\b50[234]\b",
            re.IGNORECASE,
        ),
    ),
    (
        "data-residue",
        re.compile(
            r"UNIQUE constraint failed|Duplicate entry|already exists|IntegrityError",
            re.IGNORECASE,
        ),
    ),
    (
        "concurrency",
        re.compile(r"deadlock|Lock wait timeout|race condition", re.IGNORECASE),
    ),
    (
        "resource",
        re.compile(
            r"Too many open files|No space left|Out of memory|OOMKilled", re.IGNORECASE
        ),
    ),
    (
        "assertion-mismatch",
        re.compile(r"AssertionError|Assertion Failed", re.IGNORECASE),
    ),
)

KNOWN_LABELS = tuple(label for label, _ in _RULES) + ("order-dependent", "unknown")


def classify_message(text: str) -> str:
    """Return a root-cause label for a failure message/trace pair."""
    if not text:
        return "unknown"
    for label, pattern in _RULES:
        if pattern.search(text):
            return label
    return "unknown"
