"""pytest adapter: command construction, test enumeration and nodeid mapping."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..errors import AdapterError
from .base import RunnerAdapter, base_env, python_executable, quote_arg, run_process


def nodeid_to_key(nodeid: str) -> str:
    """Convert an executable nodeid to the parser key (classname::name).

    ``tests/test_a.py::TestCls::test_x`` -> ``tests.test_a.TestCls::test_x``
    """
    path, _, rest = nodeid.partition("::")
    if not rest:
        return nodeid
    parts = rest.split("::")
    module = path[:-3] if path.endswith(".py") else path
    module = module.replace("\\", ".").replace("/", ".")
    if len(parts) > 1:
        module = module + "." + ".".join(parts[:-1])
    return f"{module}::{parts[-1]}"


class PytestAdapter(RunnerAdapter):
    name = "pytest"
    supports_locate = True

    def __init__(self, cwd: Path | str = ".", timeout: float = 300.0) -> None:
        super().__init__(cwd, timeout)
        self._base_dir_cache: Optional[Path] = None

    def _find_base(self, sample_path: str) -> Path:
        """Find the directory that collected nodeids are relative to.

        pytest prints nodeids relative to its rootdir, which may be an ancestor
        of the working directory. Probing needs a path that resolves the same
        way from ``cwd``, so we locate the real base before making it absolute.
        """
        for candidate in (self.cwd, *self.cwd.parents):
            try:
                if (candidate / sample_path).is_file():
                    return candidate
            except OSError:  # pragma: no cover - unreadable path component
                continue
        return self.cwd

    def absolute_nodeid(self, nodeid: str) -> str:
        path, sep, rest = nodeid.partition("::")
        if not path or Path(path).is_absolute():
            return nodeid
        base = self._base_dir_cache
        if base is None or not (base / path).is_file():
            base = self._find_base(path)
        resolved = str(base / path)
        return f"{resolved}::{rest}" if sep else resolved

    def cwd_relative_nodeid(self, nodeid: str) -> str:
        absolute = self.absolute_nodeid(nodeid)
        path, sep, rest = absolute.partition("::")
        try:
            relative = os.path.relpath(path, str(self.cwd))
        except ValueError:  # different drive on Windows
            relative = path
        return f"{relative}::{rest}" if sep else relative

    def build_command(self, tests: list[str], report_path: Path) -> list[str]:
        resolved = [self.absolute_nodeid(item) for item in tests]
        return [
            python_executable(),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *resolved,
            f"--junitxml={report_path}",
        ]

    def _collect(self, extra: list[str]) -> list[str]:
        command = [
            python_executable(),
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *extra,
        ]
        code, out, err, timed_out = run_process(
            command, self.cwd, self.timeout, base_env()
        )
        if timed_out:
            raise AdapterError("收集用例超时")
        if code != 0 and "::" not in out:
            detail = (err or out).strip()[-300:]
            raise AdapterError(f"收集用例失败: {detail}")

        tests: list[str] = []
        for line in out.splitlines():
            line = line.strip().strip("\r")
            if "::" not in line:
                continue
            if line.startswith(("=", "!", "E ", "FAILED", "ERROR")):
                continue
            tests.append(line)
        return tests

    def list_tests(self) -> list[str]:
        tests = self._collect([])
        if not tests:
            # A project's addopts may already contain -q, which turns our -q
            # into -qq and silences the collection list. Retry with the
            # inherited addopts cleared before giving up.
            tests = self._collect(["-o", "addopts="])
        if tests:
            sample = tests[0].partition("::")[0]
            self._base_dir_cache = self._find_base(sample)
        return tests

    def nodeid_map(self) -> dict[str, str]:
        try:
            return {nodeid_to_key(nodeid): nodeid for nodeid in self.list_tests()}
        except AdapterError:
            return {}

    def result_key(self, nodeid: str) -> str:
        return nodeid_to_key(nodeid)

    def render_reproduce(self, tests: list[str]) -> str:
        parts = " ".join(
            quote_arg(self.cwd_relative_nodeid(item)) for item in tests
        )
        return f"{quote_arg(python_executable())} -m pytest -q {parts}"
