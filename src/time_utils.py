import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_time_interval(interval_str: str) -> Optional[timedelta]:
    if not interval_str:
        return None

    match = re.match(r"^(\d+)([mhd])$", interval_str.lower().strip())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    return {
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
    }.get(unit)


def get_time_range_description(interval: timedelta) -> str:
    total = int(interval.total_seconds())
    if total < 3600:
        mins = total // 60
        return f"Last {mins} minute{'s' if mins != 1 else ''}"
    if total < 86400:
        hrs = total // 3600
        return f"Last {hrs} hour{'s' if hrs != 1 else ''}"
    days = total // 86400
    return f"Last {days} day{'s' if days != 1 else ''}"


def utc_now() -> datetime:
    """Current UTC time as a naive datetime (the DB stores naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Convert a datetime to naive UTC; naive input is assumed to be UTC already."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def format_timestamp_for_display(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")
