"""Tests for timestamps, ANSI colouring and table alignment."""

import io
import time

import pytest

from stm32serial.render import (
    RESET,
    colorize,
    format_timestamp,
    render_table,
    supports_color,
)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0.0, "+00:00.000"),
        (1.234, "+00:01.234"),
        (59.999, "+00:59.999"),
        (60.0, "+01:00.000"),
        (3661.5, "+61:01.500"),
    ],
)
def test_format_timestamp_elapsed(seconds, expected):
    assert format_timestamp(seconds, "elapsed") == expected


def test_format_timestamp_clamps_negative_values():
    assert format_timestamp(-5.0, "elapsed") == "+00:00.000"


def test_format_timestamp_clock_uses_local_time():
    stamp = format_timestamp(time.mktime((2024, 1, 2, 3, 4, 5, 0, 0, -1)), "clock")
    assert stamp.startswith("03:04:05.")


def test_supports_color_respects_environment(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert supports_color(Tty()) is True
    assert supports_color(io.StringIO()) is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color(Tty()) is False

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert supports_color(io.StringIO()) is True


def test_colorize_wraps_known_levels_only():
    assert colorize("boom", "ERROR") == "\x1b[31mboom" + RESET
    assert colorize("boom", "ERROR", enabled=False) == "boom"
    assert colorize("boom", None) == "boom"
    assert colorize("boom", "NOT-A-LEVEL") == "boom"


def test_render_table_aligns_columns():
    rendered = render_table(["channel", "count", "mean"], [["temp", 3, "22.5"], ["h", 1, "50"]])
    lines = rendered.splitlines()
    assert lines[0].split() == ["channel", "count", "mean"]
    # No trailing padding anywhere.
    assert all(line == line.rstrip() for line in lines)
    # Numeric columns are right aligned, so "3" is padded before "22.5".
    assert lines[1].startswith("temp")
    assert lines[1].endswith("22.5")
    assert lines[2].startswith("h")


def test_render_table_headers_only():
    assert render_table(["a", "b"], []).strip() == "a  b"