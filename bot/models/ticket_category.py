"""TicketCategory model — mirrors the ticket_category table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TicketCategory:
    """Ticket category stored in Supabase.

    Mirrors the ticket_category table. Categories are guild-scoped and ordered
    by position for display in the ticket panel dropdown.
    """

    id: str  # UUID PK
    guild_id: str
    name: str
    emoji: str | None = None
    description: str | None = None
    position: int = 0
    active: bool = True
    created_at: datetime | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> TicketCategory:
        """Build a TicketCategory from a Supabase row (camelCase keys)."""
        return cls(
            id=row["id"],
            guild_id=row["guildId"],
            name=row["name"],
            emoji=row.get("emoji"),
            description=row.get("description"),
            position=row["position"],
            active=row.get("active", True),
            created_at=row.get("createdAt"),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "id": self.id,
            "guildId": self.guild_id,
            "name": self.name,
            "emoji": self.emoji,
            "description": self.description,
            "position": self.position,
            "active": self.active,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
