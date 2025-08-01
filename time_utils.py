from datetime import datetime, timedelta


def business_hours_delta(start: datetime, end: datetime) -> timedelta:
    total = timedelta(0)
    current = start
    while current < end:
        next_day = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        working_end = min(next_day, end)
        # skip weekends
        if current.weekday() < 5:
            total += working_end - current
        current = next_day
    return total
