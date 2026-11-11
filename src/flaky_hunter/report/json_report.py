"""JSON report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Finding, Report


def _cluster_to_dict(cluster) -> dict[str, Any]:
    return {
        "signature": cluster.signature,
        "label": cluster.label,
        "count": cluster.count,
        "first_round": cluster.first_round,
        "last_round": cluster.last_round,
        "sample_message": cluster.sample_message,
    }


def _located_to_dict(located) -> dict[str, Any] | None:
    if located is None:
        return None
    return {
        "status": located.status.value,
        "blockers": list(located.blockers),
        "probes_used": located.probes_used,
        "confidence": located.confidence,
        "note": located.note,
        "reproduce": located.reproduce,
        "evidence": [
            {
                "index": item.index,
                "tests": list(item.tests),
                "outcome": item.outcome,
                "duration_ms": round(item.duration_ms, 2),
            }
            for item in located.evidence
        ],
    }


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "nodeid": finding.nodeid,
        "classification": finding.classification.value,
        "score": finding.score,
        "attempts": finding.attempts,
        "failures": finding.failures,
        "pass_rate": round(finding.pass_rate, 4),
        "rounds_present": finding.rounds_present,
        "duration": {
            "avg_ms": round(finding.duration_avg_ms, 2),
            "max_ms": round(finding.duration_max_ms, 2),
        },
        "root_cause": finding.root_cause,
        "clusters": [_cluster_to_dict(cluster) for cluster in finding.clusters],
        "located": _located_to_dict(finding.located),
    }


def report_to_dict(report: Report) -> dict[str, Any]:
    summary = report.summary
    return {
        "schema_version": report.schema_version,
        "tool_version": report.tool_version,
        "session_id": report.session_id,
        "generated_at": report.generated_at,
        "adapter": report.adapter,
        "command": report.command,
        "cwd": report.cwd,
        "summary": {
            "rounds_total": summary.rounds_total,
            "rounds_ok": summary.rounds_ok,
            "tests_total": summary.tests_total,
            "skipped_tests": summary.skipped_tests,
            "flaky": summary.flaky,
            "broken": summary.broken,
            "stable": summary.stable,
            "insufficient": summary.insufficient,
            "suppressed_by_baseline": summary.suppressed_by_baseline,
        },
        "rounds": [
            {
                "round": item.round,
                "status": item.status.value,
                "duration_ms": round(item.duration_ms, 2),
                "exit_code": item.exit_code,
                "error": item.error,
            }
            for item in report.rounds
        ],
        "findings": [_finding_to_dict(finding) for finding in report.findings],
    }


def dumps(report: Report, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=indent)


def write(report: Report, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(report) + "\n", encoding="utf-8")
    return target


def load_baseline(path: str | Path) -> set[str]:
    """Return the nodeids already known to be flaky in a previous report."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"基线报告缺少 findings 数组: {path}")
    known: set[str] = set()
    for item in findings:
        if not isinstance(item, dict):
            continue
        nodeid = item.get("nodeid")
        classification = item.get("classification")
        if nodeid and classification in ("flaky", "broken"):
            known.add(str(nodeid))
    return known


__all__ = ["report_to_dict", "dumps", "write", "load_baseline"]
