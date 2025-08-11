"""Utilities for working with business hours."""

from datetime import datetime, timedelta, time


BUSINESS_START = time(8, 0)
BUSINESS_END = time(16, 30)


def _next_business_start(dt: datetime) -> datetime:
    """Return the next datetime aligned with the start of business hours.

    Steps:
    1. Add one calendar day to ``dt``.
    2. Replace the time portion with ``BUSINESS_START`` (08:00).
    3. Return the normalized datetime.

    The helper itself does not skip weekends; callers should continue
    invoking it until a weekday is reached.
    """
    next_day = dt + timedelta(days=1)
    return next_day.replace(
        hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0
    )


def business_hours_breakdown(start: datetime, end: datetime):
    """Return a list of business-hour segments between ``start`` and ``end``.

    Steps:
    1. Iterate from ``start`` until ``end``.
    2. Skip Saturdays and Sundays by jumping to the next business start.
    3. For each weekday, compute the 08:00 ``day_start`` and 16:30 ``day_end``.
    4. Snap the current time to ``day_start`` if it falls earlier.
    5. If the current time is past ``day_end``, move to the next day.
    6. Record a segment from the current time to the earlier of ``day_end`` or ``end``.
    7. Advance to the next day's start and repeat.

    Example:
        >>> from datetime import datetime
        >>> business_hours_breakdown(
        ...     datetime(2024, 1, 5, 16, 0), datetime(2024, 1, 8, 10, 0)
        ... )
        [(datetime(2024, 1, 5, 16, 0), datetime(2024, 1, 5, 16, 30)),
         (datetime(2024, 1, 8, 8, 0), datetime(2024, 1, 8, 10, 0))]

    Weekends are skipped entirely, days are segmented by business start and
    end, and the return value lists each contiguous span that contributes
    to business time.
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
    """Return the total business time between ``start`` and ``end``.

    Steps:
    1. If ``start`` is not before ``end``, return ``timedelta(0)``.
    2. Use :func:`business_hours_breakdown` to obtain all weekday segments.
    3. Sum the duration of each segment to compute the total.

    Only hours between 08:00 and 16:30 on weekdays contribute to the
    total because weekend periods are skipped by the breakdown.
    """

    if start >= end:
        return timedelta(0)
    total = timedelta()
    for seg_start, seg_end in business_hours_breakdown(start, end):
        total += seg_end - seg_start
    return total
