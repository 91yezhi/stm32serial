"""Tests for the aggregate statistics and the sparkline renderer."""

import csv
import json
import math

import pytest

from stm32serial import StatsCollector, parse_samples, sparkline
from stm32serial.stats import CSV_FIELDS, PERCENTILE_WINDOW, SPARK_CHARS, ChannelStats


def test_accumulates_basic_statistics():
    channel = ChannelStats("temp")
    for value in (20.0, 24.0, 22.0):
        channel.add(value, "C")

    assert channel.count == 3
    assert channel.minimum == 20.0
    assert channel.maximum == 24.0
    assert channel.first == 20.0
    assert channel.last == 22.0
    assert channel.mean == pytest.approx(22.0)
    assert channel.unit == "C"


def test_population_standard_deviation():
    channel = ChannelStats("x")
    for value in (2, 4, 4, 4, 5, 5, 7, 9):
        channel.add(value)
    # Known example: mean 5, population stdev 2.
    assert channel.mean == pytest.approx(5.0)
    assert channel.stdev == pytest.approx(2.0)


def test_single_sample_has_zero_stdev():
    channel = ChannelStats("x")
    channel.add(3.0)
    assert channel.stdev == 0.0


def test_as_dict_keys_and_rounding():
    channel = ChannelStats("vbus")
    channel.add(3.3000, "V")
    channel.add(3.4000, "V")
    data = channel.as_dict()
    assert list(data) == list(CSV_FIELDS)
    assert data["channel"] == "vbus"
    assert data["unit"] == "V"
    assert data["count"] == 2
    assert data["mean"] == pytest.approx(3.35)


def test_recent_window_is_bounded():
    channel = ChannelStats("x")
    for value in range(1000):
        channel.add(float(value))
    assert len(channel.recent) < 1000
    assert channel.sparkline(10)


@pytest.mark.parametrize("values", [[], [5.0]])
def test_sparkline_degenerate_series(values):
    rendered = sparkline(values, 10)
    assert rendered in ("", SPARK_CHARS[len(SPARK_CHARS) // 2])


def test_sparkline_maps_low_to_high():
    rendered = sparkline([1.0, 2.0, 3.0], 10)
    assert len(rendered) == 3
    assert rendered[0] == SPARK_CHARS[0]
    assert rendered[-1] == SPARK_CHARS[-1]


def test_sparkline_constant_series_uses_middle_char():
    assert sparkline([7.0] * 6, 6) == SPARK_CHARS[len(SPARK_CHARS) // 2] * 6


def test_sparkline_pools_long_series_and_keeps_peak():
    # 100 values, one spike in the middle; pooling must not flatten the peak.
    values = [0.0] * 50 + [100.0] + [0.0] * 49
    rendered = sparkline(values, 10)
    assert len(rendered) == 10
    assert rendered.count(SPARK_CHARS[-1]) >= 1


def test_sparkline_rejects_non_positive_width():
    with pytest.raises(ValueError):
        sparkline([1.0], 0)


def test_sparkline_accepts_custom_ramp():
    ramp = ".:-=+*#@"
    rendered = sparkline([1.0, 2.0, 3.0], 10, ramp)
    assert set(rendered) <= set(ramp)
    assert rendered.endswith(ramp[-1])


def test_collector_groups_channels_and_ignores_plain_text():
    collector = StatsCollector()
    collector.add_lines(
        [
            "boot complete",
            "temp=20.0C hum=40.0%",
            "[INFO] tick=1 temp=22.0C",
        ]
    )
    assert len(collector) == 3
    names = [channel.name for channel in collector.sorted_channels()]
    assert names == ["hum", "temp", "tick"]
    temp = collector.channels["temp"]
    assert temp.count == 2
    assert temp.last == 22.0


def test_collector_add_uses_parse_samples():
    collector = StatsCollector()
    collector.add(parse_samples("temp=1.5C"))
    assert collector.channels["temp"].count == 1


def test_to_json_is_valid_and_stable():
    collector = StatsCollector()
    collector.add_lines(["temp=1.0C", "temp=3.0C"])
    payload = json.loads(collector.to_json())
    assert payload["channels"][0]["channel"] == "temp"
    assert payload["channels"][0]["mean"] == pytest.approx(2.0)
    assert json.loads(collector.to_json()) == payload


def test_write_csv(tmp_path):
    collector = StatsCollector()
    collector.add_lines(["temp=1.0C", "hum=50%"])
    target = tmp_path / "stats.csv"
    rows = collector.write_csv(str(target))

    assert rows == 2
    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        records = list(reader)
    assert [record["channel"] for record in records] == ["hum", "temp"]
    assert reader.fieldnames == list(CSV_FIELDS)


def test_mean_is_finite_for_empty_channel():
    assert math.isfinite(ChannelStats("x").mean)


def test_stdev_survives_a_large_offset():
    # Regression test: the previous sum-of-squares formula lost every digit of
    # the variance at this magnitude and reported stdev == 0.0 for a signal
    # that is clearly moving (ADC counts and microsecond timestamps live here).
    channel = ChannelStats("adc")
    for value in (1e8, 1e8 + 1, 1e8, 1e8 + 1):
        channel.add(value)
    assert channel.mean == pytest.approx(1e8 + 0.5)
    assert channel.stdev == pytest.approx(0.5, abs=1e-9)


def test_percentiles_interpolate_linearly():
    channel = ChannelStats("x")
    for value in range(1, 11):
        channel.add(float(value))
    assert channel.percentile(0.0) == 1.0
    assert channel.percentile(1.0) == 10.0
    assert channel.p50 == pytest.approx(5.5)
    assert channel.p95 == pytest.approx(9.55)


def test_percentiles_of_an_empty_channel_are_zero():
    channel = ChannelStats("x")
    assert channel.p50 == 0.0
    assert channel.p95 == 0.0


def test_percentile_window_is_bounded_and_trailing():
    channel = ChannelStats("x")
    for value in range(5000):
        channel.add(float(value))
    assert len(channel.window) == PERCENTILE_WINDOW
    # Trailing window: the early samples have been evicted on purpose.
    assert channel.p95 > 4000


def test_as_dict_exposes_percentiles():
    channel = ChannelStats("x")
    for value in (1.0, 2.0, 3.0):
        channel.add(value)
    data = channel.as_dict()
    assert list(data) == list(CSV_FIELDS)
    assert data["p50"] == pytest.approx(2.0)
    assert data["p95"] == pytest.approx(2.9)