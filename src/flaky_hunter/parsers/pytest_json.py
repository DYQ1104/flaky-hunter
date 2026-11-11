"""Parser for the ``pytest-json-report`` plugin output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import ReportParseError
from ..models import Outcome, TestResult

_OUTCOME_MAP = {
    "passed": Outcome.PASSED,
    "failed": Outcome.FAILED,
    "error": Outcome.ERROR,
    "skipped": Outcome.SKIPPED,
    "xfailed": Outcome.SKIPPED,
    "xpassed": Outcome.PASSED,
}


def _longrepr(test: dict[str, Any]) -> str:
    for phase in ("call", "setup", "teardown"):
        node = test.get(phase)
        if isinstance(node, dict):
            longrepr = node.get("longrepr")
            if isinstance(longrepr, str) and longrepr.strip():
                return longrepr.strip()
    return ""


def _duration_ms(test: dict[str, Any]) -> float:
    raw = test.get("duration")
    if raw is None:
        call = test.get("call")
        if isinstance(call, dict):
            raw = call.get("duration")
    try:
        return float(raw) * 1000.0
    except (TypeError, ValueError):
        return 0.0


def parse_pytest_json(
    path: Path | str, session_id: str, round_no: int
) -> list[TestResult]:
    report_path = Path(path)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        raise ReportParseError(f"无法读取报告 {report_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReportParseError(
            f"JSON 解析失败 {report_path.name}: {exc}"
        ) from exc

    tests = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(tests, list):
        raise ReportParseError(
            f"报告 {report_path.name} 缺少 tests 数组（需要 pytest-json-report 产物）"
        )

    results: list[TestResult] = []
    seen: dict[str, int] = {}
    for item in tests:
        if not isinstance(item, dict):
            continue
        nodeid = str(item.get("nodeid") or "").strip()
        if not nodeid:
            continue
        raw_outcome = str(item.get("outcome") or "").lower()
        outcome = _OUTCOME_MAP.get(raw_outcome, Outcome.FAILED)
        trace = _longrepr(item)
        message = trace.splitlines()[0].strip()[:300] if trace else ""

        if nodeid in seen:
            seen[nodeid] += 1
            nodeid = f"{nodeid}#{seen[nodeid]}"
        else:
            seen[nodeid] = 1

        results.append(
            TestResult(
                session_id=session_id,
                round=round_no,
                nodeid=nodeid,
                outcome=outcome,
                duration_ms=_duration_ms(item),
                message=message,
                trace=trace,
            )
        )

    if not results:
        raise ReportParseError(f"报告 {report_path.name} 中没有有效用例记录")
    return results
