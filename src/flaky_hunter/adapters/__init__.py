"""Runner adapters."""

from __future__ import annotations

from .base import (
    RunnerAdapter,
    base_env,
    python_executable,
    quote_arg,
    run_process,
    split_command,
)
from .junit_adapter import JUnitAdapter
from .pytest_adapter import PytestAdapter, nodeid_to_key

_ADAPTERS = {
    "pytest": PytestAdapter,
    "junit-xml": JUnitAdapter,
}


def make_adapter(name: str, cwd: str, timeout: float = 300.0) -> RunnerAdapter:
    try:
        factory = _ADAPTERS[name]
    except KeyError as exc:  # config.validate should have caught this
        raise ValueError(f"未知 adapter: {name}") from exc
    return factory(cwd=cwd, timeout=timeout)


__all__ = [
    "RunnerAdapter",
    "PytestAdapter",
    "JUnitAdapter",
    "make_adapter",
    "nodeid_to_key",
    "base_env",
    "python_executable",
    "quote_arg",
    "run_process",
    "split_command",
]
