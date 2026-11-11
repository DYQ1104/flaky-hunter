import json
from pathlib import Path

import pytest

from flaky_hunter.errors import ReportParseError
from flaky_hunter.models import Outcome
from flaky_hunter.parsers import load_report, parse_junit_xml, parse_pytest_json

XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3">
    <testcase classname="tests.test_a" name="test_ok" time="0.010" />
    <testcase classname="tests.test_a" name="test_bad" time="0.500">
      <failure message="AssertionError: boom">trace line</failure>
    </testcase>
    <testcase classname="tests.test_a" name="test_skip" time="0">
      <skipped message="no database" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_outcomes(tmp_path: Path):
    report = tmp_path / "report.xml"
    report.write_text(XML, encoding="utf-8")
    results = parse_junit_xml(report, "s1", 1)

    assert [item.outcome for item in results] == [
        Outcome.PASSED,
        Outcome.FAILED,
        Outcome.SKIPPED,
    ]
    assert results[0].nodeid == "tests.test_a::test_ok"
    assert results[1].message == "AssertionError: boom"
    assert results[1].duration_ms == pytest.approx(500.0)


def test_junit_rejects_doctype(tmp_path: Path):
    report = tmp_path / "report.xml"
    report.write_text(
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "y">]><testsuites />',
        encoding="utf-8",
    )
    with pytest.raises(ReportParseError):
        parse_junit_xml(report, "s1", 1)


def test_parse_pytest_json(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "nodeid": "tests/test_a.py::test_ok",
                        "outcome": "passed",
                        "duration": 0.1,
                    },
                    {
                        "nodeid": "tests/test_a.py::test_bad",
                        "outcome": "failed",
                        "call": {
                            "longrepr": "AssertionError: boom",
                            "duration": 0.2,
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    results = parse_pytest_json(report, "s1", 2)
    assert results[0].outcome == Outcome.PASSED
    assert results[1].outcome == Outcome.FAILED
    assert results[1].round == 2
    assert results[1].duration_ms == pytest.approx(200.0)


def test_load_report_sniffs_json(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"tests": [{"nodeid": "a::b", "outcome": "passed"}]}),
        encoding="utf-8",
    )
    results = load_report(report, "s1", 1)
    assert results[0].nodeid == "a::b"


def test_empty_report_is_an_error(tmp_path: Path):
    report = tmp_path / "report.xml"
    report.write_text("   ", encoding="utf-8")
    with pytest.raises(ReportParseError):
        load_report(report, "s1", 1)
