# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-06

### Added

- `stm32serial frames` — decode a binary packet stream (sync `0xA5 0x5A`,
  `msg_id`, `length`, payload, little-endian CRC-16) from a capture file or a
  live port, as a table or `--json`, with `--hex`, `--max-frames`, `--demo`,
  `--seed` and `--follow`.
- `stm32serial.framing` — `encode_frame`, `crc16` (CRC-16/CCITT-FALSE) and a
  resynchronising `FrameDecoder` that survives split frames, leading garbage,
  truncation and checksum errors, reporting `frames` / `crc_errors` /
  `discarded_bytes` / `pending_bytes`.
- `FileByteSource`, `SerialByteSource` and `open_byte_source()` next to the
  existing line sources, so raw streams are testable without hardware.
- `synthetic_frames()` produces a deliberately hostile demo stream: split
  frames, injected noise and one corrupted payload byte.
- `stats` reports `p50` and `p95` (linear interpolation over a trailing
  1024-sample window) as table columns, in `--json` and in the `--csv` export.
- `percentile(values, fraction)` and `ChannelStats.percentile()` are exported
  for library use.

### Fixed

- `stdev` no longer loses all precision on signals with a large offset. The
  sum-of-squares formula suffered catastrophic cancellation and reported
  `stdev = 0.0` for `1e8, 1e8+1, 1e8, 1e8+1`; Welford's online algorithm now
  returns the correct `0.5`.

### Changed

- `CSV_FIELDS` gains `p50` and `p95` (between `stdev` and `first`), so CSV
  consumers see two extra columns.

## [0.1.0] - 2026-11-04

First public release.

### Added

- `stm32serial read` — stream a UART or a log file with `--grep`, `--level`,
  `--max-lines`, `--follow`, `--ts` and `--color`.
- `stm32serial stats` — aggregate every `name=value` channel into count, min,
  max, mean, population standard deviation, first/last, plus a unicode
  sparkline; export as a table, `--json` or `--csv`.
- `stm32serial demo` — deterministic synthetic telemetry so the tool (and the
  test suite) works without a board.
- Target syntax `COM5@115200` / `/dev/ttyUSB0@230400`, with plain paths treated
  as log files.
- Log-level normalisation (`WARNING`, `ERR`, `CRIT` aliases) and a
  `TRACE < DEBUG < INFO < WARN < ERROR < FATAL` ordering.
- Hardware behind a single `lines()` interface (`FileSource`, lazily imported
  `SerialSource`), keeping parser, statistics and rendering pure and testable.
- 81 tests, ruff linting, and a GitHub Actions matrix for Python 3.9–3.13 on
  Linux, macOS and Windows.
- ASCII sparkline fallback when the console encoding cannot render the unicode
  block glyphs.

[Unreleased]: https://github.com/91yezhi/stm32serial/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/91yezhi/stm32serial/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/91yezhi/stm32serial/releases/tag/v0.1.0