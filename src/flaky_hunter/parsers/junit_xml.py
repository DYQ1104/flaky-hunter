"""JUnit XML parser.

Supports the subset emitted by pytest, JUnit 5, Maven Surefire and Go test
tooling: ``<testsuites>``/``<testsuite>`` > ``<testcase>`` with optional
``<failure>``, ``<error>`` and ``<skipped>`` children.

The XML is rejected when a DOCTYPE declaration is present, which removes the
XXE attack surface without pulling in a third-party parser.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..errors import ReportParseError
from ..models import Outcome, TestResult

_DOCTYPE = re.compile(r"<!DOCTYPE", re.IGNORECASE)


def _to_float(raw: str | None) -> float:
    if not raw:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:300]
    return ""


def parse_junit_xml(
    path: Path | str, session_id: str, round_no: int
) -> list[TestResult]:
    report_path = Path(path)
    try:
        raw = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ReportParseError(f"无法读取报告 {report_path}: {exc}") from exc

    if _DOCTYPE.search(raw[:4096]):
        raise ReportParseError(
            f"报告 {report_path.name} 含 DOCTYPE 声明，已拒绝解析（避免 XXE）"
        )
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ReportParseError(f"XML 解析失败 {report_path.name}: {exc}") from exc

    results: list[TestResult] = []
    seen: dict[str, int] = {}

    for case in root.iter("testcase"):
        name = (case.get("name") or "").strip()
        if not name:
            continue
        classname = (case.get("classname") or "").strip()
        nodeid = f"{classname}::{name}" if classname else name

        outcome = Outcome.PASSED
        message = ""
        trace = ""
        for child in case:
            tag = child.tag
            if tag in ("failure", "error"):
                outcome = Outcome.FAILED if tag == "failure" else Outcome.ERROR
                trace = (child.text or "").strip()
                message = (child.get("message") or "").strip() or _first_line(trace)
                break
            if tag == "skipped":
                outcome = Outcome.SKIPPED
                message = (child.get("message") or "").strip() or _first_line(
                    child.text or ""
                )
                break

        # Parametrized ids are already unique; this only guards against writers
        # that duplicate a testcase entry.
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
                suite=classname,
                outcome=outcome,
                duration_ms=_to_float(case.get("time")) * 1000.0,
                message=message,
                trace=trace,
            )
        )

    if not results:
        raise ReportParseError(f"报告 {report_path.name} 中没有 testcase 记录")
    return results
