"""Ticket model — mirrors the Ticket table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

_ACTIVE_STATUSES = frozenset({"open", "claimed"})
_VALID_REPAIR_COMBINATIONS = frozenset({"close/repaired", "no_op/already_closed", "no_op/skipped", "no_op/error"})


@dataclass(frozen=True)
class IntegrityEvidence:
    """Read-only evidence that an active ticket's channel is missing."""

    ticket_id: str
    guild_id: str
    channel_id: str | None
    status: str
    channel_exists: bool
    corroborated: bool

    def __post_init__(self) -> None:
        """Derive corroboration from immutable ticket and channel evidence."""
        object.__setattr__(
            self,
            "corroborated",
            self.status in _ACTIVE_STATUSES and not self.channel_exists,
        )

    @classmethod
    def from_db_row(cls, row: dict[str, Any], channel_exists: bool) -> IntegrityEvidence:
        """Build evidence from a ticket row and a completed channel check."""
        return cls(
            ticket_id=row["ticketId"],
            guild_id=row["guildId"],
            channel_id=row.get("channelId"),
            status=row["status"],
            channel_exists=channel_exists,
            corroborated=False,
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize evidence using the ticket table's camelCase convention."""
        return {
            "ticketId": self.ticket_id,
            "guildId": self.guild_id,
            "channelId": self.channel_id,
            "status": self.status,
            "channelExists": self.channel_exists,
            "corroborated": self.corroborated,
        }


@dataclass(frozen=True)
class RepairResult:
    """Deterministic, auditable result of one ticket repair attempt."""

    ticket_id: str
    guild_id: str
    action: str
    outcome: str
    reason: str | None
    evidence_id: str | None
    timestamp: datetime

    def __post_init__(self) -> None:
        """Reject wire values outside the documented repair contract."""
        combination = f"{self.action}/{self.outcome}"
        if combination not in _VALID_REPAIR_COMBINATIONS:
            raise ValueError(f"Invalid repair action/outcome combination: {self.action}/{self.outcome}")
        if combination == "close/repaired" and not self.evidence_id:
            raise ValueError("Repaired close requires evidence_id")

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> RepairResult:
        """Build a result from a camelCase audit/evidence row."""
        timestamp = row["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return cls(
            ticket_id=row["ticketId"],
            guild_id=row["guildId"],
            action=row["action"],
            outcome=row["outcome"],
            reason=row.get("reason"),
            evidence_id=row.get("evidenceId"),
            timestamp=timestamp,
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize the result using camelCase persistence keys."""
        return {
            "ticketId": self.ticket_id,
            "guildId": self.guild_id,
            "action": self.action,
            "outcome": self.outcome,
            "reason": self.reason,
            "evidenceId": self.evidence_id,
            "timestamp": self.timestamp.isoformat(),
        }


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
    custom_fields: dict[str, Any] | None = None

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Ticket:
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

    def to_db_dict(self) -> dict[str, Any]:
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
