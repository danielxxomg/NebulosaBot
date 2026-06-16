"""Unit tests for bot.utils.time.parse_duration."""

from __future__ import annotations

import pytest

from bot.utils.time import parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30s", 30),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        ("1h30m", 5400),
        # Invalid / empty fall back to 1 hour.
        ("", 3600),
        ("abc", 3600),
        ("30", 3600),  # no unit suffix
        ("1x", 3600),  # unknown unit
    ],
)
def test_parse_duration(text: str, expected: int) -> None:
    assert parse_duration(text) == expected


def test_parse_duration_case_insensitive() -> None:
    """Unit letters are lower-cased before matching."""
    assert parse_duration("1H") == 3600
    assert parse_duration("2D") == 172800
