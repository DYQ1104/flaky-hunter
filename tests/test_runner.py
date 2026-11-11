from __future__ import annotations

import sys
from pathlib import Path

import pytest

from flaky_hunter.config import Config
from flaky_hunter.errors import ConfigError
from flaky_hunter.models import ProbeOutcome, RoundStatus
from flaky_hunter.runner import execute, materialize_command


def _junit(cases: list[tuple[str, str, str]]) -> str:
    chunks = []
    for classname, name, outcome in cases:
        child = ""
        if outcome == "failed":
            child = '<failure message="boom">trace</failure>'
        elif outcome == "error":
            child = '<error message="kaboom">trace</error>'
        elif outcome == "skipped":
            child = "<skipped/>"
        chunks.append(
            f'<testcase classname="{classname}" name="{name}" time="0.01">'
            f"{child}</testcase>"
        )
    return "<testsuites><testsuite>" + "".join(chunks) + "</testsuite></testsuites>"


class FakeAdapter:
    name = "fake"

    def __init__(
        self,
        cwd: Path,
        payload: str | None = None,
        outcome: ProbeOutcome | None = None,
    ) -> None:
        self.cwd = cwd
        self.payload = payload
        self.outcome = outcome or ProbeOutcome("passed")
        self.calls: list[list[str]] = []

    def execute(
        self,
        tests,
        report_path,
        session_id="probe",
        round_no=1,
        timeout=None,
        target=None,
    ):
        self.calls.append(list(tests))
        if self.payload is not None:
            Path(report_path).write_text(self.payload, encoding="utf-8")
        return self.outcome


def test_materialize_command_requires_report_placeholder():
    with pytest.raises(ConfigError, match="report"):
        materialize_command("pytest -q", Path("report.xml"), 1)


def test_materialize_command_substitutes_round_and_quotes_path(tmp_path: Path):
    path = tmp_path / "with space" / "report.xml"

    command = materialize_command(
        "pytest -q --junitxml={report} --round={round}", path, 2
    )

    assert "--round=2" in command
    assert '"' in command
    assert "with space" in command


def test_execute_collects_every_round(tmp_path: Path):
    config = Config()
    config.run.rounds = 3
    config.run.timeout_per_round = 10
    adapter = FakeAdapter(
        tmp_path,
        payload=_junit(
            [
                ("tests.test_a", "test_ok", "passed"),
                ("tests.test_a", "test_bad", "failed"),
            ]
        ),
    )

    session = execute(config, adapter, session_id="abc")

    assert len(session.rounds) == 3
    assert all(item.status == RoundStatus.OK for item in session.rounds)
    assert len(session.valid_rounds) == 3
    assert len(session.results) == 6
    assert {item.round for item in session.results} == {1, 2, 3}
    assert session.truncated is False
    assert adapter.calls == [[], [], []]


def test_execute_marks_missing_report_invalid(tmp_path: Path):
    config = Config()
    config.run.rounds = 2
    adapter = FakeAdapter(tmp_path, payload=None)

    session = execute(config, adapter)

    assert session.results == []
    assert [item.status for item in session.rounds] == [
        RoundStatus.INVALID,
        RoundStatus.INVALID,
    ]
    assert "报告文件不存在" in session.rounds[0].error


def test_execute_keeps_timeout_status(tmp_path: Path):
    config = Config()
    config.run.rounds = 1
    adapter = FakeAdapter(
        tmp_path, payload=None, outcome=ProbeOutcome("timeout", 0.0, "命令超时")
    )

    session = execute(config, adapter)

    assert session.rounds[0].status == RoundStatus.TIMEOUT
    assert session.rounds[0].exit_code is None
    assert session.results == []


def test_execute_stops_when_time_budget_is_exhausted(tmp_path: Path):
    config = Config()
    config.run.rounds = 5
    config.run.max_rounds_seconds = -1
    adapter = FakeAdapter(tmp_path, payload=_junit([("tests.test_a", "test_ok", "passed")]))

    session = execute(config, adapter)

    assert session.truncated is True
    assert session.rounds == []
    assert session.results == []


def test_execute_runs_command_template(tmp_path: Path):
    script = tmp_path / "emit.py"
    script.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text("
        "'<testsuites><testsuite><testcase classname=\"tests.t\" "
        "name=\"test_cmd\" /></testsuite></testsuites>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    config = Config()
    config.run.rounds = 1
    config.run.command = (
        f'"{sys.executable}" "{script}" {{report}}'
    )
    adapter = FakeAdapter(tmp_path)

    session = execute(config, adapter)

    assert adapter.calls == []
    assert session.rounds[0].status == RoundStatus.OK
    assert [item.nodeid for item in session.results] == ["tests.t::test_cmd"]


def test_execute_rejects_template_without_report(tmp_path: Path):
    config = Config()
    config.run.rounds = 1
    config.run.command = "pytest -q"
    adapter = FakeAdapter(tmp_path)

    with pytest.raises(ConfigError, match="report"):
        execute(config, adapter)
