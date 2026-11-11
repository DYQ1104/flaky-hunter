"""Flakiness scoring and bucketing.

The score deliberately is *not* the failure rate. A test that fails every time
is broken, not flaky; the most dangerous test is the one that flips 50/50.
"""

from __future__ import annotations

from ..models import Classification

# Attempts needed before we fully trust a rate. Below this, the score is
# scaled down because a 1-of-2 failure rate is not evidence of much.
CONFIDENCE_ATTEMPTS = 10


def compute_score(attempts: int, failures: int) -> int:
    """Return a 0-100 flakiness score.

    ``U = 4p(1-p)`` is the Gini impurity: 0 at p=0 and p=1, 1 at p=0.5.
    ``C = min(1, attempts / 10)`` down-weights small samples.
    """
    if attempts <= 0:
        return 0
    failures = max(0, min(failures, attempts))
    rate = failures / attempts
    instability = 4.0 * rate * (1.0 - rate)
    confidence = min(1.0, attempts / float(CONFIDENCE_ATTEMPTS))
    return int(round(100.0 * instability * confidence))


def classify_outcome(
    attempts: int, failures: int, min_attempts: int = 5
) -> Classification:
    if attempts < min_attempts:
        return Classification.INSUFFICIENT
    if failures == 0:
        return Classification.STABLE
    if failures >= attempts:
        return Classification.BROKEN
    return Classification.FLAKY
