"""Basic tests for the bot components."""

import pytest
from datetime import datetime, timedelta
from time_utils import parse_time_interval, get_time_range_description


class TestTimeUtils:
    """Test time parsing utilities."""

    def test_parse_time_interval_minutes(self):
        """Test parsing minute intervals."""
        result = parse_time_interval("30m")
        assert result == timedelta(minutes=30)

    def test_parse_time_interval_hours(self):
        """Test parsing hour intervals."""
        result = parse_time_interval("2h")
        assert result == timedelta(hours=2)

    def test_parse_time_interval_days(self):
        """Test parsing day intervals."""
        result = parse_time_interval("7d")
        assert result == timedelta(days=7)

    def test_parse_time_interval_invalid(self):
        """Test parsing invalid intervals."""
        assert parse_time_interval("invalid") is None
        assert parse_time_interval("") is None
        assert parse_time_interval("30x") is None

    def test_get_time_range_description(self):
        """Test time range descriptions."""
        assert "30 minutes" in get_time_range_description(timedelta(minutes=30))
        assert "2 hours" in get_time_range_description(timedelta(hours=2))
        assert "7 days" in get_time_range_description(timedelta(days=7))


if __name__ == "__main__":
    pytest.main([__file__])
