"""Unit tests for bot.models.economy_config — EconomyConfig dataclass.

Proves from_db_row/to_db_dict round-trip correctness and default handling.
"""

from __future__ import annotations

from bot.models.economy_config import EconomyConfig


class TestEconomyConfigFromDbRow:
    """from_db_row must map camelCase Supabase columns to snake_case fields."""

    def test_from_db_row_all_fields(self) -> None:
        """All fields populated from a complete row."""
        row = {
            "guildId": "111222333",
            "dailyReward": 200,
            "dailyCooldownHours": 12,
            "xpPerMessage": 20,
            "xpCooldownSeconds": 30,
            "levelBaseXp": 500,
            "levelMultiplier": 2.0,
            "levelRoles": {"10": "role_a", "20": "role_b"},
            "levelUpChannelId": "999888777",
        }
        cfg = EconomyConfig.from_db_row(row)

        assert cfg.guild_id == "111222333"
        assert cfg.daily_reward == 200
        assert cfg.daily_cooldown_hours == 12
        assert cfg.xp_per_message == 20
        assert cfg.xp_cooldown_seconds == 30
        assert cfg.level_base_xp == 500
        assert cfg.level_multiplier == 2.0
        assert cfg.level_roles == {"10": "role_a", "20": "role_b"}
        assert cfg.level_up_channel_id == "999888777"

    def test_from_db_row_defaults_for_missing_keys(self) -> None:
        """Missing optional keys fall back to documented defaults."""
        row = {"guildId": "444555666"}
        cfg = EconomyConfig.from_db_row(row)

        assert cfg.guild_id == "444555666"
        assert cfg.daily_reward == 100
        assert cfg.daily_cooldown_hours == 24
        assert cfg.xp_per_message == 10
        assert cfg.xp_cooldown_seconds == 60
        assert cfg.level_base_xp == 100
        assert cfg.level_multiplier == 1.5
        assert cfg.level_roles == {}
        assert cfg.level_up_channel_id is None


class TestEconomyConfigToDbDict:
    """to_db_dict must serialize back to camelCase keys matching Supabase schema."""

    def test_to_db_dict_round_trip(self) -> None:
        """Row → from_db_row → to_db_dict must reproduce the original row."""
        row = {
            "guildId": "111222333",
            "dailyReward": 200,
            "dailyCooldownHours": 12,
            "xpPerMessage": 20,
            "xpCooldownSeconds": 30,
            "levelBaseXp": 500,
            "levelMultiplier": 2.0,
            "levelRoles": {"10": "role_a"},
            "levelUpChannelId": "999888777",
        }
        cfg = EconomyConfig.from_db_row(row)
        result = cfg.to_db_dict()

        assert result == row

    def test_to_db_dict_with_defaults(self) -> None:
        """Default-config to_db_dict must contain all required keys."""
        cfg = EconomyConfig(guild_id="777")
        result = cfg.to_db_dict()

        assert result["guildId"] == "777"
        assert result["dailyReward"] == 100
        assert result["dailyCooldownHours"] == 24
        assert result["xpPerMessage"] == 10
        assert result["xpCooldownSeconds"] == 60
        assert result["levelBaseXp"] == 100
        assert result["levelMultiplier"] == 1.5
        assert result["levelRoles"] == {}
        assert result["levelUpChannelId"] is None
