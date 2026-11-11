"""Order-dependence experiments and polluter localization."""

from __future__ import annotations

from typing import Callable, Optional

from ..models import (
    LocateResult,
    LocateStatus,
    ProbeEvidence,
    ProbeOutcome,
)
from .bisect import bisect_prefix
from .budget import ProbeBudget
from .minimize import minimize_blockers

ProbeCallback = Callable[[list[str]], ProbeOutcome]


class _Recorder:
    """Wraps a probe callback with budget accounting and evidence capture."""

    def __init__(self, probe: ProbeCallback, budget: ProbeBudget) -> None:
        self._probe = probe
        self.budget = budget
        self.evidence: list[ProbeEvidence] = []

    def __call__(self, tests: list[str]) -> Optional[ProbeOutcome]:
        if not self.budget.can_probe():
            return None
        self.budget.consume()
        try:
            outcome = self._probe(tests)
        except Exception as exc:  # isolate probe failures from the analysis
            outcome = ProbeOutcome("invalid", 0.0, str(exc)[:300])
        self.evidence.append(
            ProbeEvidence(
                index=len(self.evidence) + 1,
                tests=list(tests),
                outcome=outcome.outcome,
                duration_ms=outcome.duration_ms,
            )
        )
        return outcome


def _result(
    status: LocateStatus,
    recorder: _Recorder,
    blockers: Optional[list[str]] = None,
    note: str = "",
    confidence: str = "low",
) -> LocateResult:
    return LocateResult(
        status=status,
        blockers=list(blockers or []),
        probes_used=recorder.budget.used,
        confidence=confidence,
        evidence=recorder.evidence,
        note=note,
    )


def locate_polluters(
    target: str,
    prefix: list[str],
    probe: ProbeCallback,
    budget: Optional[ProbeBudget] = None,
    confirm_runs: int = 2,
    baseline_runs: int = 2,
) -> LocateResult:
    """Find the minimal set of tests that make ``target`` fail.

    ``prefix`` must be the tests that execute before ``target`` in the original
    order. The callback runs a subset and reports passed/failed/timeout/invalid.
    """
    recorder = _Recorder(probe, budget or ProbeBudget())
    baseline_runs = max(1, baseline_runs)
    confirm_runs = max(1, confirm_runs)

    if not prefix:
        return _result(
            LocateStatus.INCONCLUSIVE, recorder, note="目标用例之前没有其他用例"
        )

    baseline_passes = 0
    for _ in range(baseline_runs):
        outcome = recorder([target])
        if outcome is None:
            return _result(LocateStatus.ABORTED, recorder, note="probe 预算耗尽")
        if outcome.passed:
            baseline_passes += 1
        elif outcome.indeterminate:
            return _result(
                LocateStatus.ABORTED,
                recorder,
                note=f"单独执行结果不可判定: {outcome.outcome}",
            )

    if baseline_passes == 0:
        return _result(
            LocateStatus.NOT_ORDER_DEPENDENT,
            recorder,
            note="单独执行也稳定失败，属于真实缺陷而非顺序依赖",
        )
    if baseline_passes < baseline_runs:
        return _result(
            LocateStatus.NOT_ORDER_DEPENDENT,
            recorder,
            note="单独执行结果不稳定，无法归因为顺序依赖",
        )

    full = recorder(prefix + [target])
    if full is None:
        return _result(LocateStatus.ABORTED, recorder, note="probe 预算耗尽")
    if full.indeterminate:
        return _result(
            LocateStatus.ABORTED,
            recorder,
            note=f"全量执行结果不可判定: {full.outcome}",
        )
    if full.passed:
        return _result(
            LocateStatus.INCONCLUSIVE,
            recorder,
            note="按原始顺序执行未能复现失败，可尝试增加轮次或检查环境差异",
        )

    bisected = bisect_prefix(prefix, target, recorder)
    if bisected.status == "budget":
        return _result(
            LocateStatus.PARTIAL,
            recorder,
            blockers=prefix[: bisected.prefix_length],
            note="二分过程中预算耗尽，结论可能不是最小的",
            confidence="medium",
        )
    if bisected.status == "indeterminate":
        return _result(
            LocateStatus.ABORTED,
            recorder,
            note=f"二分过程中出现不可判定结果: {bisected.detail}",
        )

    blockers, minimize_status = minimize_blockers(
        prefix[: bisected.prefix_length], target, recorder
    )
    if not blockers:
        return _result(
            LocateStatus.INCONCLUSIVE,
            recorder,
            note="未能收敛到非空前序集合",
        )

    confirmed = 0
    budget_hit = False
    for _ in range(confirm_runs):
        outcome = recorder(blockers + [target])
        if outcome is None:
            budget_hit = True
            break
        if outcome.failed:
            confirmed += 1

    if budget_hit:
        return _result(
            LocateStatus.PARTIAL,
            recorder,
            blockers=blockers,
            note="复核阶段预算耗尽",
            confidence="medium",
        )
    if confirmed < confirm_runs:
        return _result(
            LocateStatus.UNSTABLE_EVIDENCE,
            recorder,
            blockers=blockers,
            note=f"复核仅 {confirmed}/{confirm_runs} 次失败，结论不稳定",
            confidence="low",
        )

    note = ""
    if minimize_status == "budget":
        note = "最小化阶段预算耗尽，污染源可能不是最小的"
    return _result(
        LocateStatus.FOUND,
        recorder,
        blockers=blockers,
        note=note,
        confidence="high",
    )
