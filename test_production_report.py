import csv
from datetime import datetime, timedelta, timezone
import types
import sys

import pytest

from production_report import (
    clip_event,
    generate_production_report,
    export_to_csv,
    export_to_sheets,
    MAX_DAYS,
)


@pytest.fixture
def sample_events():
    """Events spanning range edges and overlapping workstations."""
    return [
        {
            "orderId": "A",
            "workstation": "Cut",
            "startTime": "2024-01-01T00:00:00Z",
            "endTime": "2024-01-01T02:00:00Z",
        },
        {
            "orderId": "A",
            "workstation": "Weld",
            "startTime": "2024-01-01T01:00:00Z",
            "endTime": "2024-01-01T03:00:00Z",
        },
        {
            # Starts before range
            "orderId": "B",
            "workstation": "Cut",
            "startTime": "2023-12-31T23:00:00Z",
            "endTime": "2024-01-01T01:00:00Z",
        },
        {
            # Ends after range
            "orderId": "B",
            "workstation": "Paint",
            "startTime": "2024-01-01T23:00:00Z",
            "endTime": "2024-01-02T01:00:00Z",
        },
        {
            # Completely outside range
            "orderId": "C",
            "workstation": "Cut",
            "startTime": "2024-02-01T00:00:00Z",
            "endTime": "2024-02-01T01:00:00Z",
        },
    ]


def test_clip_event_trims_to_boundaries():
    event = {
        "startTime": "2024-01-01T00:00:00Z",
        "endTime": "2024-01-01T05:00:00Z",
    }
    start = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc)

    hours = clip_event(event, start, end)

    assert hours == 2.0
    assert event["startTime"] == "2024-01-01T01:00:00+00:00"
    assert event["endTime"] == "2024-01-01T03:00:00+00:00"


def test_clip_event_uses_precomputed_hours():
    event = {
        "startTime": "2024-01-01T00:00:00Z",
        "endTime": "2024-01-01T05:00:00Z",
        "hours": 2.5,
    }
    start = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc)

    hours = clip_event(event, start, end)

    assert round(hours, 2) == 1.0
    assert event["startTime"] == "2024-01-01T01:00:00+00:00"
    assert event["endTime"] == "2024-01-01T03:00:00+00:00"


def test_generate_production_report(sample_events):
    report = generate_production_report(
        sample_events, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
    )

    expected_summary = [
        {
            "orderId": "A",
            "workstations": {"Cut": 2.0, "Weld": 2.0},
            "order_total": 4.0,
        },
        {
            "orderId": "B",
            "workstations": {"Cut": 1.0, "Paint": 1.0},
            "order_total": 2.0,
        },
    ]
    expected_totals = {
        "Cut": 3.0,
        "Paint": 1.0,
        "Weld": 2.0,
        "grand_total": 6.0,
    }
    expected_details = [
        {
            "orderId": "A",
            "workstation": "Cut",
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2024-01-01T02:00:00+00:00",
            "hours": 2.0,
        },
        {
            "orderId": "A",
            "workstation": "Weld",
            "start": "2024-01-01T01:00:00+00:00",
            "end": "2024-01-01T03:00:00+00:00",
            "hours": 2.0,
        },
        {
            "orderId": "B",
            "workstation": "Cut",
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2024-01-01T01:00:00+00:00",
            "hours": 1.0,
        },
        {
            "orderId": "B",
            "workstation": "Paint",
            "start": "2024-01-01T23:00:00+00:00",
            "end": "2024-01-02T00:00:00+00:00",
            "hours": 1.0,
        },
    ]

    assert report["summary"] == expected_summary
    assert report["totals"] == expected_totals
    assert report["details"] == expected_details


def test_generate_report_uses_precomputed_hours():
    events = [
        {
            "orderId": "X",
            "workstation": "Cut",
            "startTime": "2024-01-01T00:00:00Z",
            "endTime": "2024-01-01T10:00:00Z",
            "hours": 5.0,
        }
    ]
    report = generate_production_report(
        events, "2024-01-01T02:00:00Z", "2024-01-01T06:00:00Z"
    )

    assert report["summary"][0]["workstations"]["Cut"] == 2.0
    assert report["totals"]["Cut"] == 2.0
    assert report["totals"]["grand_total"] == 2.0
    assert report["details"][0]["hours"] == 2.0


