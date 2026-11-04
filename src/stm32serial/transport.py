"""Byte sources: real serial ports, log files, and the abstraction between them.

``pyserial`` is imported lazily so that file-based usage (and the test suite)
works on machines where the serial backend is unavailable.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from pathlib import Path

__all__ = ["SourceError", "FileSource", "SerialSource", "open_source", "parse_target"]


class SourceError(RuntimeError):
    """Raised when a target cannot be opened; surfaced to the user as an error."""


_SERIAL_PREFIXES = ("com", "/dev/tty", "/dev/cu.", "/dev/serial", "\\\\.\\com")


def parse_target(spec: str, default_baud: int = 115200) -> tuple:
    """Split ``"COM5@115200"`` into ``("serial", "COM5", 115200)``.

    A target without a recognised port prefix is treated as a file path, so
    ``stm32serial read logs/run1.log`` works with no extra flags.
    """
    spec = spec.strip()
    if not spec:
        raise SourceError("empty target")

    baud = default_baud
    if "@" in spec:
        head, _, tail = spec.rpartition("@")
        if head and tail.isdigit():
            spec, baud = head, int(tail)

    lowered = spec.lower()
    if lowered.startswith(_SERIAL_PREFIXES):
        return "serial", spec, baud
    return "file", spec, baud


class FileSource:
    """Yields lines from a log file, optionally following it like ``tail -f``."""

    def __init__(self, path: str, follow: bool = False, poll_interval: float = 0.2) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise SourceError(f"file not found: {path}")
        if self.path.is_dir():
            raise SourceError(f"target is a directory: {path}")
        self.follow = follow
        self.poll_interval = poll_interval

    def lines(self) -> Iterator[str]:
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            while True:
                line = handle.readline()
                if line:
                    yield line.rstrip("\r\n")
                    continue
                if not self.follow:
                    return
                time.sleep(self.poll_interval)

    def close(self) -> None:
        """Nothing to release; the file is closed when the generator ends."""


class SerialSource:
    """Yields decoded lines from a UART exposed as a serial port."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.2) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None

    def _open(self):
        try:
            import serial  # imported here: file mode must work without pyserial
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise SourceError(
                "pyserial is required for serial ports: pip install pyserial"
            ) from exc
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        except Exception as exc:  # serial.SerialException and friends
            raise SourceError(
                f"cannot open serial port {self.port!r} at {self.baudrate} baud: {exc}"
            ) from exc
        return self._serial

    def lines(self) -> Iterator[str]:
        handle = self._serial if self._serial is not None else self._open()
        try:
            while True:
                raw = handle.readline()
                if not raw:
                    continue  # read timeout: keep waiting, Ctrl-C stops the loop
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
        finally:
            self.close()

    def close(self) -> None:
        if self._serial is not None:
            with contextlib.suppress(Exception):
                self._serial.close()
            self._serial = None


def open_source(spec: str, baudrate: int = 115200, follow: bool = False):
    """Open *spec* (a port such as ``COM5`` or a file path) as a line source."""
    kind, target, baud = parse_target(spec, baudrate)
    if kind == "serial":
        return SerialSource(target, baud)
    return FileSource(target, follow=follow)