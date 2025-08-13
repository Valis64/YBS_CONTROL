from __future__ import annotations

"""Utilities for generating production reports.

This module provides helpers for clamping production events to a date range
and aggregating the resulting hours.  The primary entry point is
:func:`generate_production_report` which accepts a list of events and returns a
summary structure suitable for programmatic consumption.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Iterable, List
import csv
import json
import os
import sys
import argparse


MAX_DAYS = int(os.getenv("PRODUCTION_REPORT_MAX_DAYS", "31"))


def _parse_datetime(value):
    """Return ``value`` as a timezone-aware :class:`~datetime.datetime`.

    The function accepts either a :class:`datetime` instance or an ISO-8601
    string.  If the parsed value is naive it is assumed to be in UTC.
    """

    if isinstance(value, datetime):
        dt = value
    else:
        # ``fromisoformat`` doesn't understand "Z" so normalise first
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def clip_event(event: Dict, start: datetime, end: datetime) -> float:
    """Clamp an event to ``start``/``end`` and return the clipped hours.

    ``event`` is expected to contain ``startTime`` and ``endTime`` keys which
    may be either ISO formatted strings or :class:`datetime` objects.  The
    function mutates these fields, storing ISO strings for the clipped start and
    end times.  If ``event`` also includes an ``hours`` field, it is scaled by
    the proportion of the interval that remains after clipping.  Otherwise the
    duration is calculated directly from the timestamps.
    """

    ev_start = _parse_datetime(event["startTime"])
    ev_end = _parse_datetime(event["endTime"])

    clipped_start = max(ev_start, start)
    clipped_end = min(ev_end, end)

    # Normalise the stored representation as ISO strings
    event["startTime"] = clipped_start.isoformat()
    event["endTime"] = clipped_end.isoformat()

    if clipped_start >= clipped_end:
        return 0.0

    if "hours" in event and event["hours"] is not None:
        total_seconds = (ev_end - ev_start).total_seconds()
        if total_seconds <= 0:
            return 0.0
        clipped_seconds = (clipped_end - clipped_start).total_seconds()
        return event["hours"] * (clipped_seconds / total_seconds)

    return (clipped_end - clipped_start).total_seconds() / 3600.0


def generate_production_report(
    events: Iterable[Dict], start: str, end: str, tz: str = "UTC"
) -> Dict[str, object]:
    """Aggregate production events into a summary report.

    Parameters
    ----------
    events:
        Iterable of event dictionaries containing ``orderId``, ``workstation``,
        ``startTime`` and ``endTime`` keys.  Times may be ISO strings or
        ``datetime`` objects.
    start, end:
        ISO formatted strings representing the inclusive range to consider.
        They are interpreted as UTC, validated to ensure ``end`` is not before
        ``start`` and that the range does not exceed :data:`MAX_DAYS`.  The
        range is converted to the target ``tz`` timezone and used to clip
        events.
    tz:
        IANA timezone name to which detail timestamps will be converted for
        presentation.  Defaults to ``"UTC"``.

    Returns
    -------
    dict
        A dictionary with ``summary``, ``totals`` and ``details`` sections.  See
        the module documentation for the exact structure.
    """

    tzinfo = ZoneInfo(tz)

    start_utc = _parse_datetime(start).astimezone(timezone.utc)
    end_utc = _parse_datetime(end).astimezone(timezone.utc)
    if end_utc < start_utc:
        raise ValueError("end must be greater than or equal to start")
    if end_utc - start_utc > timedelta(days=MAX_DAYS):
        raise ValueError(f"date range exceeds {MAX_DAYS} days")

    start_dt = start_utc.astimezone(tzinfo)
    end_dt = end_utc.astimezone(tzinfo)

    # Aggregation containers
    by_order = defaultdict(lambda: defaultdict(float))
    totals_by_ws = defaultdict(float)
    details: List[Dict] = []

    for ev in events:
        order_id = ev.get("orderId")
        workstation = ev.get("workstation")
        ev_start = _parse_datetime(ev.get("startTime")).astimezone(tzinfo)
        ev_end = _parse_datetime(ev.get("endTime")).astimezone(tzinfo)

        # Skip events outside the requested range
        if ev_end <= start_dt or ev_start >= end_dt:
            continue

        clip_data = {"startTime": ev_start, "endTime": ev_end}
        if "hours" in ev:
            clip_data["hours"] = ev.get("hours")
        hours = clip_event(clip_data, start_dt, end_dt)
        if hours <= 0:
            continue

        by_order[order_id][workstation] += hours
        totals_by_ws[workstation] += hours

        details.append(
            {
                "orderId": order_id,
                "workstation": workstation,
                "start": _parse_datetime(clip_data["startTime"]).astimezone(
                    timezone.utc
                ).isoformat(),
                "end": _parse_datetime(clip_data["endTime"]).astimezone(
                    timezone.utc
                ).isoformat(),
                "hours": round(hours, 2),
            }
        )

    summary = []
    for order_id in sorted(by_order.keys()):
        ws_totals = {
            ws: round(h, 2) for ws, h in sorted(by_order[order_id].items())
        }
        order_total = round(sum(by_order[order_id].values()), 2)
        summary.append(
            {
                "orderId": order_id,
                "workstations": ws_totals,
                "order_total": order_total,
            }
        )

    totals = {ws: round(h, 2) for ws, h in sorted(totals_by_ws.items())}
    totals["grand_total"] = round(sum(totals_by_ws.values()), 2)

    return {
        "summary": summary,
        "totals": totals,
        "details": details,
        "timezone": tz,
    }


def _build_summary_table(report: Dict[str, object]):
    """Return headers and rows summarising hours by workstation.

    The resulting table has two columns: ``Workstation`` and ``Hours``.  A
    final row labelled ``Grand Total`` contains the sum of all workstation
    hours.  ``report`` is expected to be the structure produced by
    :func:`generate_production_report`.
    """

    totals = report.get("totals", {})

    headers = ["Workstation", "Hours"]
    rows: List[List[str]] = []

    for ws in sorted(k for k in totals.keys() if k != "grand_total"):
        rows.append([ws, f"{totals.get(ws, 0):.2f}"])

    rows.append(["Grand Total", f"{totals.get('grand_total', 0):.2f}"])
    return headers, rows


def _build_order_summary_table(report: Dict[str, object]):
    """Return headers and rows summarising hours by order.

    The table has one column for the order identifier, one column for each
    workstation appearing in the data and a final ``Order Total`` column.
    A ``Totals`` row summarises hours per workstation and the grand total.
    """

    summary = report.get("summary", [])

    workstations = sorted({ws for s in summary for ws in s.get("workstations", {})})
    headers = ["Order ID", *workstations, "Order Total"]

    rows: List[List[str]] = []
    totals = {ws: 0.0 for ws in workstations}
    grand_total = 0.0

    for s in summary:
        ws_totals = s.get("workstations", {})
        order_total = s.get("order_total", 0.0)
        row = [s.get("orderId")]
        for ws in workstations:
            val = ws_totals.get(ws, 0.0)
            row.append(f"{val:.2f}")
            totals[ws] += val
        row.append(f"{order_total:.2f}")
        rows.append(row)
        grand_total += order_total

    total_row = ["Totals"]
    for ws in workstations:
        total_row.append(f"{totals[ws]:.2f}")
    total_row.append(f"{grand_total:.2f}")
    rows.append(total_row)

    return headers, rows


def _build_detail_table(report: Dict[str, object]):
    """Return headers and rows for the detail portion of ``report``."""

    tzinfo = ZoneInfo(report.get("timezone", "UTC"))

    headers = ["Order ID", "Workstation", "Start", "End", "Hours"]
    rows = []
    for d in report.get("details", []):
        start = _parse_datetime(d.get("start")).astimezone(tzinfo).isoformat()
        end = _parse_datetime(d.get("end")).astimezone(tzinfo).isoformat()
        rows.append(
            [
                d.get("orderId"),
                d.get("workstation"),
                start,
                end,
                f"{d.get('hours', 0):.2f}",
            ]
        )
    return headers, rows


def export_to_csv(report: Dict[str, object], out_dir: str) -> None:
    """Write ``report`` to ``out_dir`` as ``Summary.csv`` and ``Details.csv``."""

    os.makedirs(out_dir, exist_ok=True)

    summary_headers, summary_rows = _build_summary_table(report)
    with open(os.path.join(out_dir, "Summary.csv"), "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(summary_headers)
        writer.writerows(summary_rows)

    detail_headers, detail_rows = _build_detail_table(report)
    with open(os.path.join(out_dir, "Details.csv"), "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(detail_headers)
        writer.writerows(detail_rows)


def export_to_sheets(report: Dict[str, object], sheet_id: str) -> None:
    """Export ``report`` to a Google Sheets spreadsheet ``sheet_id``.

    The function creates/clears ``Summary`` and ``Details`` worksheets and
    populates them with the report data.  Basic formatting such as freezing
    the top five rows and first column, auto-sizing columns, two decimal number
    formatting and borders are applied.
    """

    import gspread  # Imported lazily as this is an optional dependency

    client = gspread.service_account()
    spreadsheet = client.open_by_key(sheet_id)

    def _upsert_ws(title, headers, rows):
        cols = len(headers)
        rows_len = len(rows) + 1
        try:
            ws = spreadsheet.worksheet(title)
            ws.clear()
        except Exception:
            ws = spreadsheet.add_worksheet(title=title, rows=rows_len, cols=cols)
        ws.update("A5", [headers] + rows)

        spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": ws.id,
                                "gridProperties": {
                                    "frozenRowCount": 5,
                                    "frozenColumnCount": 1,
                                },
                            },
                            "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
                        }
                    },
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": ws.id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": cols,
                            }
                        }
                    },
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": 5,
                                "startColumnIndex": 1,
                                "endRowIndex": rows_len + 5,
                                "endColumnIndex": cols,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {
                                        "type": "NUMBER",
                                        "pattern": "0.00",
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    },
                    {
                        "updateBorders": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": 4,
                                "startColumnIndex": 0,
                                "endRowIndex": rows_len + 5,
                                "endColumnIndex": cols,
                            },
                            "top": {"style": "SOLID", "width": 1},
                            "bottom": {"style": "SOLID", "width": 1},
                            "left": {"style": "SOLID", "width": 1},
                            "right": {"style": "SOLID", "width": 1},
                            "innerHorizontal": {"style": "SOLID", "width": 1},
                            "innerVertical": {"style": "SOLID", "width": 1},
                        }
                    },
                ]
            }
        )

    summary_headers, summary_rows = _build_order_summary_table(report)
    detail_headers, detail_rows = _build_detail_table(report)
    _upsert_ws("Summary", summary_headers, summary_rows)
    _upsert_ws("Details", detail_headers, detail_rows)


def main(argv: List[str] | None = None) -> None:
    """Entry point for command line usage.

    Events are expected as JSON on ``stdin``.  The output destination must be
    specified using ``--sheet-id`` or ``--csv-dir``.
    """

    parser = argparse.ArgumentParser(description="Generate production report")
    parser.add_argument("--start", required=True, help="Start time (ISO format)")
    parser.add_argument("--end", required=True, help="End time (ISO format)")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sheet-id", help="Destination Google Sheet ID")
    group.add_argument("--csv-dir", help="Directory to write CSV files")
    args = parser.parse_args(argv)

    try:
        events = json.load(sys.stdin)
    except json.JSONDecodeError:
        parser.error("Invalid JSON input")

    report = generate_production_report(events, args.start, args.end, args.timezone)

    if args.sheet_id:
        export_to_sheets(report, args.sheet_id)
    else:
        export_to_csv(report, args.csv_dir)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

