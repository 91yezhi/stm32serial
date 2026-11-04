"""stm32serial - a tiny, testable CLI toolkit for STM32 serial telemetry.

The public helpers are re-exported here so that the parsers and the statistics
engine can be used as a library from your own scripts:

    >>> from stm32serial import StatsCollector, parse_samples
    >>> collector = StatsCollector()
    >>> collector.add(parse_samples("temp=25.5C hum=41%"))
    >>> collector.channels["temp"].last
    25.5
"""

from .parser import LEVELS, Sample, level_of, parse_samples, severity_of
from .stats import ChannelStats, StatsCollector, sparkline

__all__ = [
    "LEVELS",
    "ChannelStats",
    "Sample",
    "StatsCollector",
    "level_of",
    "parse_samples",
    "severity_of",
    "sparkline",
]

__version__ = "0.1.0"