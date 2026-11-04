"""Line parsing for the ``name=value`` telemetry that most STM32 firmwares print.

Everything in this module is pure: no I/O, no globals, no hardware.  That is
what makes the interesting parts of the tool testable on a CI runner without a
board attached.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# Severity order, cheapest first.  ``severity_of`` returns the index in this
# tuple so that ``--level`` can filter "this level or worse".
LEVELS = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")
SEVERITY = {name: index for index, name in enumerate(LEVELS)}

# Firmware rarely spells the level twice the same way; accept the usual aliases
# and normalise them so downstream code only ever sees LEVELS entries.
_ALIASES = {"WARNING": "WARN", "ERR": "ERROR", "CRIT": "FATAL"}

_LEVEL_TOKEN = r"(TRACE|DEBUG|INFO|WARNING|WARN|ERROR|FATAL|ERR|CRIT)"

# ``[INFO] ...``, ``<warn> ...`` and ``(ERROR) ...``
_BRACKETED_LEVEL = re.compile(r"[\[<(]\s*" + _LEVEL_TOKEN + r"\s*[\])>]", re.IGNORECASE)
# ``INFO: ...`` and ``ERROR - ...`` at the start of a line
_PREFIX_LEVEL = re.compile(r"^\s*" + _LEVEL_TOKEN + r"\s*[:\-]", re.IGNORECASE)

# ``temp=25.5C``, ``hum: 41 %``, ``vbus=3.3``.
#
# * the lookbehind keeps identifiers such as ``uart1_rx`` intact,
# * the unit group refuses to swallow the next pair's key (``a=1 b=2``), which
#   is why it is tied to the value with no whitespace in between,
# * scientific notation is accepted because ADC dumps often use it.
_SAMPLE = re.compile(
    r"(?<![\w.])"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_./\-]{0,31})"
    r"\s*[:=]\s*"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"\s*(?P<unit>(?![A-Za-z0-9_]*\s*[:=])[A-Za-z%\u00b0][A-Za-z0-9%/\u00b0^_\-]{0,9})?"
)


@dataclass(frozen=True)
class Sample:
    """A single numeric reading extracted from one line."""

    name: str
    value: float
    unit: str | None = None


def parse_samples(line: str) -> list[Sample]:
    """Extract every ``name=value[unit]`` pair found in *line*.

    Unparseable fragments are ignored instead of raising, because a serial line
    is a stream of mixed log text and telemetry: dropping the noise is the
    whole point.
    """
    samples: list[Sample] = []
    for match in _SAMPLE.finditer(line):
        raw = match.group("value")
        try:
            value = float(raw)
        except ValueError:  # pragma: no cover - the regex only emits valid floats
            continue
        samples.append(Sample(match.group("name"), value, match.group("unit")))
    return samples


def iter_samples(lines: Iterable[str]) -> Iterator[Sample]:
    """Yield samples from an iterable of lines."""
    for line in lines:
        yield from parse_samples(line)


def level_of(line: str) -> str | None:
    """Return the normalised log level of *line*, or ``None`` if it has none."""
    for pattern in (_BRACKETED_LEVEL, _PREFIX_LEVEL):
        match = pattern.search(line)
        if match:
            token = match.group(1).upper()
            return _ALIASES.get(token, token)
    return None


def severity_of(level: str) -> int:
    """Numeric severity for *level*; unknown levels are treated as the lowest."""
    return SEVERITY.get(level.upper(), SEVERITY["TRACE"])