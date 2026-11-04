"""Tests for target parsing and the line sources (no hardware required)."""

import pytest

from stm32serial.transport import FileSource, SerialSource, SourceError, open_source, parse_target


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("COM5", ("serial", "COM5", 115200)),
        ("COM5@9600", ("serial", "COM5", 9600)),
        ("com12", ("serial", "com12", 115200)),
        ("/dev/ttyUSB0", ("serial", "/dev/ttyUSB0", 115200)),
        ("/dev/ttyACM0@230400", ("serial", "/dev/ttyACM0", 230400)),
        ("/dev/cu.usbserial-1420", ("serial", "/dev/cu.usbserial-1420", 115200)),
    ],
)
def test_parse_target_serial(spec, expected):
    assert parse_target(spec) == expected


@pytest.mark.parametrize(
    "spec",
    ["examples/sample_log.txt", "logs/run@2.log", "./capture.csv", "C:/logs/a.txt"],
)
def test_parse_target_file(spec):
    kind, target, baud = parse_target(spec)
    assert kind == "file"
    assert target == spec
    assert baud == 115200


def test_parse_target_rejects_empty():
    with pytest.raises(SourceError):
        parse_target("   ")


def test_file_source_missing_file(tmp_path):
    with pytest.raises(SourceError, match="file not found"):
        FileSource(str(tmp_path / "nope.log"))


def test_file_source_rejects_directory(tmp_path):
    with pytest.raises(SourceError, match="directory"):
        FileSource(str(tmp_path))


def test_file_source_strips_line_endings(tmp_path):
    log = tmp_path / "run.log"
    # Write bytes so that Windows text-mode newline translation cannot double
    # the CR: the source must cope with real-world CRLF files.
    log.write_bytes(b"one\r\ntwo\nthree\r\n")
    assert list(FileSource(str(log)).lines()) == ["one", "two", "three"]


def test_file_source_follow_keeps_reading(tmp_path):
    log = tmp_path / "live.log"
    log.write_text("first\n", encoding="utf-8")
    source = FileSource(str(log), follow=True, poll_interval=0.01)
    stream = source.lines()
    assert next(stream) == "first"
    with log.open("a", encoding="utf-8") as handle:
        handle.write("second\n")
    assert next(stream) == "second"
    stream.close()


def test_open_source_returns_file_source(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("temp=1.0C\n", encoding="utf-8")
    source = open_source(str(log))
    assert isinstance(source, FileSource)
    assert list(source.lines()) == ["temp=1.0C"]


def test_serial_source_reports_open_errors_as_source_errors():
    # Either pyserial is missing or the port does not exist; both must be a
    # SourceError rather than a traceback for the user.
    source = SerialSource("COM_DOES_NOT_EXIST", timeout=0.01)
    with pytest.raises(SourceError):
        next(source.lines())