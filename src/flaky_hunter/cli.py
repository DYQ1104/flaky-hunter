"""Command line interface."""

from __future__ import annotations

import argparse
import glob
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import __version__
from .adapters import make_adapter
from .analyze import analyze
from .config import Config, load_config, validate
from .errors import FlakyHunterError, ReportParseError
from .locate import ProbeBudget, locate_polluters, select_targets
from .models import Classification, LocateStatus, Report, RoundInfo, RoundStatus
from .parsers import load_report
from .report import color_enabled, json_report, render
from .runner import execute, new_session_id

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FLAKY_FOUND = 2
EXIT_NO_RUN = 3


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="配置文件路径，默认向上查找 .flaky-hunter.toml")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印每轮执行详情")


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "markdown"],
        help="报告输出格式，默认 terminal",
    )
    parser.add_argument("--output", help="把报告写入文件")
    parser.add_argument(
        "--fail-on-score",
        type=int,
        help="存在评分 >= 该值的 flaky 用例时以退出码 2 结束（0 表示关闭）",
    )
    parser.add_argument("--baseline", help="基线报告（json），只报告新增问题")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fh",
        description="检测、排序并定位 flaky test。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run = subparsers.add_parser("run", help="执行多轮测试并完整分析")
    run.add_argument("-c", "--command", help="命令模板，必须包含 {report}")
    run.add_argument("-n", "--rounds", type=int, help="执行轮数")
    run.add_argument("--adapter", choices=["pytest", "junit-xml"], help="runner adapter")
    run.add_argument("--cwd", help="测试执行目录")
    run.add_argument("--timeout-per-round", type=float, help="单轮超时（秒）")
    run.add_argument("--top-n", type=int, help="定位多少个候选用例")
    run.add_argument("--no-locate", action="store_true", help="跳过污染源定位")
    run.add_argument("--ignore", action="append", help="忽略的用例路径 glob，可多次指定")
    _add_output_options(run)
    _add_common_options(run)

    analyze_parser = subparsers.add_parser(
        "analyze", help="只分析已有报告，不执行测试"
    )
    analyze_parser.add_argument("reports", nargs="+", help="报告文件或 glob")
    analyze_parser.add_argument(
        "--adapter", choices=["pytest", "junit-xml"], help="报告来源，仅用于展示"
    )
    analyze_parser.add_argument(
        "--cwd",
        help="测试项目目录：提供时用 pytest 收集结果补全可执行 nodeid",
    )
    analyze_parser.add_argument("--ignore", action="append", help="忽略的用例路径 glob")
    _add_output_options(analyze_parser)
    _add_common_options(analyze_parser)

    locate = subparsers.add_parser("locate", help="对单个用例做顺序依赖定位")
    locate.add_argument("target", help="目标用例 nodeid")
    locate.add_argument("--cwd", help="测试执行目录")
    locate.add_argument("--timeout-per-probe", type=float, help="单次 probe 超时（秒）")
    locate.add_argument("--max-probes", type=int, help="probe 总预算")
    locate.add_argument("--confirm-runs", type=int, help="结论复核次数")
    locate.add_argument("--baseline-runs", type=int, help="单独执行的基线次数")
    locate.add_argument("--ignore", action="append", help="忽略的用例路径 glob")
    _add_common_options(locate)

    demo = subparsers.add_parser("demo", help="运行内置示例并输出完整报告")
    demo.add_argument("-n", "--rounds", type=int, default=10, help="演示轮数，默认 10")
    demo.add_argument("--no-locate", action="store_true", help="跳过污染源定位")
    _add_common_options(demo)

    return parser


def _cfg_start(args: argparse.Namespace) -> str:
    return getattr(args, "cwd", None) or "."


def _apply_overrides(config: Config, args: argparse.Namespace) -> None:
    if getattr(args, "command", None):
        config.run.command = args.command
    if getattr(args, "rounds", None) is not None:
        config.run.rounds = args.rounds
    if getattr(args, "adapter", None):
        config.run.adapter = args.adapter
    if getattr(args, "cwd", None):
        config.run.cwd = args.cwd
    if getattr(args, "timeout_per_round", None) is not None:
        config.run.timeout_per_round = args.timeout_per_round
    if getattr(args, "format", None):
        config.output.format = args.format
    if getattr(args, "output", None):
        config.output.path = args.output
    if getattr(args, "fail_on_score", None) is not None:
        config.ci.fail_on_score = args.fail_on_score
    if getattr(args, "top_n", None) is not None:
        config.locate.top_n = args.top_n
    if getattr(args, "no_locate", False):
        config.locate.enabled = False
    if getattr(args, "ignore", None):
        config.analysis.ignore = list(args.ignore)
    if getattr(args, "timeout_per_probe", None) is not None:
        config.locate.timeout_per_probe = args.timeout_per_probe
    if getattr(args, "max_probes", None) is not None:
        config.locate.max_probe_total = args.max_probes
    if getattr(args, "confirm_runs", None) is not None:
        config.locate.confirm_runs = args.confirm_runs
    if getattr(args, "baseline_runs", None) is not None:
        config.locate.baseline_runs = args.baseline_runs
    validate(config)