def test_generate_production_report_validates_range(sample_events):
    with pytest.raises(ValueError):
        generate_production_report(
            sample_events, "2024-01-02T00:00:00Z", "2024-01-01T00:00:00Z"
        )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    too_long = start + timedelta(days=MAX_DAYS + 1)
    with pytest.raises(ValueError):
        generate_production_report(
            sample_events, start.isoformat(), too_long.isoformat()
        )


def test_export_to_csv(sample_events, tmp_path):
    report = generate_production_report(
        sample_events, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
    )
    export_to_csv(report, tmp_path)

    with open(tmp_path / "Summary.csv") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["Workstation", "Hours"],
        ["Cut", "3.00"],
        ["Paint", "1.00"],
        ["Weld", "2.00"],
        ["Grand Total", "6.00"],
    ]

    with open(tmp_path / "Details.csv") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        ["Order ID", "Workstation", "Start", "End", "Hours"],
        [
            "A",
            "Cut",
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T02:00:00+00:00",
            "2.00",
        ],
        [
            "A",
            "Weld",
            "2024-01-01T01:00:00+00:00",
            "2024-01-01T03:00:00+00:00",
            "2.00",
        ],
        [
            "B",
            "Cut",
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T01:00:00+00:00",
            "1.00",
        ],
        [
            "B",
            "Paint",
            "2024-01-01T23:00:00+00:00",
            "2024-01-02T00:00:00+00:00",
            "1.00",
        ],
    ]


def test_export_to_sheets(monkeypatch, sample_events):
    report = generate_production_report(
        sample_events, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
    )

    class DummyWorksheet:
        def __init__(self):
            self.id = 1
            self.updated = None
        def clear(self):
            pass
        def update(self, cell, data):
            self.updated = (cell, data)

    class DummySpreadsheet:
        def __init__(self):
            self.wss = {}
            self.batch = []
        def worksheet(self, title):
            if title in self.wss:
                return self.wss[title]
            raise gspread.WorksheetNotFound()
        def add_worksheet(self, title, rows, cols):
            ws = DummyWorksheet()
            self.wss[title] = ws
            return ws
        def batch_update(self, body):
            self.batch.append(body)

    class DummyClient:
        def __init__(self):
            self.sheet = DummySpreadsheet()
        def open_by_key(self, key):
            self.key = key
            return self.sheet

    dummy = types.SimpleNamespace()
    dummy.WorksheetNotFound = type("WorksheetNotFound", (Exception,), {})
    client = DummyClient()
    dummy.service_account = lambda: client
    monkeypatch.setitem(sys.modules, "gspread", dummy)

    export_to_sheets(report, "sheet123")

    summary_ws = client.sheet.wss["Summary"]
    detail_ws = client.sheet.wss["Details"]
    assert summary_ws.updated == (
        "A5",
        [
            ["Order ID", "Cut", "Paint", "Weld", "Order Total"],
            ["A", "2.00", "0.00", "2.00", "4.00"],
            ["B", "1.00", "1.00", "0.00", "2.00"],
            ["Totals", "3.00", "1.00", "2.00", "6.00"],
        ],
    )
    assert detail_ws.updated == (
        "A5",
        [
            ["Order ID", "Workstation", "Start", "End", "Hours"],
            [
                "A",
                "Cut",
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T02:00:00+00:00",
                "2.00",
            ],
            [
                "A",
                "Weld",
                "2024-01-01T01:00:00+00:00",
                "2024-01-01T03:00:00+00:00",
                "2.00",
            ],
            [
                "B",
                "Cut",
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T01:00:00+00:00",
                "1.00",
            ],
            [
                "B",
                "Paint",
                "2024-01-01T23:00:00+00:00",
                "2024-01-02T00:00:00+00:00",
                "1.00",
            ],
        ],
    )
