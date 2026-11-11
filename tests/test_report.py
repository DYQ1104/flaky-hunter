import json

import pytest

from flaky_hunter.models import (
    Classification,
    Finding,
    LocateResult,
    LocateStatus,
    ProbeEvidence,
    Report,
    RoundInfo,
    SessionSummary,
)
from flaky_hunter.report import markdown, render
from flaky_hunter.report import json_report


def _finding(
    nodeid: str,
    classification: Classification,
    attempts: int = 10,
    failures: int = 0,
    score: int = 0,
    root_cause: str = "",
    located=None,
) -> Finding:
    return Finding(
        nodeid=nodeid,
        classification=classification,
        attempts=attempts,
        failures=failures,
        score=score,
        pass_rate=(attempts - failures) / attempts,
        rounds_present=attempts,
        root_cause=root_cause,
        located=located,
    )


def _report(findings: list[Finding], skipped: int = 3) -> Report:
    counts = {bucket: 0 for bucket in Classification}
    for finding in findings:
        counts[finding.classification] += 1
    located = LocateResult(
        status=LocateStatus.FOUND,
        blockers=["tests/test_z.py::test_polluter"],
        probes_used=10,
        confidence="high",
        reproduce="python -m pytest -q tests/test_z.py::test_polluter tests/test_a.py::test_flaky",
        evidence=[ProbeEvidence(index=1, tests=["tests/test_z.py::test_polluter"], outcome="failed")],
    )
    findings[0].located = located
    summary = SessionSummary(
        rounds_total=10,
        rounds_ok=10,
        tests_total=len(findings),
        skipped_tests=skipped,
        flaky=counts[Classification.FLAKY],
        broken=counts[Classification.BROKEN],
        stable=counts[Classification.STABLE],
        insufficient=counts[Classification.INSUFFICIENT],
    )
    return Report(
        session_id="abc123",
        generated_at="2026-11-11T16:00:00+08:00",
        rounds=[RoundInfo(round=index) for index in range(1, 11)],
        findings=findings,
        summary=summary,
        adapter="pytest",
        tool_version="1.0.0",
        command="pytest -q --junitxml={report}",
        cwd="/tmp/project",
    )


def _sample_report() -> Report:
    return _report(
        [
            _finding(
                "tests/test_a.py::test_flaky",
                Classification.FLAKY,
                attempts=10,
                failures=5,
                score=96,
                root_cause="network",
            ),
            _finding(
                "tests/test_b.py::test_broken",
                Classification.BROKEN,
                attempts=10,
                failures=10,
            ),
            _finding("tests/test_c.py::test_stable", Classification.STABLE, attempts=10),
            _finding(
                "tests/test_d.py::test_few",
                Classification.INSUFFICIENT,
                attempts=2,
                failures=1,
                score=44,
            ),
        ]
    )


def test_json_contains_metadata_and_skipped():
    data = json_report.report_to_dict(_sample_report())

    assert data["schema_version"] == "1.1"
    assert data["tool_version"] == "1.0.0"
    assert data["command"] == "pytest -q --junitxml={report}"
    assert data["cwd"] == "/tmp/project"
    assert data["summary"]["skipped_tests"] == 3
    assert data["findings"][0]["classification"] == "flaky"
    assert data["findings"][0]["located"]["blockers"] == ["tests/test_z.py::test_polluter"]


def test_terminal_renders_all_sections():
    text = render(_sample_report(), "terminal")

    assert "OVERVIEW" in text
    assert "flaky 1" in text
    assert "skipped 3" in text
    assert "FLAKY TESTS" in text
    assert "LOCATED POLLUTERS" in text
    assert "BROKEN" in text
    assert "INSUFFICIENT" in text
    assert "test_polluter" in text
    assert "\x1b[" not in text


def test_markdown_renders_metadata_and_located():
    text = render(_sample_report(), "markdown")

    assert "flaky-hunter 1.0.0" in text
    assert "| skipped | 3 |" in text
    assert "## 定位结论" in text
    assert "tests/test_z.py::test_polluter" in text
    assert "```bash" in text


def test_markdown_without_flaky():
    report = _report(
        [_finding("tests/test_c.py::test_stable", Classification.STABLE, attempts=10)]
    )
    text = markdown.render(report)

    assert "未发现 flaky 用例。" in text
    assert "## Flaky tests" in text


def test_markdown_escapes_table_pipes():
    assert markdown._escape("a|b") == "a\\|b"


def test_unknown_format_raises():
    with pytest.raises(ValueError):
        render(_sample_report(), "xml")


def test_json_round_trips():
    text = render(_sample_report(), "json")
    data = json.loads(text)
    assert data["session_id"] == "abc123"
    assert len(data["rounds"]) == 10
