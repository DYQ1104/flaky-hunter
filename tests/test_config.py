from pathlib import Path

import pytest

from flaky_hunter.config import Config, load_config, validate
from flaky_hunter.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_match_documented_behaviour():
    config = Config()

    assert config.run.adapter == "pytest"
    assert config.run.rounds == 10
    assert config.run.timeout_per_round == 600.0
    assert config.analysis.min_attempts == 5
    assert config.analysis.flaky_threshold == 30
    assert config.locate.enabled is True
    assert config.locate.max_probe_total == 60
    assert config.output.format == "terminal"
    assert config.ci.fail_on_score == 0


def test_loads_sections_from_toml(tmp_path: Path):
    path = _write(
        tmp_path / ".flaky-hunter.toml",
        """
[run]
command = "python -m pytest -q --junitxml={report}"
rounds = 3
adapter = "pytest"
cwd = "tests"

[analysis]
min_attempts = 2
ignore = ["tests/test_slow.py"]

[locate]
top_n = 2
max_probe_total = 10

[output]
format = "json"

[ci]
fail_on_score = 60
""",
    )

    config = load_config(str(path))

    assert config.run.rounds == 3
    assert config.run.cwd == "tests"
    assert config.run.command.endswith("{report}")
    assert config.analysis.min_attempts == 2
    assert config.analysis.ignore == ["tests/test_slow.py"]
    assert config.locate.top_n == 2
    assert config.locate.max_probe_total == 10
    assert config.output.format == "json"
    assert config.ci.fail_on_score == 60
    assert config.source_path == str(path)
    assert "source_path" not in config.snapshot()


def test_loads_pyproject_tool_section(tmp_path: Path):
    path = _write(
        tmp_path / "pyproject.toml",
        """
[project]
name = "demo"

[tool.flaky-hunter.run]
rounds = 4
adapter = "junit-xml"

[tool.flaky-hunter.ci]
fail_on_score = 50
""",
    )

    config = load_config(str(path))

    assert config.run.rounds == 4
    assert config.run.adapter == "junit-xml"
    assert config.ci.fail_on_score == 50


def test_discovers_config_upwards(tmp_path: Path):
    _write(tmp_path / ".flaky-hunter.toml", "[run]\nrounds = 2\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    config = load_config(start_dir=str(nested))

    assert config.run.rounds == 2


def test_unknown_keys_are_ignored(tmp_path: Path):
    path = _write(
        tmp_path / ".flaky-hunter.toml",
        "[run]\nrounds = 6\nfuture_option = true\n",
    )

    config = load_config(str(path))

    assert config.run.rounds == 6


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write(
        tmp_path / ".flaky-hunter.toml",
        '[run]\nrounds = 2\nadapter = "pytest"\n[output]\nformat = "terminal"\n',
    )
    monkeypatch.setenv("FH_ROUNDS", "7")
    monkeypatch.setenv("FH_ADAPTER", "junit-xml")
    monkeypatch.setenv("FH_FORMAT", "json")
    monkeypatch.setenv("FH_FAIL_ON_SCORE", "80")

    config = load_config(str(path))

    assert config.run.rounds == 7
    assert config.run.adapter == "junit-xml"
    assert config.output.format == "json"
    assert config.ci.fail_on_score == 80


def test_empty_env_value_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FH_ROUNDS", "")

    config = load_config(None, start_dir=str(tmp_path))

    assert config.run.rounds == 10


def test_invalid_env_value_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FH_ROUNDS", "many")

    with pytest.raises(ConfigError, match="FH_ROUNDS"):
        load_config(None, start_dir=".")


def test_missing_explicit_config_raises():
    with pytest.raises(ConfigError, match="配置文件不存在"):
        load_config("does-not-exist.toml")


def test_malformed_toml_raises(tmp_path: Path):
    path = _write(tmp_path / ".flaky-hunter.toml", "[run\nrounds = 2\n")

    with pytest.raises(ConfigError, match="格式错误"):
        load_config(str(path))


def test_non_table_section_raises(tmp_path: Path):
    path = _write(tmp_path / ".flaky-hunter.toml", "run = 3\n")

    with pytest.raises(ConfigError, match=r"\[run\] 必须是表"):
        load_config(str(path))


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda cfg: setattr(cfg.run, "adapter", "nose"), "未知 adapter"),
        (lambda cfg: setattr(cfg.output, "format", "xml"), "未知输出格式"),
        (lambda cfg: setattr(cfg.run, "rounds", 0), "rounds 必须"),
        (lambda cfg: setattr(cfg.analysis, "min_attempts", 0), "min_attempts 必须"),
        (lambda cfg: setattr(cfg.ci, "fail_on_score", 101), "fail_on_score"),
        (lambda cfg: setattr(cfg.ci, "fail_on_score", -1), "fail_on_score"),
        (lambda cfg: setattr(cfg.locate, "max_probe_total", 2), "max_probe_total"),
    ],
)
def test_validate_rejects_bad_values(mutate, message):
    config = Config()
    mutate(config)

    with pytest.raises(ConfigError, match=message):
        validate(config)


def test_validate_accepts_boundary_values():
    config = Config()
    config.run.rounds = 1
    config.analysis.min_attempts = 1
    config.ci.fail_on_score = 100
    config.locate.max_probe_total = 3

    validate(config)
