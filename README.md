# stm32serial

> Turn a UART into something that answers questions.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-111%20passed-brightgreen)](tests/)
[![Lint](https://img.shields.io/badge/lint-ruff-000000)](https://docs.astral.sh/ruff/)

A tiny command-line toolkit for STM32 serial telemetry. It reads a live UART or
a captured log, filters it by log level, and aggregates every `name=value`
channel into min / max / mean / stdev / p50 / p95 with a sparkline trend — then
exports JSON or CSV when you need to keep the numbers. Binary protocols are
covered too: a resynchronising frame decoder turns length-prefixed, CRC-checked
packets into the same table.

The interesting part is not the CLI. It is that **every piece of logic is
testable without a board**: the hardware sits behind two tiny interfaces
(`lines()` and `chunks()`), so the parsers, the statistics engine, the frame
decoder, the renderer and the CLI are all exercised by the test suite on any CI
runner.

```
$ stm32serial stats examples/sample_log.txt
channel  unit  count    min    max    mean   stdev     p50     p95   last                                     trend
hum     %     60  35.87  45.95  41.474    3.37  42.105  45.901  45.91  ▅▅▅▆▆▆▆▇▇███████▇▇▆▅▄▄▃▃▂▂▁▁▁▁▁▂▂▃▄▅▅▆▇█
temp     C     60  23.14  29.64  26.742   2.121  26.865  29.495  29.49  ▃▄▄▅▅▅▆▇▇▇███▇▇▆▆▅▄▄▃▂▂▁▁▁▁▂▂▃▃▄▅▆▇▇████
tick     -     60      0     59    29.5  17.318    29.5   56.05     59  ▁▁▁▂▂▂▂▂▂▃▃▃▃▃▃▄▄▄▄▄▅▅▅▅▅▆▆▆▆▆▆▇▇▇▇▇▇███
vbus     V     60  3.297  3.306   3.301   0.002   3.301   3.305  3.303  ▃▅▇▆▄█▄▆▁▅▄▆▃▇▁▆▄▅▃█▁▅▆▄▆▅▂▇▃▆▃▆▃▇▂▆▃▆▄▆
```

No config file, no daemon, one dependency (`pyserial`), and a `demo` command
that produces realistic telemetry so you can try everything before you plug in
a board.

## Why this exists

Firmware usually prints its state like this:

```
[INFO] tick=42 temp=26.53C hum=43.10% vbus=3.301V
```

Which is great until you ask "what is the temperature doing?". Then you are
grepping a wall of text, and the answer is still a number you have to squint
at. `stm32serial` answers the question directly:

```console
$ stm32serial read COM5@115200 --level WARN
+00:00.000 [WARN] tick=12 temp=28.70C hum=44.83% vbus=3.297V
+00:03.284 [ERROR] uart overrun, 3 sample(s) dropped
```

...and when you want the summary instead of the stream:

```console
$ stm32serial stats COM5@115200 --grep temp
channel  unit  count    min    max    mean   stdev     p50     p95   last                                     trend
temp     C     60  23.14  29.64  26.742   2.121  26.865  29.495  29.49  ▃▄▄▅▅▅▆▇▇▇███▇▇▆▆▅▄▄▃▂▂▁▁▁▁▂▂▃▃▄▅▆▇▇████
```

## Install

Not on PyPI yet — install from source:

```bash
git clone https://github.com/91yezhi/stm32serial.git
cd stm32serial
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev]"
```

Python 3.9 or newer. `pyserial` is installed with the package; the development
extra adds `pytest` and `ruff`.

## 60-second tour

Start with synthetic data — no board, no port, no permissions:

```console
$ stm32serial demo --count 12
+00:00.000 temp=24.86C hum=44.79% vbus=3.306V
+00:00.000 temp=25.52C hum=45.66% vbus=3.295V
+00:00.000 temp=26.26C hum=45.89% vbus=3.281V
+00:00.000 temp=27.12C hum=45.48% vbus=3.284V
+00:00.000 temp=27.40C hum=46.35% vbus=3.285V
+00:00.000 temp=27.24C hum=45.92% vbus=3.318V
+00:00.000 temp=27.22C hum=45.31% vbus=3.319V
+00:00.000 [INFO] tick=7 temp=26.23C hum=45.40% vbus=3.292V
+00:00.000 temp=25.55C hum=43.92% vbus=3.292V
+00:00.000 temp=25.23C hum=43.30% vbus=3.303V
+00:00.000 temp=24.23C hum=42.76% vbus=3.302V
+00:00.000 temp=23.02C hum=41.55% vbus=3.288V
```

Pipe it, colour it, throttle it — `--ts off`, `--ts clock`, `--color always`,
`--interval 0.1`, `--count 0` all work the way you expect.

Filter a captured log (the repository ships `examples/sample_log.txt`):

```console
$ stm32serial read examples/sample_log.txt --level WARN --ts off
[WARN] tick=12 temp=28.70C hum=44.83% vbus=3.297V
[WARN] tick=21 temp=28.57C hum=45.58% vbus=3.297V
[WARN] tick=28 temp=25.63C hum=42.24% vbus=3.306V
[ERROR] uart overrun, 3 sample(s) dropped
[WARN] tick=36 temp=23.17C hum=37.19% vbus=3.303V
[WARN] tick=45 temp=25.36C hum=36.42% vbus=3.299V
[ERROR] uart overrun, 1 sample(s) dropped
[WARN] tick=56 temp=29.60C hum=43.69% vbus=3.304V
```

Summarise it, as a table, as JSON, or as a CSV you can drop into a notebook:

```console
$ stm32serial stats examples/sample_log.txt --json
{
  "channels": [
    {
      "channel": "hum",
      "unit": "%",
      "count": 60,
      "min": 35.87,
      "max": 45.95,
      "mean": 41.474,
      "stdev": 3.37,
      "p50": 42.105,
      "p95": 45.901,
      "first": 41.0,
      "last": 45.91
    }
  ]
}

$ stm32serial stats examples/sample_log.txt --csv run1.csv
wrote 4 row(s) to run1.csv
```

## Binary frames

Not every link prints text. Many designs send a compact packet: sync word,
message id, length, payload, CRC. `stm32serial frames` decodes that stream —
and because a UART gives no message boundaries, the decoder resynchronises after
noise, truncation and checksum errors instead of giving up.

The wire format is deliberately simple, so firmware can generate it without a
library:

```
+--------+--------+--------+--------+---------+--------+--------+
| 0xA5   | 0x5A   | msg_id | length | payload | crc_lo | crc_hi |
+--------+--------+--------+--------+---------+--------+--------+
```

`length` counts payload bytes only, so a frame occupies `6 + length` bytes; the
checksum is CRC-16/CCITT-FALSE (poly `0x1021`, init `0xFFFF`) over `msg_id`,
`length` and the payload, little-endian on the wire.

```console
$ stm32serial frames --demo 6
seq    id  len                  payload
1  0x02    4                     boot
2  0x01   23  temp=24.86C vbus=3.286V
3  0x01   23  temp=25.98C vbus=3.283V
4  0x01   23  temp=26.64C vbus=3.295V
5  0x01   23  temp=26.81C vbus=3.300V
6  0x01   23  temp=27.09C vbus=3.297V
7  0x01   23  temp=27.12C vbus=3.284V
12 frame(s), 0 crc error(s), 2 byte(s) discarded, 0 byte(s) pending
```

The demo stream is hostile on purpose: the first frame is split across two
writes, occasional garbage bytes precede a frame, and every eleventh packet has
a flipped payload byte. The summary line reports what the decoder had to
survive:

```console
$ stm32serial frames --demo 12
...
12 frame(s), 1 crc error(s), 32 byte(s) discarded, 1 byte(s) pending
```

Decode a capture, or stream from the board, and switch the payload rendering
(the repository ships `examples/sample_frames.bin`, which contains a boot frame,
four telemetry frames, a corrupted frame and one non-text payload):

```console
$ stm32serial frames examples/sample_frames.bin
seq    id  len      payload
1  0x02    4         boot
2  0x01   11  temp=24.86C
3  0x01   11  temp=25.98C
4  0x01   11  temp=26.64C
5  0x01   11  temp=26.81C
6  0x03    3     00 01 02
6 frame(s), 1 crc error(s), 19 byte(s) discarded, 0 byte(s) pending

$ stm32serial frames capture.bin --json
$ stm32serial frames COM5@115200 --hex          # always show hex
$ stm32serial frames COM5@115200 --max-frames 20
```

Payloads that are printable UTF-8 are shown as text; anything else as
space-separated hex. `--json` emits `{"frames": [...], "stats": {...}}` with
`seq`, `id`, `length`, `payload_hex`, `payload_text` and the decoder counters —
handy for piping into `jq` or a notebook.

## Commands

### `stm32serial read TARGET`

| Option | Meaning |
| --- | --- |
| `TARGET` | `COM5`, `COM5@115200`, `/dev/ttyUSB0`, `/dev/ttyACM0@230400`, or a log file path |
| `--baud` | Baud rate when the target has no `@baud` suffix (default `115200`) |
| `--grep PATTERN` | Regular expression, case-insensitive |
| `--level LEVEL` | Keep this level or worse; lines without a level are dropped |
| `--max-lines N` | Stop after N lines (`0` = unlimited) |
| `--follow` | Keep a log file open and print lines as they arrive (`tail -f`) |
| `--ts elapsed\|clock\|off` | `+MM:SS.mmm` (default), local wall clock, or no prefix |
| `--color auto\|always\|never` | ANSI colours for levels; `auto` honours `NO_COLOR` / `FORCE_COLOR` |

### `stm32serial stats TARGET [TARGET ...]`

Aggregates every telemetry channel across one or more targets (a later target
continues the same accumulator, which is how you combine several captures).

| Option | Meaning |
| --- | --- |
| `--grep`, `--level` | Same filters as `read` |
| `--json` | Machine-readable output |
| `--csv PATH` | Write the table to CSV and report the row count |
| `--no-sparkline` | Drop the `trend` column |
| `--width COLS` | Sparkline width (default 40) |

Statistics: count, min, max, mean, population standard deviation, p50, p95,
first value, last value. Mean and stdev use Welford's online algorithm, so a
large offset (`1e8 ± 1` ADC counts) does not eat the variance — a naive
sum-of-squares implementation reports `stdev = 0` there. Memory stays
O(channels): the last 256 values per channel are kept for the sparkline, and the
last 1024 for the percentiles.

### `stm32serial frames TARGET [TARGET ...]`

Decodes binary frames (see [Binary frames](#binary-frames)) from a capture or a
live port.

| Option | Meaning |
| --- | --- |
| `--demo N` | Generate a deliberately messy synthetic stream instead of reading a target |
| `--seed N` | Seed for `--demo` (default `7`) |
| `--hex` | Show every payload as hex, even printable ones |
| `--json` | `{"frames": [...], "stats": {...}}` instead of a table |
| `--max-frames N` | Stop after N decoded frames (`0` = unlimited) |
| `--baud`, `--follow` | Same as `read` |

### `stm32serial demo`

`--count N`, `--interval SEC`, `--seed N`, plus the shared `--ts` / `--color`
flags. Deterministic for a given seed, so examples and tests are reproducible.

Targets that start with `com`, `/dev/tty`, `/dev/cu.`, `/dev/serial` or `\\.\com`
are treated as serial ports; anything else is a file path.

## Supported formats

Log levels are recognised in several shapes and normalised before filtering:

| Written as | Detected |
| --- | --- |
| `[INFO] ...`, `<warn> ...`, `(ERROR) ...` | bracketed token anywhere in the line |
| `INFO: ...`, `ERROR - ...` | leading token |
| `WARNING`, `ERR`, `CRIT` | normalised to `WARN`, `ERROR`, `FATAL` |

Order: `TRACE < DEBUG < INFO < WARN < ERROR < FATAL`.

Telemetry is any `name=value[unit]` or `name: value[unit]` pair, several per
line, and it coexists with prose:

| Line | Channels |
| --- | --- |
| `temp=25.50C hum=41.00%` | `temp=25.5 C`, `hum=41.0 %` |
| `[INFO] tick=7 vbus=3.300V` | `tick=7`, `vbus=3.3 V` |
| `gain=1.5e-3 offset=-12.5v` | scientific notation and signs |
| `uart1_rx=1` | identifiers keep their underscores |
| `a=1 b=2` | two channels — the unit never swallows the next key |
| `boot complete` | nothing; plain text is ignored |

## Use it as a library

The parsers and the collector are plain functions and dataclasses:

```python
from stm32serial import StatsCollector, parse_samples

collector = StatsCollector()
collector.add(parse_samples("temp=25.5C hum=41%"))
collector.add(parse_samples("temp=26.5C hum=43%"))

temp = collector.channels["temp"]
print(temp.mean, temp.stdev, temp.p50, temp.p95, temp.sparkline(20))
print(collector.to_json())
```

`stm32serial.transport.open_source()` gives you the same `lines()` iterator the
CLI uses, and `open_byte_source()` the `chunks()` one, so a custom script needs
no new I/O code. The frame decoder is equally usable on its own:

```python
from stm32serial import FrameDecoder, encode_frame

decoder = FrameDecoder()
frames = decoder.feed(encode_frame(0x01, b"temp=25.5C"))
print(frames[0].msg_id, frames[0].text, decoder.counters())
```

## Design: testable without hardware

```
                 ┌──────────────┐
  read / stats ──►  transport   │──lines()──► parser ──► stats ──► render
                 └──────────────┘
                   ├── FileSource       (tests, captured logs, --follow)
                   └── SerialSource     (pyserial, imported lazily)

                 ┌──────────────┐
       frames ──►│   transport   │──chunks()──► framing ──► cli table / json
                 └──────────────┘
                   ├── FileByteSource   (captures, --follow)
                   └── SerialByteSource (pyserial, imported lazily)
```

* `transport` is the only module that touches the outside world.
* `parser`, `stats`, `framing` and `render` are pure: no globals, no I/O, no clock.
* The CLI is tested end-to-end through `main(argv)` with temporary log files
  and `capsys`, so argument handling, exit codes and formatting are covered.

That is why `pytest` needs no serial port, no board, and no network: 111 tests
run in about 0.4 s.

| Area | What the tests pin down |
| --- | --- |
| parser | unit lookahead (`a=1 b=2`), scientific notation, level aliases, level ordering |
| stats | population stdev, Welford stability at `1e8`, percentile interpolation, bounded buffers, CSV/JSON shape |
| framing | CRC check value, split frames, garbage, CRC-error resync, payload containing the magic, truncation |
| render | timestamp rollover, `NO_COLOR`/`FORCE_COLOR`, right-aligned numeric columns |
| transport | target parsing, missing file/directory, CRLF, `--follow`, open failures |
| cli | filters, exit codes, `--json`/`--csv`/`--max-lines`, missing samples, `frames` demo/capture/`--hex` |

## Troubleshooting

**`cannot open serial port 'COM5'`** — the port is busy (close the Arduino IDE,
a serial monitor, or another terminal) or the name is wrong. On Linux, add
yourself to the `dialout` group; on macOS look for `/dev/cu.usbserial-*`.

**`pyserial is required for serial ports`** — the package was installed without
dependencies: `pip install pyserial`.

**The sparkline looks like `␣␣␣` or `?:`** — your console encoding cannot render
the unicode block glyphs, so the tool falls back to an ASCII ramp
(`.:-=+*#@`). Set `PYTHONIOENCODING=utf-8` (and use Windows Terminal) for the
pretty version. `--no-sparkline` removes the column entirely.

**Colours in a log file** — colours are auto-detected; force them off with
`--color never` or `NO_COLOR=1`.

**Empty `stats` output** — nothing matched the telemetry grammar. Check the
format with `stm32serial read YOUR_LOG --max-lines 20`; samples need a
`name=value` pair, and `--level` drops lines that have no level at all.

**`frames` prints nothing** — the stream has no `0xA5 0x5A` sync word, so it is
not using this wire format. Check with
`stm32serial read YOUR_LOG --max-lines 20` whether the device is printing text
instead, and inspect the summary line: a large `pending` count means a frame
header was seen but the rest never arrived (baud rate or `length` mismatch).

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 111 tests
ruff check .       # lint + import order
```

```
src/stm32serial/
  parser.py     name=value + log level parsing
  stats.py      aggregates (Welford + percentiles), sparkline, CSV/JSON export
  framing.py    CRC-16/CCITT-FALSE framing, resynchronising frame decoder
  transport.py  FileSource / SerialSource / byte sources / target parsing
  render.py     timestamps, colours, tables
  demo.py       deterministic synthetic telemetry and frame streams
  cli.py        argparse wiring for read / stats / frames / demo
tests/          parser, stats, framing, render, transport, cli
examples/       sample_log.txt and sample_frames.bin (used by the README)
```

Layout follows the src layout; `pyproject.toml` holds build, metadata, pytest
and ruff configuration. CI runs the suite on Python 3.10–3.13 for every push and
pull request.

## Roadmap

- [ ] `watch` mode that prints one refreshed summary table instead of a stream
- [ ] feed decoded frame payloads into `stats` (`frames --stats`)
- [ ] `--plot` using matplotlib when available
- [ ] publish to PyPI

## 中文速览

一个给 STM32 串口调试用的小工具：`read` 实时读取并过滤串口/日志（支持按日志
级别和正则筛选），`stats` 把 `temp=25.5C` 这类数据聚合成最小值、最大值、均值、
标准差、p50/p95 和趋势图，可导出 JSON / CSV；`frames` 解析 `0xA5 0x5A` 同步字 +
CRC16 校验的二进制帧，遇到噪声、截断和校验错误会自动重新同步；`demo` 无需开发板
即可演示。

难点在可测试性：硬件读写被隔离在 `transport` 一个模块里，解析、统计、帧解码、
渲染都是纯函数，因此 CI 上不用接板子就能跑完 111 个测试。统计量用 Welford 在线
算法，避免大数值下的方差抵消。

```bash
pip install -e ".[dev]"
pytest -q
stm32serial demo --count 10
stm32serial stats examples/sample_log.txt
stm32serial frames --demo 12
```

## License

MIT — see [LICENSE](LICENSE).