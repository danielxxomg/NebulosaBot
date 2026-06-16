"""Infraction model — mirrors the Infraction table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Infraction:
    """Moderation infraction stored in Supabase.

    Mirrors the Infraction table. type is one of: WARN, MUTE, KICK, BAN.
    """

    id: str  # UUID PK
    guild_id: str
    target_id: str
    moderator_id: str
    type: str  # WARN / MUTE / KICK / BAN
    reason: str
    created_at: datetime
    active: bool = True
    expires_at: datetime | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> Infraction:
        """Build an Infraction from a Supabase row (camelCase keys)."""
        return cls(
            id=row["id"],
            guild_id=row["guildId"],
            target_id=row["targetId"],
            moderator_id=row["moderatorId"],
            type=row["type"],
            reason=row["reason"],
            active=row.get("active", True),
            expires_at=row.get("expiresAt"),
            created_at=row["createdAt"],
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "id": self.id,
            "guildId": self.guild_id,
            "targetId": self.target_id,
            "moderatorId": self.moderator_id,
            "type": self.type,
            "reason": self.reason,
            "active": self.active,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
