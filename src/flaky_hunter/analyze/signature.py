"""Failure-signature normalisation.

Raw failure text contains timestamps, ports, temp paths and object addresses
that change on every run. Collapsing them into a stable signature is what makes
cross-round clustering possible.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?")
_TIME_ONLY = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b")
_HEX_ADDR = re.compile(r"\b0x[0-9a-fA-F]+\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_PORT = re.compile(r":\d{2,5}\b")
_TEMP_PATH = re.compile(
    r"(?:/tmp/|/var/folders/|/private/var/|[A-Za-z]:\\Users\\[^\\\s]+\\AppData\\)"
    r"[^\s'\"]*"
)
_STANDALONE_NUMBER = re.compile(r"(?<![\w.])\d+(?![\w])")
_WHITESPACE = re.compile(r"[ \t]+")

_NORMALIZERS = (
    (_TIMESTAMP, "<ts>"),
    (_TIME_ONLY, "<time>"),
    (_UUID, "<uuid>"),
    (_HEX_ADDR, "0x<hex>"),
    (_TEMP_PATH, "<tmp>"),
    (_PORT, ":<port>"),
    (_STANDALONE_NUMBER, "<n>"),
    (_WHITESPACE, " "),
)

_EXCEPTION = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b")
_FRAME_LONG = re.compile(r'File "([^"]+)", line \d+, in ([^\s]+)')
_FRAME_SHORT = re.compile(r"([^\s:()\"']+\.py):\d+(?:: in ([^\s]+))?")

_LIBRARY_MARKERS = (
    "site-packages",
    "dist-packages",
    "/lib/python",
    "\\lib\\python",
    "/usr/lib/python",
    "/usr/local/lib/python",
)


def normalize_text(text: str) -> str:
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _is_library_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _LIBRARY_MARKERS)


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _user_frames(trace: str) -> list[str]:
    frames: list[tuple[str, str]] = []
    for match in _FRAME_LONG.finditer(trace):
        frames.append((match.group(1), match.group(2)))
    if not frames:
        for match in _FRAME_SHORT.finditer(trace):
            frames.append((match.group(1), match.group(2) or ""))

    kept: list[str] = []
    for path, func in frames:
        if _is_library_path(path):
            continue
        frame = _basename(path)
        if func:
            frame = f"{frame}:{func}"
        kept.append(normalize_text(frame))
    return kept[-3:]


def exception_type(*texts: str) -> str:
    found = ""
    for text in texts:
        matches = _EXCEPTION.findall(text or "")
        if matches:
            found = matches[-1]
    return found or "Unknown"


@dataclass(frozen=True)
class SignatureInfo:
    signature: str
    exception: str
    frames: list[str]
    display: str


def signature_for(message: str, trace: str = "") -> SignatureInfo:
    exc = exception_type(message, trace)
    frames = _user_frames(trace)
    payload = normalize_text(message) + "\n" + "|".join(frames)
    digest = hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest()[:12]
    display = exc if not frames else f"{exc} @ {frames[-1]}"
    return SignatureInfo(signature=digest, exception=exc, frames=frames, display=display)
