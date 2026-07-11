"""EconomyConfig model — mirrors the economy_config table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EconomyConfig:
    """Per-guild economy configuration stored in Supabase.

    Mirrors the ``economy_config`` table.  ``guild_id`` is the primary key
    and foreign key to ``guild(id)`` with ``ON DELETE CASCADE``.
    """

    guild_id: str  # Discord guild ID (PK, FK → guild.id)
    daily_reward: int = 100
    daily_cooldown_hours: int = 24
    xp_per_message: int = 10
    xp_cooldown_seconds: int = 60
    level_base_xp: int = 100
    level_multiplier: float = 1.5
    level_roles: dict[str, str] = field(default_factory=dict)  # {"level": "role_id"}
    level_up_channel_id: str | None = None

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> EconomyConfig:
        """Build an EconomyConfig from a Supabase row (camelCase keys)."""
        return cls(
            guild_id=row["guildId"],
            daily_reward=row.get("dailyReward", 100),
            daily_cooldown_hours=row.get("dailyCooldownHours", 24),
            xp_per_message=row.get("xpPerMessage", 10),
            xp_cooldown_seconds=row.get("xpCooldownSeconds", 60),
            level_base_xp=row.get("levelBaseXp", 100),
            level_multiplier=row.get("levelMultiplier", 1.5),
            level_roles=row.get("levelRoles", {}),
            level_up_channel_id=row.get("levelUpChannelId"),
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "guildId": self.guild_id,
            "dailyReward": self.daily_reward,
            "dailyCooldownHours": self.daily_cooldown_hours,
            "xpPerMessage": self.xp_per_message,
            "xpCooldownSeconds": self.xp_cooldown_seconds,
            "levelBaseXp": self.level_base_xp,
            "levelMultiplier": self.level_multiplier,
            "levelRoles": self.level_roles,
            "levelUpChannelId": self.level_up_channel_id,
        }
