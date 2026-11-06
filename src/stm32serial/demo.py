"""Synthetic telemetry, so ``stm32serial demo`` works without a board.

The generator is seeded and deterministic, which is what lets the test suite
assert on its output and lets reviewers replay the README examples exactly.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator

from .framing import encode_frame

__all__ = ["synthetic_lines", "synthetic_frames"]

#: Message ids used by the synthetic firmware.
MSG_TELEMETRY = 0x01
MSG_STATUS = 0x02


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


def synthetic_frames(count: int = 0, seed: int = 7) -> Iterator[bytes]:
    """Yield a byte stream that looks like a noisy binary UART link.

    Each iteration emits one chunk.  The stream deliberately contains the
    things a real receiver has to survive: a truncated frame at the start, a
    frame with a corrupted checksum, and stray noise bytes between frames.
    That makes ``stm32serial frames --demo`` a demonstration of resync, not
    just of happy-path parsing.
    """
    rng = random.Random(seed)
    # Deliberately split across chunk boundaries: the decoder must buffer.
    yield encode_frame(MSG_STATUS, b"boot")[:4]
    yield encode_frame(MSG_STATUS, b"boot")[4:]

    index = 0
    while count <= 0 or index < count:
        phase = index * 0.35
        temperature = 25.0 + 2.5 * math.sin(phase) + rng.uniform(-0.4, 0.4)
        vbus = 3.30 + rng.uniform(-0.02, 0.02)
        payload = f"temp={temperature:.2f}C vbus={vbus:.3f}V".encode()
        stream = encode_frame(MSG_TELEMETRY, payload)

        if index and index % 11 == 0:
            # Flip a payload byte: the CRC must reject this frame.
            broken = bytearray(stream)
            broken[5] ^= 0xFF
            stream = bytes(broken)
        elif index and index % 5 == 0:
            # Line noise between frames.
            stream = bytes(rng.randrange(0, 0x7F) for _ in range(rng.randint(1, 3))) + stream

        yield stream
        index += 1