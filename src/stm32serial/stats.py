"""Running statistics and the terminal sparkline renderer.

The collector keeps only O(channels) state plus a bounded ring buffer per
channel, so it can analyse an unbounded serial stream without growing memory.

Mean and variance use Welford's online algorithm rather than ``sum`` /
``sum of squares``: telemetry often carries large offsets (ADC counts, micro-
second timestamps) where the naive formula loses every significant digit of
the variance and reports ``stdev = 0`` for a signal that clearly moves.
"""

from __future__ import annotations

import csv
import json
import math
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .parser import Sample, parse_samples

SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"  # ▁▂▃▄▅▆▇█

# How many recent values per channel are kept for the sparkline.  Bounded on
# purpose: a 115200 baud link can produce a few thousand samples per minute.
RECENT_WINDOW = 256

# How many recent values feed the p50/p95 estimates.  Percentiles need the
# samples themselves, so they are computed over this trailing window rather
# than over the whole stream; the window is wide enough for a stable p95 on
# the streams seen in practice while staying a few kilobytes per channel.
PERCENTILE_WINDOW = 1024

# Column order shared by ``ChannelStats.as_dict`` and the CSV export.
CSV_FIELDS = (
    "channel",
    "unit",
    "count",
    "min",
    "max",
    "mean",
    "stdev",
    "p50",
    "p95",
    "first",
    "last",
)


def sparkline(
    values: Sequence[float],
    width: int = 40,
    chars: str = SPARK_CHARS,
) -> str:
    """Render *values* as a fixed-width sparkline.

    Longer series are max-pooled into *width* buckets, which keeps peaks
    visible instead of averaging them away.  *chars* is the ramp used, lowest
    first: callers on terminals that cannot encode the unicode blocks pass an
    ASCII ramp such as ``".:-=+*#@"``.
    """
    if width <= 0:
        raise ValueError("width must be positive")
    if not values:
        return ""
    if len(chars) < 2:
        raise ValueError("chars must contain at least two symbols")

    data = list(values)
    if len(data) > width:
        bucket = len(data) / float(width)
        pooled: list[float] = []
        for index in range(width):
            start = int(index * bucket)
            end = max(start + 1, int((index + 1) * bucket))
            pooled.append(max(data[start:end]))
        data = pooled

    low, high = min(data), max(data)
    if math.isclose(low, high):
        return chars[len(chars) // 2] * len(data)

    span = high - low
    top = len(chars) - 1
    return "".join(chars[int((value - low) / span * top + 0.5)] for value in data)


def _trim(value: float, digits: int = 3) -> float:
    """Round for display without turning ``25.0`` into ``25.000``."""
    return round(value, digits)


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated percentile of an already small series.

    ``fraction`` is clamped to ``[0, 1]``; an empty series returns ``0.0``.
    This mirrors the type-7 definition used by numpy's default ``percentile``
    so numbers agree with the tools people reach for next.
    """
    if not values:
        return 0.0
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    fraction = min(max(fraction, 0.0), 1.0)
    position = (len(data) - 1) * fraction
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return data[low]
    weight = position - low
    return data[low] + (data[high] - data[low]) * weight


@dataclass
class ChannelStats:
    """Aggregate of one telemetry channel."""

    name: str
    unit: str | None = None
    count: int = 0
    minimum: float = math.inf
    maximum: float = -math.inf
    first: float = 0.0
    last: float = 0.0
    _mean: float = 0.0
    _m2: float = 0.0
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=RECENT_WINDOW))
    window: deque[float] = field(default_factory=lambda: deque(maxlen=PERCENTILE_WINDOW))

    def add(self, value: float, unit: str | None = None) -> None:
        if self.unit is None and unit:
            self.unit = unit
        if self.count == 0:
            self.first = value
        # Welford: one pass, no catastrophic cancellation on large offsets.
        self.count += 1
        delta = value - self._mean
        self._mean += delta / self.count
        self._m2 += delta * (value - self._mean)
        self.last = value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.recent.append(value)
        self.window.append(value)

    @property
    def mean(self) -> float:
        return self._mean if self.count else 0.0

    @property
    def stdev(self) -> float:
        """Population standard deviation (0 for a single sample)."""
        if self.count < 2:
            return 0.0
        return math.sqrt(max(self._m2 / self.count, 0.0))

    def percentile(self, fraction: float) -> float:
        """Percentile over the trailing ``PERCENTILE_WINDOW`` samples."""
        if not self.count:
            return 0.0
        return percentile(list(self.window), fraction)

    @property
    def p50(self) -> float:
        return self.percentile(0.50)

    @property
    def p95(self) -> float:
        return self.percentile(0.95)

    def as_dict(self) -> dict[str, object]:
        return {
            "channel": self.name,
            "unit": self.unit or "",
            "count": self.count,
            "min": _trim(self.minimum) if self.count else 0.0,
            "max": _trim(self.maximum) if self.count else 0.0,
            "mean": _trim(self.mean),
            "stdev": _trim(self.stdev),
            "p50": _trim(self.p50),
            "p95": _trim(self.p95),
            "first": _trim(self.first),
            "last": _trim(self.last),
        }

    def sparkline(self, width: int = 40, chars: str = SPARK_CHARS) -> str:
        return sparkline(list(self.recent), width, chars)


class StatsCollector:
    """Accumulates :class:`Sample` objects into per-channel aggregates."""

    def __init__(self) -> None:
        self.channels: dict[str, ChannelStats] = {}

    def add(self, samples: Iterable[Sample]) -> None:
        for sample in samples:
            channel = self.channels.get(sample.name)
            if channel is None:
                channel = self.channels[sample.name] = ChannelStats(sample.name)
            channel.add(sample.value, sample.unit)

    def add_line(self, line: str) -> None:
        self.add(parse_samples(line))

    def add_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.add_line(line)

    def __len__(self) -> int:
        return len(self.channels)

    def sorted_channels(self) -> list[ChannelStats]:
        """Channels that actually received samples, ordered by name."""
        channels = [channel for channel in self.channels.values() if channel.count > 0]
        return sorted(channels, key=lambda channel: channel.name)

    def rows(self) -> list[dict[str, object]]:
        return [channel.as_dict() for channel in self.sorted_channels()]

    def as_dict(self) -> dict[str, object]:
        return {"channels": self.rows()}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=False)

    def write_csv(self, path: str) -> int:
        """Write one row per channel; returns the number of rows written."""
        rows = self.rows()
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)