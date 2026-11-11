"""Greedy minimisation of the polluter set."""

from __future__ import annotations

from typing import Callable, Optional

from ..models import ProbeOutcome

ProbeFn = Callable[[list[str]], Optional[ProbeOutcome]]


def minimize_blockers(
    blockers: list[str], target: str, probe: ProbeFn
) -> tuple[list[str], str]:
    """Drop every candidate that is not required to make ``target`` fail."""
    current = list(blockers)
    for candidate in list(blockers):
        if candidate not in current:
            continue
        trial = [item for item in current if item != candidate]
        outcome = probe(trial + [target])
        if outcome is None:
            return current, "budget"
        if outcome.indeterminate:
            continue
        if outcome.failed:
            current = trial
    return current, "ok"
