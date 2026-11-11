"""Configuration loading and precedence handling.

Precedence (highest first): CLI flags > FH_* environment variables > config
file (.flaky-hunter.toml or pyproject.toml [tool.flaky-hunter]) > defaults.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from .errors import ConfigError

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter version
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

CONFIG_FILENAMES = (".flaky-hunter.toml", "flaky-hunter.toml")
VALID_ADAPTERS = ("pytest", "junit-xml")
VALID_FORMATS = ("terminal", "json", "markdown")


@dataclass
class RunSection:
    command: str = ""
    rounds: int = 10
    timeout_per_round: float = 600.0
    max_rounds_seconds: float = 1800.0
    adapter: str = "pytest"
    cwd: str = "."
    delay: float = 0.0


@dataclass
class AnalysisSection:
    min_attempts: int = 5
    flaky_threshold: int = 30
    ignore: list[str] = field(default_factory=list)
    exclude_markers: list[str] = field(default_factory=list)


@dataclass
class LocateSection:
    enabled: bool = True
    top_n: int = 5
    confirm_runs: int = 2
    baseline_runs: int = 2
    max_probe_total: int = 60
    timeout_per_probe: float = 300.0


@dataclass
class OutputSection:
    format: str = "terminal"
    path: str = ""


@dataclass
class CiSection:
    fail_on_score: int = 0


@dataclass
class Config:
    run: RunSection = field(default_factory=RunSection)
    analysis: AnalysisSection = field(default_factory=AnalysisSection)
    locate: LocateSection = field(default_factory=LocateSection)
    output: OutputSection = field(default_factory=OutputSection)
    ci: CiSection = field(default_factory=CiSection)
    source_path: str = ""

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("source_path", None)
        return data


def _merge_into(dc: Any, values: dict[str, Any]) -> None:
    known = {f.name for f in fields(dc)}
    for key, value in values.items():
        if key not in known:
            continue
        current = getattr(dc, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_into(current, value)
        else:
            setattr(dc, key, value)


def _read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise ConfigError(
            "检测到配置文件但缺少 TOML 解析器：请使用 Python 3.11+，"
            "或执行 `pip install tomli`。"
        )
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件 {path}: {exc}") from exc
    except Exception as exc:  # tomllib.TOMLDecodeError and friends
        raise ConfigError(f"配置文件 {path} 格式错误: {exc}") from exc


def _find_config_file(start: Path) -> Optional[Path]:
    current = start.resolve()
    for directory in (current, *current.parents):
        for name in CONFIG_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file():
            data = _read_toml(pyproject)
            tool = data.get("tool", {})
            if isinstance(tool, dict) and "flaky-hunter" in tool:
                return pyproject
    return None


def load_config(path: Optional[str] = None, start_dir: str = ".") -> Config:
    config = Config()
    source: Optional[Path] = None
    if path:
        source = Path(path)
        if not source.is_file():
            raise ConfigError(f"配置文件不存在: {source}")
    else:
        source = _find_config_file(Path(start_dir))

    if source is not None:
        data = _read_toml(source)
        if source.name == "pyproject.toml":
            data = data.get("tool", {}).get("flaky-hunter", {})
        if not isinstance(data, dict):
            raise ConfigError(f"配置文件 {source} 的顶层结构必须是表(table)")
        config.source_path = str(source)
        for section_name in ("run", "analysis", "locate", "output", "ci"):
            section = getattr(config, section_name)
            values = data.get(section_name, {})
            if not isinstance(values, dict):
                raise ConfigError(f"[{section_name}] 必须是表(table)")
            _merge_into(section, values)

    _apply_env(config)
    validate(config)
    return config


def _apply_env(config: Config) -> None:
    mapping = {
        "FH_COMMAND": (config.run, "command", str),
        "FH_ROUNDS": (config.run, "rounds", int),
        "FH_ADAPTER": (config.run, "adapter", str),
        "FH_CWD": (config.run, "cwd", str),
        "FH_FORMAT": (config.output, "format", str),
        "FH_FAIL_ON_SCORE": (config.ci, "fail_on_score", int),
    }
    for env_name, (section, attr, caster) in mapping.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            setattr(section, attr, caster(raw))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"环境变量 {env_name} 取值非法: {raw!r}") from exc


def validate(config: Config) -> None:
    if config.run.adapter not in VALID_ADAPTERS:
        raise ConfigError(
            f"未知 adapter: {config.run.adapter!r}，可选: {', '.join(VALID_ADAPTERS)}"
        )
    if config.output.format not in VALID_FORMATS:
        raise ConfigError(
            f"未知输出格式: {config.output.format!r}，可选: {', '.join(VALID_FORMATS)}"
        )
    if config.run.rounds < 1:
        raise ConfigError("rounds 必须 >= 1")
    if config.analysis.min_attempts < 1:
        raise ConfigError("min_attempts 必须 >= 1")
    if not 0 <= config.ci.fail_on_score <= 100:
        raise ConfigError("fail_on_score 必须在 0~100 之间（0 表示关闭）")
    if config.locate.max_probe_total < 3:
        raise ConfigError("max_probe_total 必须 >= 3")
