import pytest
from datetime import datetime, timedelta, timezone

from production_report import generate_production_report, _build_detail_table, MAX_DAYS


def sample_events():
    return [
        {
            "orderId": "A",
            "workstation": "Cut",
            "startTime": "2024-01-01T00:00:00Z",
            "endTime": "2024-01-01T02:00:00Z",
        }
    ]


def test_validates_date_range():
    events = sample_events()
    # end before start
    with pytest.raises(ValueError):
        generate_production_report(
            events,
            "2024-01-02T00:00:00Z",
            "2024-01-01T00:00:00Z",
        )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    too_long_end = start + timedelta(days=MAX_DAYS + 1)
    with pytest.raises(ValueError):
        generate_production_report(
            events,
            start.isoformat(),
            too_long_end.isoformat(),
        )


def test_timezone_conversion_and_storage():
    events = sample_events()
    report = generate_production_report(
        events,
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
        tz="America/New_York",
    )

    assert report["details"][0]["start"].startswith("2024-01-01T00:00:00+00:00")
    headers, rows = _build_detail_table(report)
    assert rows[0][2].startswith("2023-12-31T19:00:00-05:00")
    assert rows[0][3].startswith("2023-12-31T21:00:00-05:00")

