import csv
import json
import sys
from io import StringIO

import pytest

from production_report import generate_production_report, export_to_csv, main


def _sample_events():
    return [
        {
            "orderId": "A",
            "workstation": "Cut",
            "startTime": "2024-01-01T00:00:00Z",
            "endTime": "2024-01-01T01:00:00Z",
        },
        {
            "orderId": "A",
            "workstation": "Print",
            "startTime": "2024-01-01T01:00:00Z",
            "endTime": "2024-01-01T03:00:00Z",
        },
        {
            "orderId": "B",
            "workstation": "Cut",
            "startTime": "2024-01-01T02:00:00Z",
            "endTime": "2024-01-01T04:00:00Z",
        },
    ]


def _make_report():
    events = _sample_events()
    return generate_production_report(
        events, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
    )


def test_export_to_csv(tmp_path):
    report = _make_report()
    export_to_csv(report, tmp_path)

    with open(tmp_path / "Summary.csv", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["Workstation", "Hours"]
    assert rows[1] == ["Cut", "3.00"]
    assert rows[2] == ["Print", "2.00"]
    assert rows[3] == ["Grand Total", "5.00"]

    with open(tmp_path / "Details.csv", newline="") as fh:
        drows = list(csv.reader(fh))
    assert drows[0] == ["Order ID", "Workstation", "Start", "End", "Hours"]
    assert len(drows) == 4
    assert drows[1][0] == "A"


def test_main_writes_csv(tmp_path):
    events = _sample_events()
    stdin = StringIO(json.dumps(events))
    old_stdin = sys.stdin
    try:
        sys.stdin = stdin
        main(
            [
                "--start",
                "2024-01-01T00:00:00Z",
                "--end",
                "2024-01-02T00:00:00Z",
                "--csv-dir",
                str(tmp_path),
            ]
        )
    finally:
        sys.stdin = old_stdin

    assert (tmp_path / "Summary.csv").exists()
    assert (tmp_path / "Details.csv").exists()


def test_main_invalid_json(tmp_path, capsys):
    stdin = StringIO("not json")
    old_stdin = sys.stdin
    try:
        sys.stdin = stdin
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    "--start",
                    "2024-01-01T00:00:00Z",
                    "--end",
                    "2024-01-02T00:00:00Z",
                    "--csv-dir",
                    str(tmp_path),
                ]
            )
    finally:
        sys.stdin = old_stdin
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Invalid JSON" in captured.err
