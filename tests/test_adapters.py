from pathlib import Path

from flaky_hunter.adapters.pytest_adapter import PytestAdapter, nodeid_to_key


def test_nodeid_to_key():
    assert nodeid_to_key("tests/test_a.py::test_x") == "tests.test_a::test_x"
    assert (
        nodeid_to_key("tests/test_a.py::TestC::test_x")
        == "tests.test_a.TestC::test_x"
    )


def test_nodeid_to_key_is_idempotent():
    key = "tests.test_a::test_x"
    assert nodeid_to_key(key) == key


def test_absolute_nodeid_resolves_rootdir_relative_path(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_a.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    workdir = tmp_path / "sub"
    workdir.mkdir()

    adapter = PytestAdapter(cwd=workdir)
    resolved = adapter.absolute_nodeid("tests/test_a.py::test_x")

    assert Path(resolved.partition("::")[0]) == test_file
    assert resolved.endswith("::test_x")


def test_cwd_relative_nodeid_shortens_again(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    adapter = PytestAdapter(cwd=tmp_path)
    resolved = adapter.cwd_relative_nodeid("tests/test_a.py::test_x")
    assert resolved.startswith("tests")
    assert resolved.endswith("::test_x")
