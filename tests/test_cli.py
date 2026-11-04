"""End-to-end tests for the CLI: ``read``, ``stats`` and ``demo``."""

import csv
import json

import pytest

from stm32serial.cli import main

LOG = """\
boot complete
[INFO] tick=0 temp=25.00C hum=41.00% vbus=3.300V
[WARN] tick=1 temp=26.00C hum=42.00% vbus=3.310V
[ERROR] uart overrun, 2 sample(s) dropped
tick=2 temp=27.00C hum=43.00% vbus=3.290V
"""


@pytest.fixture()
def log_file(tmp_path):
    path = tmp_path / "run.log"
    path.write_text(LOG, encoding="utf-8")
    return str(path)


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "read" in capsys.readouterr().out


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "stm32serial 0.1.0" in capsys.readouterr().out


def test_demo_count_and_no_timestamps(capsys):
    assert main(["demo", "--count", "5", "--ts", "off"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 5
    assert lines[0].startswith("temp=")


def test_demo_elapsed_timestamps(capsys):
    assert main(["demo", "--count", "2", "--ts", "elapsed", "--color", "never"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert all(line.startswith("+00:0") for line in lines)


def test_demo_level_colouring(capsys):
    # Every 29th synthetic line is an ERROR and 7th is INFO; a short run still
    # exercises the coloured branch.
    assert main(["demo", "--count", "30", "--color", "always"]) == 0
    assert "\x1b[" in capsys.readouterr().out


def test_read_max_lines(log_file, capsys):
    assert main(["read", log_file, "--max-lines", "2", "--ts", "off"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == ["boot complete", "[INFO] tick=0 temp=25.00C hum=41.00% vbus=3.300V"]


def test_read_level_filter(log_file, capsys):
    assert main(["read", log_file, "--level", "WARN", "--ts", "off"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert all(line.startswith(("[WARN]", "[ERROR]")) for line in lines)


def test_read_grep_filter(log_file, capsys):
    assert main(["read", log_file, "--grep", "temp", "--ts", "off"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 3


def test_read_missing_file_reports_error(capsys):
    assert main(["read", "does-not-exist.log"]) == 1
    assert "file not found" in capsys.readouterr().err


def test_read_invalid_grep_reports_error(log_file, capsys):
    assert main(["read", log_file, "--grep", "([unclosed"]) == 1
    assert "invalid --grep" in capsys.readouterr().err


def test_stats_table(log_file, capsys):
    assert main(["stats", log_file]) == 0
    out = capsys.readouterr().out
    assert "channel" in out and "trend" in out
    for name in ("hum", "temp", "tick", "vbus"):
        assert name in out


def test_stats_no_sparkline(log_file, capsys):
    assert main(["stats", log_file, "--no-sparkline"]) == 0
    assert "trend" not in capsys.readouterr().out


def test_stats_json(log_file, capsys):
    assert main(["stats", log_file, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    channels = {item["channel"]: item for item in payload["channels"]}
    assert channels["temp"]["count"] == 3
    assert channels["temp"]["max"] == pytest.approx(27.0)


def test_stats_csv(log_file, tmp_path, capsys):
    target = tmp_path / "out.csv"
    assert main(["stats", log_file, "--csv", str(target)]) == 0
    assert "wrote 4 row(s)" in capsys.readouterr().out
    with target.open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 4


def test_stats_multiple_targets(tmp_path, capsys):
    first = tmp_path / "a.log"
    second = tmp_path / "b.log"
    first.write_text("temp=1.0C\n", encoding="utf-8")
    second.write_text("temp=3.0C\n", encoding="utf-8")
    assert main(["stats", str(first), str(second), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channels"][0]["count"] == 2
    assert payload["channels"][0]["mean"] == pytest.approx(2.0)


def test_stats_without_samples(tmp_path, capsys):
    empty = tmp_path / "empty.log"
    empty.write_text("just text\n", encoding="utf-8")
    assert main(["stats", str(empty)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no telemetry samples found" in captured.err