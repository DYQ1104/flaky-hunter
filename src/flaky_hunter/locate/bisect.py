"""Binary search for the smallest failing prefix.

Assumption (documented, not proven): if a prefix of length m makes the target
fail, any longer prefix also fails. Pollution is usually additive, so this holds
in practice; when it does not, the evidence table makes it visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..models import ProbeOutcome

ProbeFn = Callable[[list[str]], Optional[ProbeOutcome]]


@dataclass
class BisectOutcome:
    prefix_length: int
    status: str  # ok | budget | indeterminate
    detail: str = ""


def bisect_prefix(
    prefix: list[str], target: str, probe: ProbeFn
) -> BisectOutcome:
    lo, hi = 0, len(prefix)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        outcome = probe(prefix[:mid] + [target])
        if outcome is None:
            return BisectOutcome(hi, "budget")
        if outcome.indeterminate:
            return BisectOutcome(hi, "indeterminate", outcome.outcome)
        if outcome.passed:
            lo = mid
        else:
            hi = mid
    return BisectOutcome(hi, "ok")
