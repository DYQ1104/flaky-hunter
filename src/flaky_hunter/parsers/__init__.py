"""Report parsers: JUnit XML and pytest-json-report."""

from __future__ import annotations

from pathlib import Path

from ..errors import ReportParseError
from ..models import TestResult
from .junit_xml import parse_junit_xml
from .pytest_json import parse_pytest_json


def load_report(path: Path | str, session_id: str, round_no: int) -> list[TestResult]:
    """Parse a report file, sniffing the format from its content."""
    report_path = Path(path)
    if not report_path.is_file():
        raise ReportParseError(f"报告文件不存在: {report_path}")
    text = report_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ReportParseError(f"报告文件为空: {report_path}")
    if text.lstrip().startswith("{"):
        return parse_pytest_json(report_path, session_id, round_no)
    return parse_junit_xml(report_path, session_id, round_no)


__all__ = ["load_report", "parse_junit_xml", "parse_pytest_json"]
