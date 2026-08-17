"""Ticket model — mirrors the Ticket table."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from bot.config import INTEGRITY_EVIDENCE_FRESHNESS_SECONDS

_ACTIVE_STATUSES = frozenset({"open", "claimed"})
_VALID_REPAIR_COMBINATIONS = frozenset(
    {
        "close/repaired",
        "close/error",
        "no_op/already_closed",
        "no_op/skipped",
        "no_op/quarantined",
        "no_op/denied",
        "no_op/error",
    }
)

# Outcomes that MUST carry a non-empty review/audit reason.
_REASON_REQUIRED_OUTCOMES = frozenset({"quarantined", "error", "denied"})


@dataclass(frozen=True)
class IntegrityEvidence:
    """Read-only evidence that an active ticket's channel is missing.

    Tri-state ``channel_exists`` (``True``/``False``/``None``) and tri-state
    ``corroborated``: ``None`` means unknown/unresolved — never coerced to
    ``False``. Corroboration requires an active ticket, an explicit
    ``channel_exists=False`` observation, and evidence observed within the
    configured freshness window (``bot.config``). Construction never mutates
    ticket state.
    """

    ticket_id: str
    guild_id: str
    channel_id: str | None
    status: str
    channel_exists: bool | None
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str | None = None
    corroborated: bool | None = None

    def __post_init__(self) -> None:
        """Derive corroboration from immutable ticket and channel evidence.

        Corroboration is ``True`` only when the ticket is active, the channel
        observation is an explicit absence, and the observation is fresh AND
        not future-dated. ``None`` channel existence, stale observations, and
        future-dated observations remain unresolved (``None``) — never coerced
        to ``False``. A live channel or a non-active ticket is
        deterministically ``False`` (not a zombie candidate). A
        caller-supplied ``corroborated`` value is always re-derived from the
        immutable fields: it can never fabricate a corroborated claim.
        Construction never mutates ticket state.
        """
        if self.channel_exists is None:
            resolved: bool | None = None
        elif self.status not in _ACTIVE_STATUSES or self.channel_exists is not False:
            resolved = False
        else:
            age = datetime.now(UTC) - self.observed_at
            if age < timedelta(0):
                # Future-dated observation: fail closed, never corroborate.
                resolved = None
            elif age <= timedelta(seconds=INTEGRITY_EVIDENCE_FRESHNESS_SECONDS):
                resolved = True
            else:
                resolved = None
        object.__setattr__(self, "corroborated", resolved)

    @classmethod
    def from_db_row(cls, row: dict[str, Any], channel_exists: bool | None = None) -> IntegrityEvidence:
        """Build evidence from a ticket row and a completed channel check."""
        observed_at = row.get("observedAt")
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        evidence_id = row.get("evidenceId")
        return cls(
            ticket_id=row["ticketId"],
            guild_id=row["guildId"],
            channel_id=row.get("channelId"),
            status=row["status"],
            channel_exists=row.get("channelExists", channel_exists),
            observed_at=observed_at or datetime.now(UTC),
            evidence_id=evidence_id or str(uuid.uuid4()),
            source=row.get("source"),
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize evidence using the ticket table's camelCase convention."""
        return {
            "ticketId": self.ticket_id,
            "guildId": self.guild_id,
            "channelId": self.channel_id,
            "status": self.status,
            "channelExists": self.channel_exists,
            "observedAt": self.observed_at.isoformat(),
            "evidenceId": self.evidence_id,
            "source": self.source,
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
        # Denied/quarantined/error outcomes must be reviewable: a non-empty
        # reason is mandatory so no failure path is silently recorded.
        if self.outcome in _REASON_REQUIRED_OUTCOMES and not (self.reason and self.reason.strip()):
            raise ValueError(f"Repair outcome {self.outcome!r} requires a non-empty reason")

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


@dataclass(frozen=True)
class CloseResult:
    """Deterministic outcome of one ticket close lifecycle.

    Ported from the superseded ``ticket-integrity-reconciliation`` delta so
    the canonical recovery lifecycle keeps one close contract. Callers can
    distinguish ``success``, ``denied``, and ``error`` from the return value;
    denied/error outcomes MUST never be rendered or audited as success.
    """

    ticket_id: str
    outcome: str  # success | denied | error
    close_reason: str | None
    transcript_url: str | None
    evidence_id: str | None  # populated for repair-driven closes


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
