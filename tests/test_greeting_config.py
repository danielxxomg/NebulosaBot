"""Unit tests for bot.models.greeting_config.GreetingConfig.

Covers the GreetingConfig model: field defaults, from_db_row mapping,
to_db_dict conversion, and roundtrip consistency.
"""

from __future__ import annotations

from bot.models.greeting_config import GreetingConfig


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestGreetingConfigDefaults:
    """New GreetingConfig instances should have sensible defaults."""

    def test_default_guild_id_only(self) -> None:
        """Creating a config with only guild_id sets all defaults."""
        config = GreetingConfig(guild_id="123456789")
        assert config.guild_id == "123456789"
        assert config.welcome_enabled is False
        assert config.goodbye_enabled is False
        assert config.welcome_channel_id is None
        assert config.goodbye_channel_id is None
        assert config.welcome_message is None
        assert config.goodbye_message is None
        assert config.welcome_card_enabled is True
        assert config.goodbye_card_enabled is True

    def test_default_welcome_card_enabled_is_true(self) -> None:
        """Welcome card should default to True (design decision)."""
        config = GreetingConfig(guild_id="abc")
        assert config.welcome_card_enabled is True

    def test_default_goodbye_card_enabled_is_true(self) -> None:
        """Goodbye card should default to True (design decision)."""
        config = GreetingConfig(guild_id="abc")
        assert config.goodbye_card_enabled is True


# ---------------------------------------------------------------------------
# from_db_row — Supabase camelCase row → GreetingConfig
# ---------------------------------------------------------------------------


class TestFromDbRow:
    """from_db_row() must correctly map camelCase DB columns to snake_case fields."""

    def test_full_row_maps_all_fields(self) -> None:
        """All 9 columns should be mapped from a complete DB row."""
        row = {
            "guildId": "123456789",
            "welcomeEnabled": True,
            "goodbyeEnabled": True,
            "welcomeChannelId": "111111111",
            "goodbyeChannelId": "222222222",
            "welcomeMessage": "Welcome {mention}!",
            "goodbyeMessage": "Goodbye {mention}!",
            "welcomeCardEnabled": True,
            "goodbyeCardEnabled": False,
        }
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "123456789"
        assert config.welcome_enabled is True
        assert config.goodbye_enabled is True
        assert config.welcome_channel_id == "111111111"
        assert config.goodbye_channel_id == "222222222"
        assert config.welcome_message == "Welcome {mention}!"
        assert config.goodbye_message == "Goodbye {mention}!"
        assert config.welcome_card_enabled is True
        assert config.goodbye_card_enabled is False

    def test_minimal_row_uses_defaults(self) -> None:
        """A row with only the primary key should fill missing fields with defaults."""
        row = {"guildId": "999888777"}
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "999888777"
        assert config.welcome_enabled is False
        assert config.goodbye_enabled is False
        assert config.welcome_channel_id is None
        assert config.goodbye_channel_id is None
        assert config.welcome_message is None
        assert config.goodbye_message is None

    def test_partial_row_picks_present_values(self) -> None:
        """Provided values should be used; missing ones should get defaults."""
        row = {
            "guildId": "aaa",
            "welcomeEnabled": True,
            "welcomeChannelId": "bbb",
            "welcomeMessage": "Hey {mention}!",
        }
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "aaa"
        assert config.welcome_enabled is True
        assert config.welcome_channel_id == "bbb"
        assert config.welcome_message == "Hey {mention}!"
        # Missing fields should use defaults.
        assert config.goodbye_enabled is False
        assert config.goodbye_channel_id is None
        assert config.goodbye_message is None


# ---------------------------------------------------------------------------
# to_db_dict — GreetingConfig → camelCase dict for Supabase
# ---------------------------------------------------------------------------


class TestToDbDict:
    """to_db_dict() must produce a dict with camelCase keys matching the DB schema."""

    def test_full_config_converts_all_fields(self) -> None:
        """All fields should be present in the output dict with correct camelCase keys."""
        config = GreetingConfig(
            guild_id="123456789",
            welcome_enabled=True,
            goodbye_enabled=False,
            welcome_channel_id="111111111",
            goodbye_channel_id=None,
            welcome_message="Welcome {mention}!",
            goodbye_message=None,
            welcome_card_enabled=True,
            goodbye_card_enabled=False,
        )
        result = config.to_db_dict()
        expected_keys = {
            "guildId", "welcomeEnabled", "goodbyeEnabled",
            "welcomeChannelId", "goodbyeChannelId",
            "welcomeMessage", "goodbyeMessage",
            "welcomeCardEnabled", "goodbyeCardEnabled",
        }
        assert set(result.keys()) == expected_keys
        assert result["guildId"] == "123456789"
        assert result["welcomeEnabled"] is True
        assert result["goodbyeEnabled"] is False
        assert result["welcomeChannelId"] == "111111111"
        assert result["goodbyeChannelId"] is None
        assert result["welcomeMessage"] == "Welcome {mention}!"
        assert result["goodbyeMessage"] is None
        assert result["welcomeCardEnabled"] is True
        assert result["goodbyeCardEnabled"] is False

    def test_bool_values_are_booleans(self) -> None:
        """Boolean fields must remain Python bool, not ints or strings."""
        config = GreetingConfig(
            guild_id="x",
            welcome_enabled=True,
            goodbye_enabled=False,
            welcome_card_enabled=True,
            goodbye_card_enabled=False,
        )
        result = config.to_db_dict()
        assert isinstance(result["welcomeEnabled"], bool)
        assert isinstance(result["goodbyeEnabled"], bool)
        assert isinstance(result["welcomeCardEnabled"], bool)
        assert isinstance(result["goodbyeCardEnabled"], bool)


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    """from_db_row(to_db_dict(config)) should be equivalent to the original config."""

    def test_roundtrip_preserves_all_fields(self) -> None:
        """Serializing then deserializing should recover the same values."""
        original = GreetingConfig(
            guild_id="123456789",
            welcome_enabled=True,
            goodbye_enabled=True,
            welcome_channel_id="111",
            goodbye_channel_id="222",
            welcome_message="Hello {mention}!",
            goodbye_message="Bye {mention}!",
            welcome_card_enabled=False,
            goodbye_card_enabled=True,
        )
        db_dict = original.to_db_dict()
        restored = GreetingConfig.from_db_row(db_dict)
        assert restored == original
