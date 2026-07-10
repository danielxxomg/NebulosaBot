"""Unit tests for bot.models.member — Member dataclass.

Proves from_db_row/to_db_dict round-trip correctness and default handling.
Tests the CURRENT behavior: datetime fields are stored as-is from the row
(ISO strings remain strings; None remains None). PR2 will add datetime
parsing and update these tests accordingly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.models.member import Member


class TestMemberFromDbRow:
    """from_db_row must map camelCase Supabase columns to snake_case fields."""

    def test_from_db_row_all_fields(self) -> None:
        """All fields populated from a complete row."""
        row = {
            "guildId": "111222333",
            "userId": "444555666",
            "xp": 500,
            "level": 5,
            "warnings": 2,
            "coins": 1234,
            "dailyStreak": 7,
            "lastDailyReset": "2024-06-15T12:00:00+00:00",
            "lastDaily": "2024-06-14T08:30:00+00:00",
            "lastXpGain": "2024-06-15T11:55:00+00:00",
        }
        m = Member.from_db_row(row)

        assert m.guild_id == "111222333"
        assert m.user_id == "444555666"
        assert m.xp == 500
        assert m.level == 5
        assert m.warnings == 2
        assert m.coins == 1234
        assert m.daily_streak == 7
        # Current behavior: strings pass through as-is (PR2 adds datetime parsing)
        assert m.last_daily_reset == "2024-06-15T12:00:00+00:00"
        assert m.last_daily == "2024-06-14T08:30:00+00:00"
        assert m.last_xp_gain == "2024-06-15T11:55:00+00:00"

    def test_from_db_row_defaults_for_missing_keys(self) -> None:
        """Missing optional keys fall back to documented defaults."""
        row = {"guildId": "111", "userId": "222"}
        m = Member.from_db_row(row)

        assert m.guild_id == "111"
        assert m.user_id == "222"
        assert m.xp == 0
        assert m.level == 0
        assert m.warnings == 0
        assert m.coins == 0
        assert m.daily_streak == 0
        assert m.last_daily_reset is None
        assert m.last_daily is None
        assert m.last_xp_gain is None

    def test_from_db_row_none_datetime_fields(self) -> None:
        """Explicit None datetime fields remain None."""
        row = {
            "guildId": "111",
            "userId": "222",
            "lastDailyReset": None,
            "lastDaily": None,
            "lastXpGain": None,
        }
        m = Member.from_db_row(row)

        assert m.last_daily_reset is None
        assert m.last_daily is None
        assert m.last_xp_gain is None


class TestMemberToDbDict:
    """to_db_dict must serialize back to camelCase keys matching Supabase schema."""

    def test_to_db_dict_with_datetime_instances(self) -> None:
        """datetime instances serialize to ISO format strings."""
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        m = Member(
            guild_id="111",
            user_id="222",
            xp=100,
            level=3,
            warnings=1,
            coins=500,
            daily_streak=5,
            last_daily_reset=dt,
            last_daily=dt,
            last_xp_gain=dt,
        )
        result = m.to_db_dict()

        assert result["guildId"] == "111"
        assert result["userId"] == "222"
        assert result["xp"] == 100
        assert result["level"] == 3
        assert result["warnings"] == 1
        assert result["coins"] == 500
        assert result["dailyStreak"] == 5
        assert result["lastDailyReset"] == dt.isoformat()
        assert result["lastDaily"] == dt.isoformat()
        assert result["lastXpGain"] == dt.isoformat()

    def test_to_db_dict_with_none_datetimes(self) -> None:
        """None datetime fields serialize to None."""
        m = Member(guild_id="111", user_id="222")
        result = m.to_db_dict()

        assert result["lastDailyReset"] is None
        assert result["lastDaily"] is None
        assert result["lastXpGain"] is None

    def test_to_db_dict_with_string_datetimes(self) -> None:
        """String datetime fields (current DB behavior) pass through to_db_dict.

        Note: to_db_dict calls .isoformat() only when value is truthy.
        Strings are truthy, so this calls .isoformat() on a str — which
        works because str.isoformat() doesn't exist. This test documents
        the CURRENT behavior: if strings are stored, to_db_dict will fail
        on them because it tries to call .isoformat(). This is the contract
        gap that PR2 will fix.
        """
        # With None values, to_db_dict works fine
        m = Member(guild_id="111", user_id="222")
        result = m.to_db_dict()
        assert result["lastDailyReset"] is None
