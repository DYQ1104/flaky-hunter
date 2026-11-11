"""Terminal renderer."""

from __future__ import annotations

import os
import sys

from .. import __version__
from ..models import Classification, LocateStatus, Report

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"{_ANSI[code]}{text}{_ANSI['reset']}"

    def bold(self, text: str) -> str:
        return self._wrap("bold", text)

    def dim(self, text: str) -> str:
        return self._wrap("dim", text)

    def red(self, text: str) -> str:
        return self._wrap("red", text)

    def green(self, text: str) -> str:
        return self._wrap("green", text)

    def yellow(self, text: str) -> str:
        return self._wrap("yellow", text)

    def cyan(self, text: str) -> str:
        return self._wrap("cyan", text)


def color_enabled(force: bool = False) -> bool:
    if force:
        return True
    if os.environ.get("NO_COLOR"):
        return False
    stream = sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def _score_color(palette: Palette, score: int) -> str:
    text = f"{score:>3}"
    if score >= 60:
        return palette.red(text)
    if score >= 30:
        return palette.yellow(text)
    return palette.green(text)


def _cause_color(palette: Palette, cause: str) -> str:
    if cause == "order-dependent":
        return palette.cyan(cause)
    if cause in ("unknown", ""):
        return palette.dim(cause or "-")
    return cause


def render(report: Report, color: bool = False) -> str:
    palette = Palette(color)
    lines: list[str] = []
    summary = report.summary

    total_ms = sum(item.duration_ms for item in report.rounds)
    lines.append(
        palette.bold(f"flaky-hunter {__version__}")
        + palette.dim(f"  ·  session {report.session_id}  ·  adapter {report.adapter}")
    )
    lines.append(
        f"Rounds: {summary.rounds_ok}/{summary.rounds_total}"
        f"   Tests: {summary.tests_total}"
        f"   Duration: {total_ms / 1000.0:.1f}s"
    )
    lines.append("")

    lines.append(palette.bold("OVERVIEW"))
    overview = (
        f"  flaky {summary.flaky}"
        f"   broken {summary.broken}"
        f"   stable {summary.stable}"
        f"   insufficient {summary.insufficient}"
    )
    if summary.suppressed_by_baseline:
        overview += f"   (baseline suppressed: {summary.suppressed_by_baseline})"
    if summary.skipped_tests:
        overview += f"   skipped {summary.skipped_tests}"
    lines.append(overview)
    lines.append("")

    flaky = [f for f in report.findings if f.classification == Classification.FLAKY]
    if flaky:
        lines.append(palette.bold("FLAKY TESTS (by score)"))
        width = max(len(f.nodeid) for f in flaky)
        width = min(max(width, 20), 70)
        lines.append(
            palette.dim(
                f"  {'#':>2}  {'SCORE':>5}  {'RATE':>7}  {'ROOT CAUSE':<18}  TEST"
            )
        )
        for index, finding in enumerate(flaky, start=1):
            rate = f"{finding.failures}/{finding.attempts}"
            cause = _cause_color(palette, finding.root_cause)
            lines.append(
                f"  {index:>2}  {_score_color(palette, finding.score)}"
                f"  {rate:>7}  {cause:<18}  {finding.nodeid}"
            )
        lines.append("")

    shown_statuses = {
        LocateStatus.FOUND,
        LocateStatus.PARTIAL,
        LocateStatus.UNSTABLE_EVIDENCE,
        LocateStatus.ABORTED,
    }
    located = [
        finding
        for finding in report.findings
        if finding.located is not None and finding.located.status in shown_statuses
    ]
    inconclusive = [
        finding
        for finding in report.findings
        if finding.located is not None and finding.located.status not in shown_statuses
    ]
    if located:
        lines.append(palette.bold("LOCATED POLLUTERS"))
        for finding in located:
            located_info = finding.located
            assert located_info is not None
            status = located_info.status.value
            if located_info.status == LocateStatus.FOUND:
                headline = palette.red(status)
            elif located_info.status in (
                LocateStatus.PARTIAL,
                LocateStatus.UNSTABLE_EVIDENCE,
            ):
                headline = palette.yellow(status)
            else:
                headline = palette.dim(status)
            lines.append(f"  {finding.nodeid}")
            lines.append(
                f"    status: {headline}"
                f"  probes: {located_info.probes_used}"
                f"  confidence: {located_info.confidence}"
            )
            for blocker in located_info.blockers:
                lines.append(f"    {palette.cyan('<-')} {blocker}")
            if located_info.note:
                lines.append(palette.dim(f"    note: {located_info.note}"))
            if located_info.reproduce:
                lines.append(palette.dim("    reproduce:"))
                lines.append(f"      {located_info.reproduce}")
        lines.append("")
    if inconclusive:
        names = ", ".join(finding.nodeid for finding in inconclusive)
        lines.append(palette.dim(f"locate inconclusive: {names}"))
        lines.append("")

    broken = [f for f in report.findings if f.classification == Classification.BROKEN]
    if broken:
        lines.append(palette.bold("BROKEN (100% failed — fix these first)"))
        for finding in broken:
            hint = ""
            if finding.located is not None and finding.located.status == LocateStatus.FOUND:
                hint = "  -> 顺序依赖，见 LOCATED POLLUTERS"
            elif finding.located is not None:
                hint = "  -> 单独执行同样失败，是真实缺陷"
            lines.append(
                f"  {finding.nodeid}   {finding.failures}/{finding.attempts}{hint}"
            )
        lines.append("")

    insufficient = [
        f for f in report.findings if f.classification == Classification.INSUFFICIENT
    ]
    if insufficient:
        lines.append(palette.bold("INSUFFICIENT (too few rounds to judge)"))
        for finding in insufficient:
            lines.append(
                f"  {finding.nodeid}   {finding.attempts} attempts"
                f" (need >= {report.config_snapshot.get('analysis', {}).get('min_attempts', 5)})"
            )
        lines.append("")

    problems = [r for r in report.rounds if r.status.value not in ("ok",)]
    if problems:
        lines.append(palette.bold("ROUND WARNINGS"))
        for item in problems:
            detail = f"  round {item.round}: {item.status.value}"
            if item.error:
                detail += f" — {item.error[:160]}"
            lines.append(palette.yellow(detail))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
