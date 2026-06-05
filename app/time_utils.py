from __future__ import annotations

from datetime import datetime, time, timedelta


def fmt_dt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def start_end_for_span(timespan: int) -> tuple[datetime, datetime]:
    now = datetime.now()
    today = datetime.combine(now.date(), time.min)

    if timespan == 1:
        return today, now
    if timespan == 2:
        monday = today - timedelta(days=today.weekday())
        return monday, now
    if timespan == 3:
        first = today.replace(day=1)
        if first.month == 12:
            next_month = first.replace(year=first.year + 1, month=1)
        else:
            next_month = first.replace(month=first.month + 1)
        return first, next_month - timedelta(seconds=1)
    if timespan == 4:
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        return last_monday, this_monday - timedelta(seconds=1)
    if timespan == 5:
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(seconds=1)
        return last_month_end.replace(day=1, hour=0, minute=0, second=0), last_month_end
    if timespan == 6:
        yesterday = today - timedelta(days=1)
        return yesterday, today - timedelta(seconds=1)
    if timespan == 0:
        return datetime(1900, 1, 1), now

    return today, now


def parse_legacy_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S")
