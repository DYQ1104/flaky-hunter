from flaky_hunter.locate import ProbeBudget, locate_polluters
from flaky_hunter.models import LocateStatus, ProbeOutcome

ORDER = [f"t{index}" for index in range(10)]
TARGET = "target"


def _probe_for(required):
    def probe(tests):
        present = set(tests)
        return ProbeOutcome(
            "failed" if all(item in present for item in required) else "passed"
        )

    return probe


def test_finds_single_polluter():
    prefix = ORDER[:8]
    result = locate_polluters(
        TARGET, prefix, _probe_for({"t3"}), ProbeBudget(60), confirm_runs=2
    )
    assert result.status == LocateStatus.FOUND
    assert result.blockers == ["t3"]
    assert result.probes_used <= 20
    assert result.confidence == "high"


def test_drops_irrelevant_tests():
    prefix = ORDER[:6]
    result = locate_polluters(
        TARGET, prefix, _probe_for({"t1"}), ProbeBudget(60), confirm_runs=2
    )
    assert result.blockers == ["t1"]


def test_keeps_synergistic_polluters():
    prefix = ORDER[:6]
    result = locate_polluters(
        TARGET, prefix, _probe_for({"t1", "t4"}), ProbeBudget(60), confirm_runs=2
    )
    assert result.status == LocateStatus.FOUND
    assert result.blockers == ["t1", "t4"]


def test_always_failing_test_is_not_order_dependent():
    result = locate_polluters(
        TARGET, ORDER, lambda tests: ProbeOutcome("failed"), ProbeBudget(60)
    )
    assert result.status == LocateStatus.NOT_ORDER_DEPENDENT
    assert result.blockers == []


def test_inconclusive_when_order_does_not_matter():
    result = locate_polluters(
        TARGET, ORDER, lambda tests: ProbeOutcome("passed"), ProbeBudget(60)
    )
    assert result.status == LocateStatus.INCONCLUSIVE


def test_budget_exhaustion_returns_partial():
    result = locate_polluters(
        TARGET, ORDER[:8], _probe_for({"t3"}), ProbeBudget(3), confirm_runs=2
    )
    assert result.status in (LocateStatus.PARTIAL, LocateStatus.ABORTED)
    assert result.probes_used == 3


def test_empty_prefix():
    result = locate_polluters(TARGET, [], _probe_for(set()), ProbeBudget(10))
    assert result.status == LocateStatus.INCONCLUSIVE
