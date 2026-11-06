"""Binary frame decoding for UART links that do not speak plain text.

Many STM32 designs send a compact binary protocol instead of ``printf``
lines: a sync word, a message id, a length, the payload and a checksum.  A
UART gives no message boundaries, so the receiver has to find frames in a
byte stream that may start mid-frame, lose bytes or pick up line noise.

Wire format decoded here (one byte each, little-endian CRC):

    +--------+--------+--------+--------+---------+--------+--------+
    | 0xA5   | 0x5A   | msg_id | length | payload | crc_lo | crc_hi |
    +--------+--------+--------+--------+---------+--------+--------+

``length`` counts payload bytes only, so a frame occupies ``6 + length``
bytes.  ``crc_lo``/``crc_hi`` are the CRC-16/CCITT-FALSE of everything from
``msg_id`` through the last payload byte (polynomial 0x1021, init 0xFFFF, no
reflection, no final xor).

The decoder is a resynchronising state machine: a bad checksum costs one
byte, not the rest of the stream, so a single flipped bit does not make the
receiver blind until the next reset.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "MAGIC",
    "Frame",
    "FrameDecoder",
    "crc16",
    "encode_frame",
]

MAGIC = b"\xa5\x5a"

#: Bytes in a frame that are not payload (sync + id + length + crc).
OVERHEAD = 6


def _build_crc_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        value = byte << 8
        for _ in range(8):
            value = ((value << 1) ^ 0x1021) & 0xFFFF if value & 0x8000 else (value << 1) & 0xFFFF
        table.append(value)
    return tuple(table)


_CRC_TABLE = _build_crc_table()


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection."""
    crc = 0xFFFF
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC_TABLE[((crc >> 8) ^ byte) & 0xFF]
    return crc


def encode_frame(msg_id: int, payload: bytes = b"") -> bytes:
    """Build one frame; useful for tests, demos and firmware-side parity."""
    if not 0 <= msg_id <= 0xFF:
        raise ValueError(f"msg_id must fit in one byte, got {msg_id!r}")
    if len(payload) > 0xFF:
        raise ValueError(f"payload must be at most 255 bytes, got {len(payload)}")
    body = bytes((msg_id, len(payload))) + bytes(payload)
    checksum = crc16(body)
    return MAGIC + body + bytes((checksum & 0xFF, checksum >> 8))


@dataclass(frozen=True)
class Frame:
    """One decoded, checksum-verified frame."""

    sequence: int
    msg_id: int
    payload: bytes
    raw: bytes

    @property
    def length(self) -> int:
        return len(self.payload)

    @property
    def text(self) -> str | None:
        """Payload as text when it is printable UTF-8, otherwise ``None``."""
        try:
            decoded = self.payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return decoded if decoded.isprintable() else None


class FrameDecoder:
    """Incremental frame decoder that tolerates noise, truncation and resync."""

    def __init__(self, magic: bytes = MAGIC) -> None:
        self.magic = bytes(magic)
        if len(self.magic) < 1:
            raise ValueError("magic must not be empty")
        self._buffer = bytearray()
        self.frames_ok = 0
        self.crc_errors = 0
        self.discarded = 0

    @property
    def pending(self) -> bytes:
        """Bytes buffered but not yet forming a complete frame."""
        return bytes(self._buffer)

    def counters(self) -> dict[str, int]:
        return {
            "frames": self.frames_ok,
            "crc_errors": self.crc_errors,
            "discarded_bytes": self.discarded,
            "pending_bytes": len(self._buffer),
        }

    def feed(self, data: bytes) -> list[Frame]:
        """Consume *data* and return every frame that completed."""
        self._buffer.extend(data)
        frames: list[Frame] = []
        buf = self._buffer

        while True:
            start = buf.find(self.magic)
            if start < 0:
                # No sync word: keep only the tail that could be a partial one.
                keep = len(self.magic) - 1
                if len(buf) > keep:
                    self.discarded += len(buf) - keep
                    del buf[: len(buf) - keep]
                return frames

            if start:
                self.discarded += start
                del buf[:start]

            if len(buf) < 4:  # magic + msg_id + length
                return frames

            length = buf[3]
            total = OVERHEAD + length
            if len(buf) < total:
                return frames

            body = bytes(buf[2 : 4 + length])
            checksum = buf[4 + length] | (buf[5 + length] << 8)
            if crc16(body) == checksum:
                self.frames_ok += 1
                frames.append(
                    Frame(
                        sequence=self.frames_ok,
                        msg_id=buf[2],
                        payload=bytes(buf[4 : 4 + length]),
                        raw=bytes(buf[:total]),
                    )
                )
                del buf[:total]
            else:
                # One byte of slip, then hunt again: the real header may be
                # buried inside what we just guessed was a payload.
                self.crc_errors += 1
                self.discarded += 1
                del buf[:1]