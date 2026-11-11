"""Data model shared by every layer of flaky-hunter."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

SCHEMA_VERSION = "1.1"


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"

    @property
    def is_failure(self) -> bool:
        return self in (Outcome.FAILED, Outcome.ERROR)


class RoundStatus(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    TRUNCATED = "truncated"


class Classification(str, Enum):
    FLAKY = "flaky"
    BROKEN = "broken"
    STABLE = "stable"
    INSUFFICIENT = "insufficient"


class LocateStatus(str, Enum):
    FOUND = "FOUND"
    NOT_ORDER_DEPENDENT = "NOT_ORDER_DEPENDENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    PARTIAL = "PARTIAL"
    UNSTABLE_EVIDENCE = "UNSTABLE_EVIDENCE"
    ABORTED = "ABORTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class TestResult:
    """One test execution inside one round."""

    session_id: str
    round: int
    nodeid: str
    suite: str = ""
    outcome: Outcome = Outcome.PASSED
    duration_ms: float = 0.0
    message: str = ""
    trace: str = ""
    stdout: str = ""
    stderr: str = ""


@dataclass
class RoundInfo:
    round: int
    status: RoundStatus = RoundStatus.OK
    report_path: str = ""
    duration_ms: float = 0.0
    exit_code: Optional[int] = None
    error: str = ""


@dataclass
class ProbeOutcome:
    """Aggregated result of one probe run (a subset of the suite)."""

    outcome: str = "invalid"  # passed | failed | error | timeout | invalid
    duration_ms: float = 0.0
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"

    @property
    def failed(self) -> bool:
        return self.outcome in ("failed", "error")

    @property
    def indeterminate(self) -> bool:
        return self.outcome in ("timeout", "invalid")


@dataclass
class ProbeEvidence:
    index: int
    tests: list[str]
    outcome: str
    duration_ms: float = 0.0


@dataclass
class Cluster:
    signature: str
    label: str
    count: int
    first_round: int
    last_round: int
    sample_message: str


@dataclass
class LocateResult:
    status: LocateStatus
    blockers: list[str] = field(default_factory=list)
    probes_used: int = 0
    confidence: str = "low"
    evidence: list[ProbeEvidence] = field(default_factory=list)
    reproduce: str = ""
    note: str = ""


@dataclass
class Finding:
    """Everything we know about one test across all rounds."""

    nodeid: str
    classification: Classification
    attempts: int
    failures: int
    score: int
    pass_rate: float
    rounds_present: int
    duration_avg_ms: float = 0.0
    duration_max_ms: float = 0.0
    clusters: list[Cluster] = field(default_factory=list)
    root_cause: str = ""
    located: Optional[LocateResult] = None


@dataclass
class SessionSummary:
    rounds_total: int = 0
    rounds_ok: int = 0
    tests_total: int = 0
    skipped_tests: int = 0
    flaky: int = 0
    broken: int = 0
    stable: int = 0
    insufficient: int = 0
    suppressed_by_baseline: int = 0


@dataclass
class Report:
    session_id: str
    generated_at: str
    rounds: list[RoundInfo] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    summary: SessionSummary = field(default_factory=SessionSummary)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    adapter: str = "pytest"
    ordered_tests: list[str] = field(default_factory=list)
    tool_version: str = ""
    command: str = ""
    cwd: str = ""
    schema_version: str = SCHEMA_VERSION
