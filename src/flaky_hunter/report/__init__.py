"""Report renderers."""

from . import json_report, markdown, terminal
from .terminal import color_enabled

_FORMATS = {
    "terminal": lambda report, color=False: terminal.render(report, color=color),
    "json": lambda report, color=False: json_report.dumps(report),
    "markdown": lambda report, color=False: markdown.render(report),
}


def render(report, fmt: str = "terminal", color: bool = False) -> str:
    try:
        renderer = _FORMATS[fmt]
    except KeyError as exc:
        raise ValueError(f"未知输出格式: {fmt}") from exc
    return renderer(report, color)


__all__ = ["render", "color_enabled", "json_report", "markdown", "terminal"]
