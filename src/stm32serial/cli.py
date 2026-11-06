"""Command line interface: ``read``, ``stats``, ``frames`` and ``demo``.

Exit codes: ``0`` success, ``1`` user-facing error (missing file, unopenable
port, invalid pattern), ``130`` interrupted with Ctrl-C.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Iterable, Iterator, Sequence

from . import __version__
from .demo import synthetic_frames, synthetic_lines
from .framing import Frame, FrameDecoder
from .parser import LEVELS, level_of, severity_of
from .render import colorize, format_timestamp, render_table, supports_color
from .stats import SPARK_CHARS, StatsCollector
from .transport import SourceError, open_byte_source, open_source

PROG = "stm32serial"

_TS_MODES = ("elapsed", "clock", "off")
_COLOR_MODES = ("auto", "always", "never")

# Fallback ramp for terminals that cannot encode the unicode block glyphs.
_ASCII_SPARK = ".:-=+*#@"


def _spark_chars() -> str:
    """Pick a sparkline ramp that the current stdout encoding can represent."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        SPARK_CHARS.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return _ASCII_SPARK
    return SPARK_CHARS


def _compile_grep(pattern: str | None) -> re.Pattern[str] | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise SourceError(f"invalid --grep pattern {pattern!r}: {exc}") from exc


def _filter_lines(
    lines: Iterable[str],
    pattern: re.Pattern[str] | None,
    min_level: str | None,
) -> Iterator[str]:
    """Apply ``--grep`` and ``--level`` without materialising the stream."""
    threshold = severity_of(min_level) if min_level else None
    for line in lines:
        if pattern is not None and not pattern.search(line):
            continue
        if threshold is not None:
            level = level_of(line)
            if level is None or severity_of(level) < threshold:
                continue
        yield line


def _wants_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return supports_color(sys.stdout)


def _emit(
    line: str,
    ts_mode: str,
    started: float,
    use_color: bool,
) -> None:
    text = line
    if ts_mode != "off":
        text = f"{format_timestamp(time.monotonic() - started, ts_mode)} {text}"
    if use_color:
        text = colorize(text, level_of(line), True)
    print(text, flush=True)


def _open(target: str, baud: int, follow: bool):
    """Open a target, translating any unexpected failure into a SourceError."""
    try:
        return open_source(target, baud, follow=follow)
    except SourceError:
        raise
    except Exception as exc:  # pragma: no cover - defensive, keeps the CLI tidy
        raise SourceError(str(exc)) from exc


def _open_bytes(target: str, baud: int, follow: bool):
    """Same as :func:`_open`, but for the raw byte sources used by ``frames``."""
    try:
        return open_byte_source(target, baud, follow=follow)
    except SourceError:
        raise
    except Exception as exc:  # pragma: no cover - defensive, keeps the CLI tidy
        raise SourceError(str(exc)) from exc


def _num(value: object) -> str:
    if isinstance(value, float):
        text = f"{value:.3f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def cmd_read(args: argparse.Namespace) -> int:
    pattern = _compile_grep(args.grep)
    use_color = _wants_color(args.color)
    source = _open(args.target, args.baud, args.follow)
    seen = 0
    started = time.monotonic()
    try:
        for line in _filter_lines(source.lines(), pattern, args.level):
            _emit(line, args.ts, started, use_color)
            seen += 1
            if args.max_lines and seen >= args.max_lines:
                break
    finally:
        source.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    pattern = _compile_grep(args.grep)
    collector = StatsCollector()
    for target in args.targets:
        source = _open(target, args.baud, False)
        try:
            collector.add_lines(_filter_lines(source.lines(), pattern, args.level))
        finally:
            source.close()

    if not len(collector):
        print("no telemetry samples found", file=sys.stderr)
        return 0

    if args.csv:
        rows = collector.write_csv(args.csv)
        print(f"wrote {rows} row(s) to {args.csv}")
        return 0

    if args.json:
        print(collector.to_json())
        return 0

    headers = ["channel", "unit", "count", "min", "max", "mean", "stdev", "p50", "p95", "last"]
    if not args.no_sparkline:
        headers.append("trend")

    rows: list[list[object]] = []
    for channel in collector.sorted_channels():
        stats = channel.as_dict()
        row: list[object] = [
            stats["channel"],
            stats["unit"] or "-",
            stats["count"],
            _num(stats["min"]),
            _num(stats["max"]),
            _num(stats["mean"]),
            _num(stats["stdev"]),
            _num(stats["p50"]),
            _num(stats["p95"]),
            _num(stats["last"]),
        ]
        if not args.no_sparkline:
            row.append(channel.sparkline(args.width, _spark_chars()))
        rows.append(row)

    print(render_table(headers, rows))
    return 0


def _payload_text(frame: Frame, force_hex: bool) -> str:
    """Printable payload when possible, hex dump otherwise."""
    if not frame.payload:
        return "-"
    text = None if force_hex else frame.text
    if text is not None:
        return text
    return " ".join(f"{byte:02x}" for byte in frame.payload)


def _frame_chunks(args: argparse.Namespace) -> Iterator[bytes]:
    if args.demo:
        yield from synthetic_frames(args.demo, args.seed)
        return
    for target in args.targets:
        source = _open_bytes(target, args.baud, args.follow)
        try:
            yield from source.chunks()
        finally:
            source.close()


