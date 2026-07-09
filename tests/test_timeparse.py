"""Unit tests for bot.utils.timeparse._to_datetime.

Covers:
    - ISO string -> datetime
    - datetime passthrough
    - None -> None
    - invalid string -> None
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.utils.timeparse import _to_datetime


class TestToDatetime:
    """_to_datetime: parse ISO strings, passthrough datetime, return None for None/invalid."""

    def test_iso_string_returns_datetime(self) -> None:
        """An ISO-8601 string MUST be parsed to a datetime."""
        result = _to_datetime("2024-06-15T12:00:00+00:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_datetime_passthrough(self) -> None:
        """A datetime object MUST be returned as-is (no wrapping/conversion)."""
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = _to_datetime(dt)
        assert result is dt

    def test_none_returns_none(self) -> None:
        """None MUST return None."""
        assert _to_datetime(None) is None

    def test_invalid_string_returns_none(self) -> None:
        """An invalid/unparseable string MUST return None, not raise."""
        assert _to_datetime("not-a-date") is None
        assert _to_datetime("") is None
        assert _to_datetime("2024-13-45T99:99:99") is None

    def test_iso_string_without_tz(self) -> None:
        """An ISO string without timezone MUST still parse."""
        result = _to_datetime("2024-06-15T12:00:00")
        assert isinstance(result, datetime)

    def test_non_string_non_datetime_non_none_returns_none(self) -> None:
        """A non-string, non-datetime, non-None value (e.g. int) MUST return None."""
        assert _to_datetime(42) is None
        assert _to_datetime(3.14) is None
