"""Terminal rendering: timestamps, level colours and fixed-width tables."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sequence
from typing import TextIO

RESET = "\x1b[0m"

_LEVEL_COLORS = {
    "TRACE": "\x1b[90m",
    "DEBUG": "\x1b[36m",
    "INFO": "\x1b[32m",
    "WARN": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "FATAL": "\x1b[1;31m",
}


def supports_color(stream: TextIO) -> bool:
    """True when *stream* should receive ANSI colour codes."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def colorize(text: str, level: str | None, enabled: bool = True) -> str:
    """Wrap *text* in the ANSI colour matching *level*."""
    if not enabled or level is None:
        return text
    code = _LEVEL_COLORS.get(level.upper())
    return f"{code}{text}{RESET}" if code else text


def format_timestamp(seconds: float, mode: str = "elapsed") -> str:
    """Render a monotonic or wall-clock timestamp.

    ``elapsed`` yields ``+00:01.234`` so that two log files stay comparable,
    while ``clock`` keeps the local time of day.
    """
    if mode == "clock":
        stamp = time.strftime("%H:%M:%S", time.localtime(seconds))
        return f"{stamp}.{int(round((seconds % 1) * 1000)) % 1000:03d}"

    total_ms = int(round(max(seconds, 0.0) * 1000))
    minutes, remainder = divmod(total_ms, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"+{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def render_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """Left-align the first column, right-align the rest, then strip padding."""
    table: list[list[str]] = [list(headers)] + [
        [str(cell) for cell in row] for row in rows
    ]
    widths = [max(len(row[index]) for row in table) for index in range(len(headers))]

    def render(row: list[str]) -> str:
        cells = [
            row[index] if index == 0 else row[index].rjust(widths[index])
            for index in range(len(headers))
        ]
        return "  ".join(cells).rstrip()

    return "\n".join(render(row) for row in table)