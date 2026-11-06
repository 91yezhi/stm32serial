"""stm32serial - a tiny, testable CLI toolkit for STM32 serial telemetry.

The public helpers are re-exported here so that the parsers, the statistics
engine and the binary frame decoder can be used as a library from your own
scripts:

    >>> from stm32serial import StatsCollector, parse_samples
    >>> collector = StatsCollector()
    >>> collector.add(parse_samples("temp=25.5C hum=41%"))
    >>> collector.channels["temp"].last
    25.5

    >>> from stm32serial import FrameDecoder, encode_frame
    >>> FrameDecoder().feed(encode_frame(0x01, b"boot"))[0].text
    'boot'
"""

from .framing import MAGIC, Frame, FrameDecoder, crc16, encode_frame
from .parser import LEVELS, Sample, level_of, parse_samples, severity_of
from .stats import ChannelStats, StatsCollector, percentile, sparkline

__all__ = [
    "LEVELS",
    "MAGIC",
    "ChannelStats",
    "Frame",
    "FrameDecoder",
    "Sample",
    "StatsCollector",
    "crc16",
    "encode_frame",
    "level_of",
    "parse_samples",
    "percentile",
    "severity_of",
    "sparkline",
]

__version__ = "0.2.0"