def cmd_frames(args: argparse.Namespace) -> int:
    if not args.demo and not args.targets:
        raise SourceError("frames needs a TARGET or --demo N")
    decoder = FrameDecoder()
    collected: list[Frame] = []
    for chunk in _frame_chunks(args):
        collected.extend(decoder.feed(chunk))
        if args.max_frames and len(collected) >= args.max_frames:
            collected = collected[: args.max_frames]
            break

    counters = decoder.counters()
    if args.json:
        print(
            json.dumps(
                {
                    "frames": [
                        {
                            "seq": frame.sequence,
                            "id": frame.msg_id,
                            "length": frame.length,
                            "payload_hex": frame.payload.hex(),
                            "payload_text": frame.text,
                        }
                        for frame in collected
                    ],
                    "stats": counters,
                },
                indent=2,
            )
        )
    else:
        headers = ["seq", "id", "len", "payload"]
        rows = [
            [frame.sequence, f"0x{frame.msg_id:02x}", frame.length, _payload_text(frame, args.hex)]
            for frame in collected
        ]
        if rows:
            print(render_table(headers, rows))
        print(
            f"{counters['frames']} frame(s), {counters['crc_errors']} crc error(s), "
            f"{counters['discarded_bytes']} byte(s) discarded, "
            f"{counters['pending_bytes']} byte(s) pending",
            file=sys.stderr,
        )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    use_color = _wants_color(args.color)
    started = time.monotonic()
    for line in synthetic_lines(args.count, args.seed):
        _emit(line, args.ts, started, use_color)
        if args.interval > 0:
            time.sleep(args.interval)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Read, filter and aggregate telemetry from an STM32 serial port or log file.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--ts",
            choices=_TS_MODES,
            default="elapsed",
            help="timestamp prefix: elapsed (+MM:SS.mmm), clock, or off (default: elapsed)",
        )
        sub.add_argument(
            "--color",
            choices=_COLOR_MODES,
            default="auto",
            help="ANSI colour for log levels (default: auto)",
        )

    read = subparsers.add_parser("read", help="stream lines (Ctrl-C to stop)")
    read.add_argument("target", help="COM5@115200, /dev/ttyUSB0, or a log file path")
    read.add_argument(
        "--baud", type=int, default=115200, help="baud rate when the target has no @baud"
    )
    read.add_argument("--grep", metavar="PATTERN", help="only print lines matching this regex")
    read.add_argument(
        "--level",
        choices=LEVELS,
        help="only print lines at this level or worse (lines without a level are skipped)",
    )
    read.add_argument(
        "--max-lines",
        type=int,
        default=0,
        metavar="N",
        help="stop after N lines (0 = unlimited)",
    )
    read.add_argument(
        "--follow", action="store_true", help="keep the file open and wait for new lines"
    )
    add_common(read)
    read.set_defaults(func=cmd_read)

    stats = subparsers.add_parser("stats", help="summarise every name=value channel")
    stats.add_argument(
        "targets", nargs="+", metavar="TARGET", help="one or more ports or log files"
    )
    stats.add_argument("--baud", type=int, default=115200, help="baud rate for serial targets")
    stats.add_argument("--grep", metavar="PATTERN", help="only consider lines matching this regex")
    stats.add_argument(
        "--level", choices=LEVELS, help="only consider lines at this level or worse"
    )
    stats.add_argument("--csv", metavar="PATH", help="write the table to a CSV file")
    stats.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    stats.add_argument("--no-sparkline", action="store_true", help="drop the trend column")
    stats.add_argument(
        "--width",
        type=int,
        default=40,
        metavar="COLS",
        help="sparkline width in characters (default: 40)",
    )
    stats.set_defaults(func=cmd_stats)

    frames = subparsers.add_parser(
        "frames", help="decode binary A5 5A frames with a CRC-16 checksum"
    )
    frames.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="a port (COM5@921600) or a binary capture file",
    )
    frames.add_argument("--baud", type=int, default=115200, help="baud rate for serial targets")
    frames.add_argument(
        "--demo",
        type=int,
        default=0,
        metavar="N",
        help="decode N synthetic frames instead of a target (0 = off)",
    )
    frames.add_argument(
        "--seed",
        type=int,
        default=7,
        help="random seed for --demo (default: 7)",
    )
    frames.add_argument("--hex", action="store_true", help="always render payloads as hex")
    frames.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    frames.add_argument(
        "--max-frames",
        type=int,
        default=0,
        metavar="N",
        help="stop after N frames (0 = unlimited)",
    )
    frames.add_argument(
        "--follow", action="store_true", help="keep a capture file open and wait for more bytes"
    )
    frames.set_defaults(func=cmd_frames)

    demo = subparsers.add_parser("demo", help="print synthetic telemetry (no board required)")
    demo.add_argument(
        "--count",
        type=int,
        default=0,
        metavar="N",
        help="number of lines to print (0 = forever)",
    )
    demo.add_argument(
        "--interval",
        type=float,
        default=0.0,
        metavar="SEC",
        help="seconds to sleep between lines",
    )
    demo.add_argument(
        "--seed",
        type=int,
        default=7,
        help="random seed for the generator (default: 7)",
    )
    add_common(demo)
    demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except SourceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 130
    except BrokenPipeError:  # e.g. ``stm32serial read ... | head``
        try:
            sys.stdout.close()
        except Exception:  # pragma: no cover - best effort during shutdown
            pass
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())