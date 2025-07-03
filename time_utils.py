"""Time parsing utilities for the bot."""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_time_interval(interval_str: str) -> Optional[timedelta]:
    """
    Parse human-readable time intervals like "10m", "1h", "24h", "10d".

    Args:
        interval_str: String representing time interval

    Returns:
        timedelta object or None if parsing fails
    """
    if not interval_str:
        return None

    # Pattern to match number followed by unit (m/h/d)
    pattern = r"^(\d+)([mhd])$"
    match = re.match(pattern, interval_str.lower().strip())

    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)

    return None


def get_time_range_description(interval: timedelta) -> str:
    """
    Get a human-readable description of a time interval.

    Args:
        interval: timedelta object

    Returns:
        Human-readable string
    """
    total_seconds = int(interval.total_seconds())

    if total_seconds < 3600:  # Less than 1 hour
        minutes = total_seconds // 60
        return f"Last {minutes} minute{'s' if minutes != 1 else ''}"
    elif total_seconds < 86400:  # Less than 1 day
        hours = total_seconds // 3600
        return f"Last {hours} hour{'s' if hours != 1 else ''}"
    else:  # Days
        days = total_seconds // 86400
        return f"Last {days} day{'s' if days != 1 else ''}"


def format_timestamp_for_display(timestamp: datetime) -> str:
    """Format timestamp for display in summaries."""
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")
