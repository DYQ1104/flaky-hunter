"""Runner adapter: the contract that lets locate work across frameworks."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..errors import AdapterError, ReportParseError
from ..models import Outcome, ProbeOutcome
from ..parsers import load_report

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def base_env(session_id: str = "", round_no: Optional[int] = None) -> dict[str, str]:
    """Environment handed to every child process.

    ``FH_SESSION_ID`` and ``FH_ROUND`` are stable hooks that demo fixtures (and
    users) can rely on to make failures deterministic.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if session_id:
        env["FH_SESSION_ID"] = session_id
    if round_no is not None:
        env["FH_ROUND"] = str(round_no)
    return env


def split_command(command: str) -> list[str]:
    if os.name == "nt":
        return [arg.strip('"') for arg in shlex.split(command, posix=False)]
    return shlex.split(command)


def quote_arg(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        return
    try:
        proc.terminate()
    except ProcessLookupError:  # pragma: no cover - race with process exit
        pass


def run_process(
    args: list[str] | str,
    cwd: Path | str,
    timeout: float,
    env: Optional[dict[str, str]] = None,
    shell: bool = False,
) -> tuple[int, str, str, bool]:
    """Run a child process and never raise on non-zero exit.

    Returns ``(exit_code, stdout, stderr, timed_out)``.
    """
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            shell=shell,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        raise AdapterError(f"无法启动子进程: {exc}") from exc

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
            proc.kill()
            out, err = "", ""
    return proc.returncode or 0, out or "", err or "", timed_out


class RunnerAdapter(ABC):
    name = "base"
    supports_locate = False

    def __init__(self, cwd: Path | str = ".", timeout: float = 300.0) -> None:
        self.cwd = Path(cwd).resolve()
        self.timeout = timeout

    @abstractmethod
    def build_command(self, tests: list[str], report_path: Path) -> list[str]:
        """Return argv for running ``tests`` (empty means the whole suite)."""

    def list_tests(self) -> list[str]:
        raise AdapterError(f"adapter {self.name!r} 不支持枚举用例，无法执行定位")

    def nodeid_map(self) -> dict[str, str]:
        """Map parser keys (classname::name) to executable nodeids."""
        return {}

    def render_reproduce(self, tests: list[str]) -> str:
        return " ".join(quote_arg(item) for item in tests)

    def result_key(self, nodeid: str) -> str:
        """Convert a nodeid to the key produced by the report parser."""
        return nodeid

    def execute(
        self,
        tests: list[str],
        report_path: Path,
        session_id: str = "probe",
        round_no: int = 1,
        timeout: Optional[float] = None,
        target: Optional[str] = None,
    ) -> ProbeOutcome:
        """Run a subset of tests and report the outcome.

        When ``target`` is given the verdict is based on *that test's* result,
        not on the process exit code: a probe subset may contain other failing
        tests, and their failure must not be mistaken for the target's.
        """
        command = self.build_command(tests, report_path)
        started = time.perf_counter()
        try:
            code, out, err, timed_out = run_process(
                command,
                self.cwd,
                timeout if timeout is not None else self.timeout,
                base_env(session_id, round_no),
            )
        except AdapterError as exc:
            return ProbeOutcome("invalid", 0.0, str(exc))
        duration_ms = (time.perf_counter() - started) * 1000.0

        if timed_out:
            return ProbeOutcome("timeout", duration_ms, "命令超时")
        if not Path(report_path).is_file():
            tail = (err or out).strip().splitlines()[-1:] or [""]
            return ProbeOutcome("invalid", duration_ms, tail[0][:500])
        if target is None:
            return ProbeOutcome(
                "passed" if code == 0 else "failed",
                duration_ms,
                (err or out).strip()[-500:],
            )

        try:
            results = load_report(report_path, session_id, round_no)
        except ReportParseError as exc:
            return ProbeOutcome("invalid", duration_ms, str(exc)[:300])

        key = self.result_key(target)
        for item in results:
            if item.nodeid != key:
                continue
            if item.outcome == Outcome.PASSED:
                return ProbeOutcome("passed", duration_ms, "")
            if item.outcome == Outcome.SKIPPED:
                return ProbeOutcome("invalid", duration_ms, "目标用例被跳过")
            return ProbeOutcome(
                item.outcome.value, duration_ms, (item.message or "")[:300]
            )
        return ProbeOutcome(
            "invalid", duration_ms, f"探针报告中未找到目标用例: {key}"
        )

    def describe(self) -> str:
        return f"{self.name} (cwd={self.cwd})"


def python_executable() -> str:
    return sys.executable or "python"