def _make_config(args: argparse.Namespace) -> Config:
    config = load_config(getattr(args, "config", None), start_dir=_cfg_start(args))
    _apply_overrides(config, args)
    return config


def _progress(round_no: int, total: int) -> None:
    sys.stderr.write(f"[flaky-hunter] round {round_no}/{total}\n")
    sys.stderr.flush()


def _enrich_nodeids(results, adapter) -> None:
    if not adapter.supports_locate:
        return
    mapping = adapter.nodeid_map()
    if not mapping:
        return
    for result in results:
        result.nodeid = mapping.get(result.nodeid, result.nodeid)


def _locate_all(report: Report, adapter, config: Config) -> None:
    targets = select_targets(report.findings, config.locate.top_n)
    if not targets:
        return
    positions = {nodeid: index for index, nodeid in enumerate(report.ordered_tests)}
    for finding in targets:
        position = positions.get(finding.nodeid)
        if position is None or position == 0:
            continue
        prefix = report.ordered_tests[:position]
        probe_dir = Path(tempfile.mkdtemp(prefix="fh-probe-"))
        counter = {"n": 0}

        def probe(tests, _dir=probe_dir, _counter=counter):
            _counter["n"] += 1
            report_path = _dir / f"probe-{_counter['n']}.xml"
            return adapter.execute(
                tests,
                report_path,
                session_id=report.session_id,
                round_no=1,
                timeout=config.locate.timeout_per_probe,
                target=finding.nodeid,
            )

        result = locate_polluters(
            finding.nodeid,
            prefix,
            probe,
            budget=ProbeBudget(config.locate.max_probe_total),
            confirm_runs=config.locate.confirm_runs,
            baseline_runs=config.locate.baseline_runs,
        )
        if result.blockers:
            result.reproduce = adapter.render_reproduce(
                result.blockers + [finding.nodeid]
            )
        finding.located = result
        if result.status == LocateStatus.FOUND:
            finding.root_cause = "order-dependent"


def _recount(report: Report) -> None:
    summary = report.summary
    summary.tests_total = len(report.findings)
    summary.flaky = 0
    summary.broken = 0
    summary.stable = 0
    summary.insufficient = 0
    for finding in report.findings:
        setattr(
            summary,
            finding.classification.value,
            getattr(summary, finding.classification.value) + 1,
        )


def _apply_baseline(report: Report, path: str) -> None:
    known = json_report.load_baseline(path)
    kept = [finding for finding in report.findings if finding.nodeid not in known]
    report.summary.suppressed_by_baseline = len(report.findings) - len(kept)
    report.findings = kept
    _recount(report)


