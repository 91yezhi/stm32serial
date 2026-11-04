"""Running statistics and the terminal sparkline renderer.

The collector keeps only O(channels) state plus a bounded ring buffer per
channel, so it can analyse an unbounded serial stream without growing memory.
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

# Column order shared by ``ChannelStats.as_dict`` and the CSV export.
CSV_FIELDS = ("channel", "unit", "count", "min", "max", "mean", "stdev", "first", "last")


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
    total: float = 0.0
    total_sq: float = 0.0
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=RECENT_WINDOW))

    def add(self, value: float, unit: str | None = None) -> None:
        if self.unit is None and unit:
            self.unit = unit
        if self.count == 0:
            self.first = value
        self.count += 1
        self.last = value
        self.total += value
        self.total_sq += value * value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.recent.append(value)

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0

    @property
    def stdev(self) -> float:
        """Population standard deviation (0 for a single sample)."""
        if self.count < 2:
            return 0.0
        variance = self.total_sq / self.count - self.mean ** 2
        return math.sqrt(max(variance, 0.0))

    def as_dict(self) -> dict[str, object]:
        return {
            "channel": self.name,
            "unit": self.unit or "",
            "count": self.count,
            "min": _trim(self.minimum) if self.count else 0.0,
            "max": _trim(self.maximum) if self.count else 0.0,
            "mean": _trim(self.mean),
            "stdev": _trim(self.stdev),
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