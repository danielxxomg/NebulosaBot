"""TicketNote model — mirrors the ticket_note table.

Staff-only annotation attached to a ticket. NOT visible to the ticket opener.
Created by Migration 003 (tickets-subsidiados).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TicketNote:
    """Staff note stored in Supabase.

    Mirrors the ``ticket_note`` table (camelCase columns). Notes are capped
    at 50 per ticket and ordered newest-first by the caller.
    """

    id: str  # UUID PK
    ticket_id: str
    author_id: str
    content: str
    created_at: datetime | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> TicketNote:
        """Build a TicketNote from a Supabase row (camelCase keys)."""
        return cls(
            id=row["id"],
            ticket_id=row["ticketId"],
            author_id=row["authorId"],
            content=row["content"],
            created_at=row.get("createdAt"),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "id": self.id,
            "ticketId": self.ticket_id,
            "authorId": self.author_id,
            "content": self.content,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
