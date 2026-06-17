"""GreetingConfig model — mirrors the greeting_config table."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GreetingConfig:
    """Per-guild greeting configuration stored in Supabase.

    Mirrors the ``greeting_config`` table.  ``guild_id`` is the primary key
    and foreign key to ``guild(id)`` with ``ON DELETE CASCADE``.
    """

    guild_id: str  # Discord guild ID (PK, FK → guild.id)
    welcome_enabled: bool = False
    goodbye_enabled: bool = False
    welcome_channel_id: str | None = None
    goodbye_channel_id: str | None = None
    welcome_message: str | None = None
    goodbye_message: str | None = None
    welcome_card_enabled: bool = True
    goodbye_card_enabled: bool = True

    @classmethod
    def from_db_row(cls, row: dict) -> GreetingConfig:
        """Build a GreetingConfig from a Supabase row (camelCase keys)."""
        return cls(
            guild_id=row["guildId"],
            welcome_enabled=row.get("welcomeEnabled", False),
            goodbye_enabled=row.get("goodbyeEnabled", False),
            welcome_channel_id=row.get("welcomeChannelId"),
            goodbye_channel_id=row.get("goodbyeChannelId"),
            welcome_message=row.get("welcomeMessage"),
            goodbye_message=row.get("goodbyeMessage"),
            welcome_card_enabled=row.get("welcomeCardEnabled", True),
            goodbye_card_enabled=row.get("goodbyeCardEnabled", True),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "guildId": self.guild_id,
            "welcomeEnabled": self.welcome_enabled,
            "goodbyeEnabled": self.goodbye_enabled,
            "welcomeChannelId": self.welcome_channel_id,
            "goodbyeChannelId": self.goodbye_channel_id,
            "welcomeMessage": self.welcome_message,
            "goodbyeMessage": self.goodbye_message,
            "welcomeCardEnabled": self.welcome_card_enabled,
            "goodbyeCardEnabled": self.goodbye_card_enabled,
        }
