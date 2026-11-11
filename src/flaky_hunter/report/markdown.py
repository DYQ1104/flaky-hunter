"""Markdown renderer, meant to be pasted into a PR or a weekly report."""

from __future__ import annotations

from ..models import Classification, LocateStatus, Report


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def render(report: Report) -> str:
    summary = report.summary
    lines: list[str] = []
    lines.append(f"# flaky-hunter report `{report.session_id}`")
    lines.append("")
    lines.append(f"- 工具: **flaky-hunter {report.tool_version}**")
    lines.append(
        f"- 轮次: **{summary.rounds_ok}/{summary.rounds_total}**"
        f"　用例数: **{summary.tests_total}**"
        f"　adapter: `{report.adapter}`"
    )
    lines.append(f"- 生成时间: `{report.generated_at}`")
    if report.cwd:
        lines.append(f"- 执行目录: `{_escape(report.cwd)}`")
    if report.command:
        lines.append(f"- 执行命令: `{_escape(report.command)}`")
    lines.append("")
    lines.append("| 分类 | 数量 |")
    lines.append("| --- | ---: |")
    lines.append(f"| flaky | {summary.flaky} |")
    lines.append(f"| broken | {summary.broken} |")
    lines.append(f"| stable | {summary.stable} |")
    lines.append(f"| insufficient | {summary.insufficient} |")
    lines.append(f"| skipped | {summary.skipped_tests} |")
    lines.append("")

    flaky = [f for f in report.findings if f.classification == Classification.FLAKY]
    lines.append("## Flaky tests")
    lines.append("")
    if flaky:
        lines.append("| # | score | 失败/执行 | 根因 | 用例 |")
        lines.append("| ---: | ---: | --- | --- | --- |")
        for index, finding in enumerate(flaky, start=1):
            lines.append(
                f"| {index} | {finding.score} | {finding.failures}/{finding.attempts}"
                f" | {finding.root_cause or '-'} | `{_escape(finding.nodeid)}` |"
            )
    else:
        lines.append("未发现 flaky 用例。")
    lines.append("")

    located = [
        f
        for f in report.findings
        if f.located is not None
        and f.located.status
        in (
            LocateStatus.FOUND,
            LocateStatus.PARTIAL,
            LocateStatus.UNSTABLE_EVIDENCE,
            LocateStatus.ABORTED,
        )
    ]
    if located:
        lines.append("## 定位结论")
        lines.append("")
        for finding in located:
            info = finding.located
            assert info is not None
            lines.append(f"### `{_escape(finding.nodeid)}`")
            lines.append("")
            lines.append(
                f"- 状态: **{info.status.value}**"
                f"　probes: {info.probes_used}"
                f"　置信度: {info.confidence}"
            )
            if info.blockers:
                lines.append("- 污染源:")
                for blocker in info.blockers:
                    lines.append(f"  - `{_escape(blocker)}`")
            if info.note:
                lines.append(f"- 说明: {info.note}")
            if info.reproduce:
                lines.append("")
                lines.append("```bash")
                lines.append(info.reproduce)
                lines.append("```")
            lines.append("")

    broken = [f for f in report.findings if f.classification == Classification.BROKEN]
    if broken:
        lines.append("## Broken tests（100% 失败）")
        lines.append("")
        for finding in broken:
            suffix = ""
            if finding.located is not None:
                if finding.located.status == LocateStatus.FOUND:
                    suffix = " — 顺序依赖"
                else:
                    suffix = " — 单独执行也失败"
            lines.append(
                f"- `{_escape(finding.nodeid)}`"
                f" ({finding.failures}/{finding.attempts}){suffix}"
            )
        lines.append("")

    warnings = [item for item in report.rounds if item.status.value != "ok"]
    if warnings:
        lines.append("## 执行告警")
        lines.append("")
        for item in warnings:
            text = f"- round {item.round}: **{item.status.value}**"
            if item.error:
                text += f" — {item.error[:200]}"
            lines.append(text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
