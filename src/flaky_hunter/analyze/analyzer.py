"""Turn raw test results into a report."""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from .. import __version__
from ..config import Config
from ..models import (
    Classification,
    Finding,
    Outcome,
    Report,
    RoundInfo,
    SessionSummary,
    TestResult,
)
from .cluster import cluster_failures
from .scorer import classify_outcome, compute_score

_BUCKET_ORDER = {
    Classification.FLAKY: 0,
    Classification.BROKEN: 1,
    Classification.INSUFFICIENT: 2,
    Classification.STABLE: 3,
}


def ordered_tests_from(results: Iterable[TestResult]) -> list[str]:
    """Return nodeids in execution order, using the earliest usable round."""
    results = list(results)
    if not results:
        return []
    first_round = min(item.round for item in results)
    seen: set[str] = set()
    order: list[str] = []
    for item in results:
        if item.round != first_round or item.nodeid in seen:
            continue
        seen.add(item.nodeid)
        order.append(item.nodeid)
    return order


def _ignored(nodeid: str, patterns: list[str]) -> bool:
    path = nodeid.split("::", 1)[0]
    return any(
        fnmatch.fnmatch(nodeid, pattern) or fnmatch.fnmatch(path, pattern)
        for pattern in patterns
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def analyze(
    results: Iterable[TestResult],
    rounds: list[RoundInfo],
    session_id: str,
    config: Config,
    adapter: str = "pytest",
    command: str = "",
    cwd: str = "",
) -> Report:
    results = list(results)
    order = ordered_tests_from(results)
    grouped: dict[str, list[TestResult]] = defaultdict(list)
    for item in results:
        grouped[item.nodeid].append(item)

    findings: list[Finding] = []
    skipped_tests = 0
    for nodeid in order:
        items = grouped.get(nodeid, [])
        attempts = sum(1 for item in items if item.outcome != Outcome.SKIPPED)
        if attempts == 0:
            skipped_tests += 1
            continue
        if _ignored(nodeid, config.analysis.ignore):
            continue
        failures = sum(1 for item in items if item.outcome.is_failure)
        rounds_present = len(
            {item.round for item in items if item.outcome != Outcome.SKIPPED}
        )
        durations = [item.duration_ms for item in items if item.duration_ms > 0]
        clusters = cluster_failures(items)
        classification = classify_outcome(
            attempts, failures, config.analysis.min_attempts
        )
        findings.append(
            Finding(
                nodeid=nodeid,
                classification=classification,
                attempts=attempts,
                failures=failures,
                score=compute_score(attempts, failures),
                pass_rate=(attempts - failures) / attempts,
                rounds_present=rounds_present,
                duration_avg_ms=_mean(durations),
                duration_max_ms=max(durations) if durations else 0.0,
                clusters=clusters,
                root_cause=clusters[0].label if clusters else "",
            )
        )

    findings.sort(
        key=lambda finding: (
            _BUCKET_ORDER[finding.classification],
            -finding.score,
            -finding.failures,
            finding.nodeid,
        )
    )

    summary = SessionSummary(
        rounds_total=len(rounds),
        rounds_ok=sum(1 for item in rounds if item.status.value == "ok"),
        tests_total=len(findings),
        skipped_tests=skipped_tests,
    )
    for finding in findings:
        setattr(
            summary,
            finding.classification.value,
            getattr(summary, finding.classification.value) + 1,
        )

    return Report(
        session_id=session_id,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        rounds=list(rounds),
        findings=findings,
        summary=summary,
        config_snapshot=config.snapshot(),
        adapter=adapter,
        ordered_tests=order,
        tool_version=__version__,
        command=command,
        cwd=cwd,
    )
