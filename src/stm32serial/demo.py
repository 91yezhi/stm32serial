"""Synthetic telemetry, so ``stm32serial demo`` works without a board.

The generator is seeded and deterministic, which is what lets the test suite
assert on its output and lets reviewers replay the README examples exactly.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator

__all__ = ["synthetic_lines"]


def synthetic_lines(count: int = 0, seed: int = 7) -> Iterator[str]:
    """Yield fake sensor lines; ``count <= 0`` means "forever".

    The shapes are deliberately realistic: a slow sine for temperature, a
    half-frequency sine for humidity, small noise on the supply rail, plus
    occasional WARN/ERROR lines so level filtering is demonstrable.
    """
    rng = random.Random(seed)
    index = 0
    while count <= 0 or index < count:
        phase = index * 0.35
        temperature = 25.0 + 2.5 * math.sin(phase) + rng.uniform(-0.4, 0.4)
        humidity = 41.0 + 5.0 * math.sin(phase / 2.0 + 1.0) + rng.uniform(-0.6, 0.6)
        vbus = 3.30 + rng.uniform(-0.02, 0.02)

        payload = f"temp={temperature:.2f}C hum={humidity:.2f}% vbus={vbus:.3f}V"
        if index and index % 29 == 0:
            yield f"[ERROR] uart overrun, {rng.randint(1, 3)} sample(s) dropped"
        elif index and index % 13 == 0:
            yield f"[WARN] tick={index} {payload}"
        elif index and index % 7 == 0:
            yield f"[INFO] tick={index} {payload}"
        else:
            yield payload
        index += 1