"""Ticket model — mirrors the Ticket table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Ticket:
    """Support ticket stored in Supabase.

    Mirrors the Ticket table. ticket_number is sequential per guild.
    """

    id: str  # UUID PK
    ticket_number: int
    guild_id: str
    author_id: str
    channel_id: str
    status: str  # open / claimed / closed
    created_at: datetime
    last_activity: datetime
    category_id: str | None = None
    claimed_by: str | None = None
    transcript_url: str | None = None
    closed_at: datetime | None = None
    parent_id: str | None = None  # self-referential; one level deep (sub-tickets)
    subject: str | None = None
    description: str | None = None
    custom_fields: dict | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> Ticket:
        """Build a Ticket from a Supabase row (camelCase keys)."""
        return cls(
            id=row["id"],
            ticket_number=row["ticketNumber"],
            guild_id=row["guildId"],
            author_id=row["authorId"],
            channel_id=row["channelId"],
            category_id=row.get("categoryId"),
            status=row["status"],
            claimed_by=row.get("claimedBy"),
            transcript_url=row.get("transcriptUrl"),
            created_at=row["createdAt"],
            closed_at=row.get("closedAt"),
            last_activity=row["lastActivity"],
            parent_id=row.get("parentId"),
            subject=row.get("subject"),
            description=row.get("description"),
            custom_fields=row.get("customFields"),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "id": self.id,
            "ticketNumber": self.ticket_number,
            "guildId": self.guild_id,
            "authorId": self.author_id,
            "channelId": self.channel_id,
            "categoryId": self.category_id,
            "status": self.status,
            "claimedBy": self.claimed_by,
            "transcriptUrl": self.transcript_url,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "closedAt": self.closed_at.isoformat() if self.closed_at else None,
            "lastActivity": self.last_activity.isoformat() if self.last_activity else None,
            "parentId": self.parent_id,
            "subject": self.subject,
            "description": self.description,
            "customFields": self.custom_fields,
        }
