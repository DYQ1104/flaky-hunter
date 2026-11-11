from pathlib import Path

import pytest

from flaky_hunter.adapters.junit_adapter import JUnitAdapter
from flaky_hunter.errors import AdapterError


def test_adapter_metadata(tmp_path: Path):
    adapter = JUnitAdapter(cwd=tmp_path)

    assert adapter.name == "junit-xml"
    assert adapter.supports_locate is False


def test_build_command_is_rejected(tmp_path: Path):
    adapter = JUnitAdapter(cwd=tmp_path)

    with pytest.raises(AdapterError, match="只能分析已有报告"):
        adapter.build_command([], tmp_path / "report.xml")


def test_list_tests_is_unsupported(tmp_path: Path):
    adapter = JUnitAdapter(cwd=tmp_path)

    with pytest.raises(AdapterError, match="不支持枚举用例"):
        adapter.list_tests()


def test_execute_fails_before_running_anything(tmp_path: Path):
    adapter = JUnitAdapter(cwd=tmp_path)

    with pytest.raises(AdapterError, match="只能分析已有报告"):
        adapter.execute([], tmp_path / "report.xml")
