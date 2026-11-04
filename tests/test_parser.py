"""Tests for the ``name=value`` telemetry and log-level parsers."""

from dataclasses import FrozenInstanceError

import pytest

from stm32serial import LEVELS, Sample, level_of, parse_samples, severity_of


def names(line):
    return [(sample.name, sample.value, sample.unit) for sample in parse_samples(line)]


def test_single_pair_with_unit():
    assert names("temp=25.50C") == [("temp", 25.5, "C")]


def test_multiple_pairs_on_one_line():
    assert names("temp=25.00C hum=41.00% vbus=3.300V") == [
        ("temp", 25.0, "C"),
        ("hum", 41.0, "%"),
        ("vbus", 3.3, "V"),
    ]


def test_colon_separator_and_spaces():
    assert names("  hum : 41.5 %  ") == [("hum", 41.5, "%")]


def test_negative_scientific_and_bare_values():
    assert names("offset=-12.5v gain=1.5e-3") == [("offset", -12.5, "v"), ("gain", 0.0015, None)]


def test_unit_is_not_stolen_from_the_next_key():
    # Without the lookahead, "a=1 b=2" would parse the unit of a as "b".
    assert names("a=1 b=2") == [("a", 1.0, None), ("b", 2.0, None)]


def test_text_without_telemetry_yields_nothing():
    assert parse_samples("[INFO] boot complete") == []
    assert parse_samples("") == []


def test_identifier_before_separator_is_not_matched_mid_word():
    # ``uart1_rx`` must not become a channel; only the real pair counts.
    assert names("uart1_rx=1") == [("uart1_rx", 1.0, None)]


def test_error_line_still_yields_its_samples():
    assert names("[ERROR] uart overrun, tick=42") == [("tick", 42.0, None)]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("[INFO] hello", "INFO"),
        ("<warn> low battery", "WARN"),
        ("(ERROR) boom", "ERROR"),
        ("DEBUG: starting", "DEBUG"),
        ("ERROR - boom", "ERROR"),
        ("warning: low", "WARN"),
        ("err: x", "ERROR"),
        ("crit: y", "FATAL"),
        ("plain text", None),
        ("", None),
    ],
)
def test_level_of(line, expected):
    assert level_of(line) == expected


def test_levels_are_ordered_by_severity():
    assert LEVELS == ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")
    severities = [severity_of(level) for level in LEVELS]
    assert severities == sorted(severities)
    assert severity_of("unknown") == severity_of("TRACE")


def test_sample_is_hashable_and_frozen():
    sample = Sample("temp", 1.0, "C")
    with pytest.raises(FrozenInstanceError):
        sample.value = 2.0  # type: ignore[misc]