"""Utilities for working with business hours."""

from datetime import datetime, timedelta, time


BUSINESS_START = time(8, 0)
BUSINESS_END = time(16, 30)


def _next_business_start(dt: datetime) -> datetime:
    """Return the next datetime at the start of business hours."""
    next_day = dt + timedelta(days=1)
    return next_day.replace(
        hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0
    )


def business_hours_breakdown(start: datetime, end: datetime):
    """Return a list of (segment_start, segment_end) within business hours.

    Business hours are 8:00–16:30 Monday–Friday. Weekends are excluded.
    """

    segments = []
    current = start
    while current < end:
        # Skip weekends entirely
        if current.weekday() >= 5:
            current = _next_business_start(current)
            continue

        day_start = current.replace(
            hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0
        )
        day_end = current.replace(
            hour=BUSINESS_END.hour, minute=BUSINESS_END.minute, second=0, microsecond=0
        )

        if current < day_start:
            current = day_start
        if current >= day_end:
            current = _next_business_start(current)
            continue

        segment_end = min(day_end, end)
        segments.append((current, segment_end))
        current = _next_business_start(current)

    return segments


def business_hours_delta(start: datetime, end: datetime) -> timedelta:
    """Return the business time between ``start`` and ``end``.

    Only hours between 08:00 and 16:30 on weekdays are counted.
    """

    if start >= end:
        return timedelta(0)
    total = timedelta()
    for seg_start, seg_end in business_hours_breakdown(start, end):
        total += seg_end - seg_start
    return total
