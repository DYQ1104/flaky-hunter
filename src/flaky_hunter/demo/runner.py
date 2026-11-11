"""Copy the bundled demo fixture into a throwaway directory."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..errors import FlakyHunterError


def prepare_fixture() -> Path:
    source = Path(__file__).resolve().parent / "fixture"
    if not source.is_dir():
        raise FlakyHunterError(f"示例仓库缺失: {source}")
    target = Path(tempfile.mkdtemp(prefix="flaky-hunter-demo-")) / "flaky-demo"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return target
