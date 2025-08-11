from __future__ import annotations

"""Utilities for generating production reports.

This module provides helpers for clamping production events to a date range
and aggregating the resulting hours.  The primary entry point is
:func:`generate_production_report` which accepts a list of events and returns a
summary structure suitable for programmatic consumption.
"""

from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Iterable, List


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
    """Clamp an event to ``start``/``end`` and return the clipped duration.

    ``event`` is expected to contain ``startTime`` and ``endTime`` keys which
    may be either ISO formatted strings or :class:`datetime` objects.  The
    function mutates these fields, storing ISO strings for the clipped start and
    end times.  The return value is the duration of the clipped interval in
    hours.
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
        They are interpreted as UTC, converted to the target ``tz`` timezone
        and used to clip events.
    tz:
        IANA timezone name to which all times will be converted.  Defaults to
        ``"UTC"``.

    Returns
    -------
    dict
        A dictionary with ``summary``, ``totals`` and ``details`` sections.  See
        the module documentation for the exact structure.
    """

    tzinfo = ZoneInfo(tz)

    start_dt = _parse_datetime(start).astimezone(tzinfo)
    end_dt = _parse_datetime(end).astimezone(tzinfo)

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
        hours = clip_event(clip_data, start_dt, end_dt)
        if hours <= 0:
            continue

        by_order[order_id][workstation] += hours
        totals_by_ws[workstation] += hours

        details.append(
            {
                "orderId": order_id,
                "workstation": workstation,
                "start": clip_data["startTime"],
                "end": clip_data["endTime"],
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

    return {"summary": summary, "totals": totals, "details": details}

