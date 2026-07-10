"""Member model — mirrors the Member table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _parse_dt(value: str | datetime | None) -> datetime | None:
    """Parse an ISO-8601 string to datetime, or pass through existing instances."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


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
    daily_streak: int = 0
    last_daily_reset: datetime | None = None
    last_daily: datetime | None = None
    last_xp_gain: datetime | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> Member:
        """Build a Member from a Supabase row (camelCase keys).

        ISO-8601 strings for datetime fields are parsed via
        ``datetime.fromisoformat()``.  Already-constructed ``datetime``
        instances (e.g. from ORM or test fixtures) pass through unchanged.
        """
        return cls(
            guild_id=row["guildId"],
            user_id=row["userId"],
            xp=row.get("xp", 0),
            level=row.get("level", 0),
            warnings=row.get("warnings", 0),
            coins=row.get("coins", 0),
            daily_streak=row.get("dailyStreak", 0),
            last_daily_reset=_parse_dt(row.get("lastDailyReset")),
            last_daily=_parse_dt(row.get("lastDaily")),
            last_xp_gain=_parse_dt(row.get("lastXpGain")),
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
            "dailyStreak": self.daily_streak,
            "lastDailyReset": self.last_daily_reset.isoformat() if self.last_daily_reset else None,
            "lastDaily": self.last_daily.isoformat() if self.last_daily else None,
            "lastXpGain": self.last_xp_gain.isoformat() if self.last_xp_gain else None,
        }
