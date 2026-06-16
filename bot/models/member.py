"""Member model — mirrors the Member table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Member:
    """Per-guild member data stored in Supabase.

    Mirrors the Member table. Composite primary key: (guild_id, user_id).
    """

    guild_id: str
    user_id: str
    xp: int = 0
    level: int = 0
    warnings: int = 0
    coins: int = 0
    last_daily: datetime | None = None
    last_xp_gain: datetime | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> Member:
        """Build a Member from a Supabase row (camelCase keys)."""
        return cls(
            guild_id=row["guildId"],
            user_id=row["userId"],
            xp=row.get("xp", 0),
            level=row.get("level", 0),
            warnings=row.get("warnings", 0),
            coins=row.get("coins", 0),
            last_daily=row.get("lastDaily"),
            last_xp_gain=row.get("lastXpGain"),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "guildId": self.guild_id,
            "userId": self.user_id,
            "xp": self.xp,
            "level": self.level,
            "warnings": self.warnings,
            "coins": self.coins,
            "lastDaily": self.last_daily.isoformat() if self.last_daily else None,
            "lastXpGain": self.last_xp_gain.isoformat() if self.last_xp_gain else None,
        }
