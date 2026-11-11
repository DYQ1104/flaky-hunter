"""Analyze-only adapter for pre-existing JUnit XML reports."""

from __future__ import annotations

from pathlib import Path

from ..errors import AdapterError
from .base import RunnerAdapter


class JUnitAdapter(RunnerAdapter):
    """Reads reports produced elsewhere; cannot execute or locate."""

    name = "junit-xml"
    supports_locate = False

    def build_command(self, tests: list[str], report_path: Path) -> list[str]:
        raise AdapterError(
            "junit-xml adapter 只能分析已有报告（fh analyze），不支持执行与定位"
        )
