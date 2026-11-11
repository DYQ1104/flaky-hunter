"""Pick which findings are worth spending probes on."""

from __future__ import annotations

from ..models import Classification, Finding


def select_targets(findings: list[Finding], top_n: int) -> list[Finding]:
    """Flaky tests first (by score), then broken ones (by failure count).

    Broken tests are included on purpose: "fails alone" and "fails only after
    other tests" are indistinguishable from the report alone, and two probes
    settle it.
    """
    flaky = [f for f in findings if f.classification == Classification.FLAKY]
    broken = [f for f in findings if f.classification == Classification.BROKEN]
    flaky.sort(key=lambda f: (-f.score, f.nodeid))
    broken.sort(key=lambda f: (-f.failures, f.nodeid))
    return (flaky + broken)[: max(0, top_n)]