def _emit(report: Report, config: Config, args: argparse.Namespace) -> None:
    use_color = (
        color_enabled()
        and not getattr(args, "no_color", False)
        and not config.output.path
    )
    text = render(report, config.output.format, color=use_color)
    if config.output.path:
        path = Path(config.output.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        sys.stderr.write(f"报告已写入 {path}\n")
    else:
        sys.stdout.write(text)


def _exit_code(report: Report, config: Config) -> int:
    threshold = config.ci.fail_on_score
    if threshold <= 0:
        return EXIT_OK
    for finding in report.findings:
        if (
            finding.classification == Classification.FLAKY
            and finding.score >= threshold
        ):
            return EXIT_FLAKY_FOUND
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    config = _make_config(args)
    adapter = make_adapter(
        config.run.adapter, config.run.cwd, config.locate.timeout_per_probe
    )

    session = execute(
        config, adapter, progress=_progress if args.verbose else None
    )
    if not session.results:
        sys.stderr.write("没有采集到任何测试结果。\n")
        for item in session.rounds:
            detail = f"  round {item.round}: {item.status.value}"
            if item.error:
                detail += f" — {item.error[:200]}"
            sys.stderr.write(detail + "\n")
        return EXIT_NO_RUN

    _enrich_nodeids(session.results, adapter)
    report = analyze(
        session.results,
        session.rounds,
        session.session_id,
        config,
        adapter=adapter.name,
        command=config.run.command or f"<{adapter.name} adapter>",
        cwd=config.run.cwd,
    )
    if config.locate.enabled and adapter.supports_locate:
        _locate_all(report, adapter, config)
    if args.baseline:
        _apply_baseline(report, args.baseline)

    _emit(report, config, args)
    return _exit_code(report, config)


def _expand_reports(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(Path(pattern))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def cmd_analyze(args: argparse.Namespace) -> int:
    config = _make_config(args)
    session_id = new_session_id()
    results = []
    rounds = []
    errors = []
    for index, path in enumerate(_expand_reports(args.reports), start=1):
        info = RoundInfo(round=index, report_path=str(path))
        try:
            results.extend(load_report(path, session_id, index))
        except ReportParseError as exc:
            info.status = RoundStatus.INVALID
            info.error = str(exc)
            errors.append(str(exc))
        rounds.append(info)
    for message in errors:
        sys.stderr.write(f"warning: {message}\n")
    if not results:
        sys.stderr.write("没有可分析的测试结果。\n")
        return EXIT_NO_RUN

    if getattr(args, "cwd", None) and config.run.adapter == "pytest":
        adapter = make_adapter(
            "pytest", config.run.cwd, config.locate.timeout_per_probe
        )
        _enrich_nodeids(results, adapter)

    report = analyze(
        results,
        rounds,
        session_id,
        config,
        adapter=config.run.adapter,
        cwd=getattr(args, "cwd", None) or "",
    )
    if args.baseline:
        _apply_baseline(report, args.baseline)
    _emit(report, config, args)
    return _exit_code(report, config)


def _resolve_target(ordered: list[str], target: str) -> Optional[str]:
    """Accept an exact nodeid or a unique path suffix.

    pytest reports nodeids relative to its rootdir, which may differ from the
    invocation directory, so ``tests/x.py::test_y`` should still match.
    """
    if target in ordered:
        return target
    candidates = [nodeid for nodeid in ordered if nodeid.endswith(target)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        sys.stderr.write(
            "错误: 目标用例匹配到多个候选项，请给出更完整的路径:\n  "
            + "\n  ".join(candidates)
            + "\n"
        )
        return None
    return ""


def cmd_locate(args: argparse.Namespace) -> int:
    config = _make_config(args)
    adapter = make_adapter("pytest", config.run.cwd, config.locate.timeout_per_probe)
    ordered = adapter.list_tests()
    resolved = _resolve_target(ordered, args.target)
    if resolved is None:
        return EXIT_ERROR
    if not resolved:
        sys.stderr.write(
            f"错误: 目标用例不在收集结果中: {args.target}\n"
            f"可用 nodeid 示例: {ordered[:3]}\n"
        )
        return EXIT_ERROR
    args.target = resolved

    position = ordered.index(args.target)
    prefix = ordered[:position]
    probe_dir = Path(tempfile.mkdtemp(prefix="fh-probe-"))
    counter = {"n": 0}

    def probe(tests):
        counter["n"] += 1
        report_path = probe_dir / f"probe-{counter['n']}.xml"
        return adapter.execute(
            tests,
            report_path,
            session_id="locate",
            round_no=1,
            timeout=config.locate.timeout_per_probe,
            target=args.target,
        )

    result = locate_polluters(
        args.target,
        prefix,
        probe,
        budget=ProbeBudget(config.locate.max_probe_total),
        confirm_runs=config.locate.confirm_runs,
        baseline_runs=config.locate.baseline_runs,
    )
    if result.blockers:
        result.reproduce = adapter.render_reproduce(result.blockers + [args.target])

    print(f"target: {args.target}")
    print(f"status: {result.status.value}")
    print(f"probes: {result.probes_used}  confidence: {result.confidence}")
    for blocker in result.blockers:
        print(f"polluter: {blocker}")
    if result.note:
        print(f"note: {result.note}")
    if result.reproduce:
        print("reproduce:")
        print(f"  {result.reproduce}")
    return EXIT_OK if result.status == LocateStatus.FOUND else EXIT_ERROR


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import prepare_fixture

    fixture = prepare_fixture()
    config = Config()
    config.run.cwd = str(fixture)
    config.run.rounds = max(1, args.rounds)
    config.run.adapter = "pytest"
    config.run.command = ""
    config.locate.timeout_per_probe = 60.0
    if args.no_locate:
        config.locate.enabled = False

    adapter = make_adapter("pytest", str(fixture), config.locate.timeout_per_probe)
    session = execute(config, adapter, progress=_progress if args.verbose else None)
    if not session.results:
        sys.stderr.write("示例执行失败，没有采集到结果。\n")
        for item in session.rounds:
            sys.stderr.write(f"  round {item.round}: {item.status.value} {item.error}\n")
        return EXIT_NO_RUN

    _enrich_nodeids(session.results, adapter)
    report = analyze(
        session.results,
        session.rounds,
        session.session_id,
        config,
        adapter=adapter.name,
        command=f"<{adapter.name} adapter>",
        cwd=str(fixture),
    )
    if config.locate.enabled:
        _locate_all(report, adapter, config)

    use_color = color_enabled() and not args.no_color
    sys.stdout.write(render(report, "terminal", color=use_color))
    sys.stderr.write(f"\n示例仓库: {fixture}\n")
    return EXIT_OK


def _configure_streams() -> None:
    """Keep UTF-8 when output is piped or redirected on a non-UTF-8 locale.

    A Windows console handles Unicode through WriteConsoleW, so it is left
    alone; pipes and files get UTF-8, which is what CI and README captures want.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty() and hasattr(stream, "reconfigure"):
                encoding = (getattr(stream, "encoding", "") or "").lower()
                if encoding not in ("utf-8", "utf8"):
                    stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: Optional[list[str]] = None) -> int:
    _configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "run": cmd_run,
        "analyze": cmd_analyze,
        "locate": cmd_locate,
        "demo": cmd_demo,
    }
    try:
        return handlers[args.subcommand](args)
    except FlakyHunterError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_ERROR
    except KeyboardInterrupt:
        sys.stderr.write("已中断\n")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
