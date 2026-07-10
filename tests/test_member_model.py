"""Unit tests for bot.models.member — Member dataclass.

Proves from_db_row/to_db_dict round-trip correctness, datetime parsing,
and default handling. from_db_row parses ISO strings via
datetime.fromisoformat() so round-trip with to_db_dict is lossless.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.models.member import Member


class TestMemberFromDbRow:
    """from_db_row must map camelCase Supabase columns to snake_case fields."""

    def test_from_db_row_all_fields(self) -> None:
        """All fields populated from a complete row — ISO strings parsed to datetime."""
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
        # ISO strings are parsed to datetime instances.
        assert m.last_daily_reset == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        assert m.last_daily == datetime(2024, 6, 14, 8, 30, 0, tzinfo=UTC)
        assert m.last_xp_gain == datetime(2024, 6, 15, 11, 55, 0, tzinfo=UTC)

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

    def test_from_db_row_accepts_existing_datetime_instances(self) -> None:
        """Already-constructed datetime instances pass through unchanged."""
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        row = {
            "guildId": "111",
            "userId": "222",
            "lastDailyReset": dt,
            "lastDaily": dt,
            "lastXpGain": dt,
        }
        m = Member.from_db_row(row)

        assert m.last_daily_reset is dt
        assert m.last_daily is dt
        assert m.last_xp_gain is dt


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

    def test_round_trip_iso_string_preserves_value(self) -> None:
        """ISO string → from_db_row → to_db_dict → same ISO string."""
        iso = "2024-06-15T12:00:00+00:00"
        row = {
            "guildId": "111",
            "userId": "222",
            "lastDailyReset": iso,
            "lastDaily": iso,
            "lastXpGain": iso,
        }
        m = Member.from_db_row(row)
        result = m.to_db_dict()

        assert result["lastDailyReset"] == iso
        assert result["lastDaily"] == iso
        assert result["lastXpGain"] == iso
