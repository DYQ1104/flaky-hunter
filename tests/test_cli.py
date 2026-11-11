import json
import sys
from pathlib import Path

import pytest

from flaky_hunter import __version__
from flaky_hunter.cli import (
    EXIT_ERROR,
    EXIT_FLAKY_FOUND,
    EXIT_NO_RUN,
    EXIT_OK,
    main,
)


def _write_report(path: Path, cases: list[tuple[str, str, str]]) -> Path:
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
            f'<testcase classname="{classname}" name="{name}">{child}</testcase>'
        )
    path.write_text(
        "<testsuites><testsuite>" + "".join(chunks) + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def _flaky_rounds(tmp_path: Path, rounds: int = 10) -> list[str]:
    paths: list[str] = []
    for round_no in range(1, rounds + 1):
        flaky = "failed" if round_no % 2 == 0 else "passed"
        path = tmp_path / f"round-{round_no}.xml"
        _write_report(
            path,
            [
                ("tests.test_flaky", "test_flaky", flaky),
                ("tests.test_stable", "test_stable", "passed"),
                ("tests.test_broken", "test_broken", "failed"),
            ],
        )
        paths.append(str(path))
    return paths


def test_analyze_json_contains_schema_and_summary(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)

    code = main(["analyze", *paths, "--format", "json"])

    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == "1.1"
    assert data["tool_version"] == __version__
    assert data["adapter"] == "pytest"
    assert data["summary"]["flaky"] == 1
    assert data["summary"]["broken"] == 1
    assert data["summary"]["stable"] == 1
    assert data["summary"]["skipped_tests"] == 0
    assert data["summary"]["rounds_ok"] == 10


def test_analyze_gate_returns_exit_code_two(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)

    code = main(["analyze", *paths, "--format", "json", "--fail-on-score", "100"])

    assert code == EXIT_FLAKY_FOUND
    capsys.readouterr()


def test_analyze_gate_is_off_by_default(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)

    code = main(["analyze", *paths, "--format", "json"])

    assert code == EXIT_OK
    capsys.readouterr()


def test_analyze_without_results_returns_three(tmp_path: Path, capsys):
    code = main(["analyze", str(tmp_path / "missing.xml")])

    assert code == EXIT_NO_RUN
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "没有可分析的测试结果" in err


def test_analyze_warns_but_continues_on_bad_report(tmp_path: Path, capsys):
    report = _write_report(
        tmp_path / "ok.xml", [("tests.test_a", "test_x", "passed")]
    )

    code = main(
        ["analyze", str(report), str(tmp_path / "missing.xml"), "--format", "json"]
    )

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "warning:" in captured.err
    data = json.loads(captured.out)
    assert len(data["rounds"]) == 2
    assert data["rounds"][0]["status"] == "ok"
    assert data["rounds"][1]["status"] == "invalid"
    assert data["summary"]["rounds_ok"] == 1


def test_baseline_suppresses_known_flaky(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "nodeid": "tests.test_flaky::test_flaky",
                        "classification": "flaky",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "analyze",
            *paths,
            "--format",
            "json",
            "--baseline",
            str(baseline),
            "--fail-on-score",
            "1",
        ]
    )

    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["suppressed_by_baseline"] == 1
    assert data["summary"]["flaky"] == 0
    assert data["summary"]["tests_total"] == 2


def test_ignore_drops_matching_tests(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)

    code = main(
        ["analyze", *paths, "--format", "json", "--ignore", "tests.test_flaky"]
    )

    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["flaky"] == 0
    assert data["summary"]["tests_total"] == 2


def test_analyze_cwd_enriches_nodeids(tmp_path: Path, capsys):
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_a.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    report = _write_report(
        tmp_path / "report.xml", [("tests.test_a", "test_x", "passed")]
    )

    code = main(
        ["analyze", str(report), "--cwd", str(project), "--format", "json"]
    )

    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["cwd"] == str(project)
    assert data["findings"][0]["nodeid"] == "tests/test_a.py::test_x"


def test_output_file_is_written(tmp_path: Path, capsys):
    paths = _flaky_rounds(tmp_path)
    target = tmp_path / "out" / "report.md"

    code = main(
        ["analyze", *paths, "--format", "markdown", "--output", str(target)]
    )

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert captured.out == ""
    assert "报告已写入" in captured.err
    text = target.read_text(encoding="utf-8")
    assert "flaky-hunter" in text
    assert "## Flaky tests" in text


def test_missing_config_returns_error(tmp_path: Path, capsys):
    code = main(
        ["analyze", "whatever.xml", "--config", str(tmp_path / "nope.toml")]
    )

    assert code == EXIT_ERROR
    assert "error:" in capsys.readouterr().err


def test_version_flag_exits_zero():
    with pytest.raises(SystemExit) as info:
        main(["--version"])

    assert info.value.code == 0


def test_run_with_command_template(tmp_path: Path, capsys):
    script = tmp_path / "emit.py"
    script.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text("
        "'<testsuites><testsuite><testcase classname=\"tests.t\" "
        "name=\"test_cmd\" /></testsuite></testsuites>', encoding='utf-8')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{script}" {{report}}'

    code = main(
        [
            "run",
            "-c",
            command,
            "--cwd",
            str(tmp_path),
            "-n",
            "2",
            "--no-locate",
            "--format",
            "json",
        ]
    )

    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["command"] == command
    assert len(data["rounds"]) == 2
    assert data["summary"]["rounds_ok"] == 2


def test_demo_smoke(capsys):
    code = main(["demo", "-n", "1", "--no-locate", "--no-color"])

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "OVERVIEW" in captured.out
    assert "示例仓库" in captured.err
