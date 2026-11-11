"""Multi-round execution orchestration."""

from __future__ import annotations

import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .adapters.base import base_env, run_process, split_command
from .config import Config
from .errors import ConfigError, ReportParseError
from .models import RoundInfo, RoundStatus, TestResult
from .parsers import load_report

ProgressFn = Callable[[int, int], None]

_MISSING_REPORT_HINT = "命令模板必须包含 {report} 占位符"


@dataclass
class RunSession:
    session_id: str
    workdir: Path
    rounds: list[RoundInfo] = field(default_factory=list)
    results: list[TestResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    truncated: bool = False

    @property
    def valid_rounds(self) -> list[RoundInfo]:
        return [
            item
            for item in self.rounds
            if item.status in (RoundStatus.OK, RoundStatus.TIMEOUT)
        ]


def new_session_id() -> str:
    return uuid.uuid4().hex[:6]


def materialize_command(template: str, report_path: Path, round_no: int) -> str:
    if "{report}" not in template:
        raise ConfigError(_MISSING_REPORT_HINT)
    path = str(report_path)
    if " " in path:
        path = f'"{path}"'
    return template.replace("{report}", path).replace("{round}", str(round_no))


def execute(
    config: Config,
    adapter,
    session_id: Optional[str] = None,
    progress: Optional[ProgressFn] = None,
) -> RunSession:
    session_id = session_id or new_session_id()
    workdir = Path(tempfile.mkdtemp(prefix=f"flaky-hunter-{session_id}-"))
    session = RunSession(session_id=session_id, workdir=workdir)
    started = time.perf_counter()

    if config.run.command and "{report}" not in config.run.command:
        raise ConfigError(_MISSING_REPORT_HINT)

    for round_no in range(1, config.run.rounds + 1):
        elapsed = time.perf_counter() - started
        if elapsed > config.run.max_rounds_seconds:
            session.truncated = True
            break

        if progress is not None:
            progress(round_no, config.run.rounds)

        report_path = workdir / f"round-{round_no}.xml"
        env = base_env(session_id, round_no)
        round_started = time.perf_counter()

        if config.run.command:
            command = materialize_command(
                config.run.command, report_path, round_no
            )
            exit_code, stdout, stderr, timed_out = run_process(
                split_command(command),
                adapter.cwd,
                config.run.timeout_per_round,
                env,
            )
        else:
            outcome = adapter.execute(
                [],
                report_path,
                session_id=session_id,
                round_no=round_no,
                timeout=config.run.timeout_per_round,
            )
            exit_code = 0 if outcome.passed else 1
            stdout = stderr = outcome.message
            timed_out = outcome.outcome == "timeout"

        duration_ms = (time.perf_counter() - round_started) * 1000.0
        info = RoundInfo(
            round=round_no,
            status=RoundStatus.TIMEOUT if timed_out else RoundStatus.OK,
            report_path=str(report_path),
            duration_ms=duration_ms,
            exit_code=None if timed_out else exit_code,
        )

        try:
            session.results.extend(
                load_report(report_path, session_id, round_no)
            )
        except ReportParseError as exc:
            info.error = str(exc)
            if not timed_out:
                info.status = RoundStatus.INVALID
        finally:
            if info.status == RoundStatus.INVALID and not info.error:
                info.error = (stderr or stdout).strip()[-300:]

        session.rounds.append(info)
        if config.run.delay:
            time.sleep(config.run.delay)

    session.total_duration_ms = (time.perf_counter() - started) * 1000.0
    return session
