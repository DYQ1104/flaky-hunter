from flaky_hunter import __version__
from flaky_hunter.analyze import analyze
from flaky_hunter.config import Config
from flaky_hunter.models import (
    Classification,
    Outcome,
    RoundInfo,
    TestResult as Result,
)


def _rounds(count: int) -> list[RoundInfo]:
    return [RoundInfo(round=index) for index in range(1, count + 1)]


def _result(
    nodeid: str,
    round_no: int,
    outcome: Outcome,
    message: str = "",
    duration_ms: float = 0.0,
) -> Result:
    return Result(
        session_id="sess",
        round=round_no,
        nodeid=nodeid,
        outcome=outcome,
        message=message,
        duration_ms=duration_ms,
    )


def _mixed_results() -> list[Result]:
    order = [
        "tests/test_c.py::test_stable",
        "tests/test_a.py::test_flaky",
        "tests/test_b.py::test_broken",
        "tests/test_d.py::test_few",
        "tests/test_e.py::test_skipped",
    ]
    results: list[Result] = []
    for round_no in range(1, 11):
        for nodeid in order:
            if nodeid.endswith("test_stable"):
                outcome = Outcome.PASSED
            elif nodeid.endswith("test_flaky"):
                outcome = (
                    Outcome.FAILED if round_no % 2 == 0 else Outcome.PASSED
                )
            elif nodeid.endswith("test_broken"):
                outcome = Outcome.FAILED
            elif nodeid.endswith("test_few"):
                outcome = Outcome.PASSED if round_no == 1 else Outcome.FAILED
                if round_no > 2:
                    continue
            else:
                outcome = Outcome.SKIPPED
            results.append(
                _result(
                    nodeid,
                    round_no,
                    outcome,
                    message=(
                        "ConnectionError: ECONNREFUSED"
                        if outcome == Outcome.FAILED
                        else ""
                    ),
                    duration_ms=10.0,
                )
            )
    return results


def test_classification_summary_and_order():
    report = analyze(_mixed_results(), _rounds(10), "sess", Config())

    summary = report.summary
    assert summary.tests_total == 4
    assert summary.skipped_tests == 1
    assert summary.flaky == 1
    assert summary.broken == 1
    assert summary.stable == 1
    assert summary.insufficient == 1
    assert summary.rounds_total == 10
    assert summary.rounds_ok == 10

    assert [finding.classification for finding in report.findings] == [
        Classification.FLAKY,
        Classification.BROKEN,
        Classification.INSUFFICIENT,
        Classification.STABLE,
    ]
    flaky = report.findings[0]
    assert flaky.nodeid == "tests/test_a.py::test_flaky"
    assert flaky.attempts == 10
    assert flaky.failures == 5
    assert flaky.score == 100
    assert flaky.pass_rate == 0.5
    assert flaky.root_cause == "network"
    assert flaky.duration_avg_ms == 10.0


def test_ordered_tests_use_first_round_and_keep_skipped():
    report = analyze(_mixed_results(), _rounds(10), "sess", Config())

    assert report.ordered_tests == [
        "tests/test_c.py::test_stable",
        "tests/test_a.py::test_flaky",
        "tests/test_b.py::test_broken",
        "tests/test_d.py::test_few",
        "tests/test_e.py::test_skipped",
    ]


def test_report_metadata_is_reproducible():
    config = Config()

    report = analyze(
        _mixed_results(),
        _rounds(10),
        "sess",
        config,
        adapter="pytest",
        command="python -m pytest -q --junitxml={report}",
        cwd="/tmp/project",
    )

    assert report.tool_version == __version__
    assert report.schema_version == "1.1"
    assert report.adapter == "pytest"
    assert report.command == "python -m pytest -q --junitxml={report}"
    assert report.cwd == "/tmp/project"
    assert report.config_snapshot["run"]["rounds"] == 10
    assert "source_path" not in report.config_snapshot


def test_ignored_tests_are_dropped_but_stay_in_order():
    config = Config()
    config.analysis.ignore = ["tests/test_ignored.py"]
    results = [
        _result("tests/test_ignored.py::test_x", round_no, Outcome.PASSED)
        for round_no in range(1, 6)
    ]

    report = analyze(results, _rounds(5), "sess", config)

    assert report.findings == []
    assert report.summary.tests_total == 0
    assert report.ordered_tests == ["tests/test_ignored.py::test_x"]


def test_only_skipped_results_produce_empty_report():
    results = [
        _result("tests/test_s.py::test_skip", round_no, Outcome.SKIPPED)
        for round_no in range(1, 4)
    ]

    report = analyze(results, _rounds(3), "sess", Config())

    assert report.findings == []
    assert report.summary.skipped_tests == 1
    assert report.summary.tests_total == 0
    assert report.summary.flaky == 0


def test_empty_input_is_safe():
    report = analyze([], [], "sess", Config())

    assert report.findings == []
    assert report.ordered_tests == []
    assert report.summary.rounds_total == 0
    assert report.summary.tests_total == 0
