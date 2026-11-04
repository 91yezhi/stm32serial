# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/91yezhi/stm32serial/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/91yezhi/stm32serial/releases/tag/v0.1.0