"""Ticket invariant helpers — pure functions for ticket lifecycle rules.

These helpers enforce the shared ticket invariant contract used identically
by the bot (``TicketService``) and the dashboard (TS mirror). They are PURE:
no Discord, no database, no side effects. Each validator either returns
``None`` on success or raises ``ValueError`` with a human-readable reason.

Wiring into ``bot.services.ticket_service`` happens in PR2; the dashboard
mirror lives in ``dashboard/lib/actions/ticket-actions.ts`` (PR3).

Contract scenarios TI-001..TI-038 are mirrored in
``tests/contract/test_ticket_invariants.py``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Per-ticket note cap enforced by the dashboard and the bot service (B5).
NOTE_CAP: int = 50

# Dedup window (seconds) for same-author duplicate notes.
NOTE_DEDUP_WINDOW_SECONDS: float = 2.0


# ---------------------------------------------------------------------------
# Note dedup
# ---------------------------------------------------------------------------


def compute_note_hash(content: str) -> str:
    """Return the SHA256 hex digest of normalized note *content*.

    Normalization = ``" ".join(content.strip().lower().split())`` — trim,
    lowercase, collapse all internal whitespace runs to a single space. This
    makes ``"  Hello   World  "`` and ``"hello world"`` hash identically, so
    cosmetic differences do not defeat the dedup check.
    """
    normalized = " ".join(content.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_duplicate_note(
    new_hash: str,
    author_id: str,
    existing_note_hashes: list[str],
    window: float = NOTE_DEDUP_WINDOW_SECONDS,
) -> bool:
    """Return ``True`` if *new_hash* matches a recent same-author note.

    The caller is expected to fetch recent same-author notes within the
    *window* via ``Database.get_recent_notes_for_dedup`` (which filters by
    ``authorId`` and ``createdAt >= now() - window``) and pass their
    precomputed hashes here. This function performs only the hash membership
    comparison — the time window and author scoping are enforced upstream by
    the database query, keeping this helper pure and trivially testable.

    Args:
        new_hash: ``compute_note_hash`` of the incoming note content.
        author_id: The incoming note's author (kept for API symmetry; author
            filtering is done by the upstream query).
        existing_note_hashes: Hashes of the author's notes already in the
            window.
        window: Dedup window in seconds (enforced upstream; accepted here for
            API symmetry with ``get_recent_notes_for_dedup``).

    Returns:
        ``True`` if *new_hash* is present in *existing_note_hashes*.
    """
    _ = (author_id, window)  # author + window are enforced by the upstream query
    return new_hash in existing_note_hashes


# ---------------------------------------------------------------------------
# Status state machine
# ---------------------------------------------------------------------------


def check_can_claim(ticket_status: str, claimed_by: str | None) -> None:
    """Validate that a claim may proceed.

    Claim is valid only when the ticket is ``open`` AND has no current
    claimant. Reassignment MUST use transfer, not claim (no-overwrite rule).
    Raises ``ValueError`` otherwise.
    """
    if ticket_status != "open":
        raise ValueError(f"Cannot claim a ticket with status {ticket_status!r} (must be open)")
    if claimed_by is not None:
        raise ValueError("Cannot claim a ticket that is already claimed (use transfer)")


def check_can_close(ticket_status: str) -> None:
    """Validate that a close may proceed.

    Close is valid for ``open`` or ``claimed``. Closing an already-closed
    ticket raises ``ValueError``.
    """
    if ticket_status == "closed":
        raise ValueError("Cannot close a ticket that is already closed")
    if ticket_status not in ("open", "claimed"):
        raise ValueError(f"Cannot close a ticket with status {ticket_status!r}")


def check_can_reopen(ticket_status: str) -> None:
    """Validate that a reopen may proceed.

    Reopen is valid only for ``closed`` tickets (status-guard idempotency).
    Raises ``ValueError`` for ``open`` or ``claimed``.
    """
    if ticket_status != "closed":
        raise ValueError(f"Cannot reopen a ticket with status {ticket_status!r} (must be closed)")


def check_can_transfer(ticket_status: str, current_claimed_by: str | None, target_id: str | None) -> None:
    """Validate that a transfer may proceed.

    Transfer reassigns ``claimedBy`` and sets ``status='claimed'`` (implicit
    re-claim). Rules:
    - A closed ticket cannot be transferred (reopen it first).
    - The target MUST be specified.
    - The target MUST differ from the current claimant (no-op transfer denied).

    Raises ``ValueError`` on any violation.
    """
    if ticket_status == "closed":
        raise ValueError("Cannot transfer a closed ticket (reopen it first)")
    if target_id is None:
        raise ValueError("Cannot transfer a ticket without a target staff member")
    if current_claimed_by is not None and target_id == current_claimed_by:
        raise ValueError("Cannot transfer a ticket to the same staff member who already claimed it")


# ---------------------------------------------------------------------------
# Notes — cap + ownership
# ---------------------------------------------------------------------------


def check_can_add_note(existing_count: int, cap: int = NOTE_CAP) -> None:
    """Validate that a note may be added given the current *existing_count*.

    Raises ``ValueError`` when the ticket has reached or exceeded *cap* notes.
    """
    if existing_count >= cap:
        raise ValueError(f"Cannot add a note: ticket has reached the {cap}-note cap ({existing_count} notes)")


def check_can_delete_note(note_author_id: str, actor_id: str) -> None:
    """Validate that *actor_id* may delete a note authored by *note_author_id*.

    Only the note's author may delete it (author-only rule). Raises
    ``ValueError`` for any other actor.
    """
    if actor_id != note_author_id:
        raise ValueError("Only the note's author may delete a note")


# ---------------------------------------------------------------------------
# Subticket parentId FK invariants
# ---------------------------------------------------------------------------


def check_subticket_parent(
    parent: dict | None,
    parent_guild_id: str,
    current_guild_id: str,
    current_id: str | None = None,
) -> None:
    """Validate the *parent* is a legal subticket parent for the current ticket.

    Rules (depth max 2, app-level FK — no DB FK):
    - The parent row MUST exist (not ``None``).
    - The parent MUST belong to the same guild as the child ticket.
    - The parent MUST NOT already have a ``parentId`` (depth cap = 2).
    - The parent MUST NOT be the child itself (no self-reference).

    Args:
        parent: The candidate parent ticket row (camelCase), or ``None``.
        parent_guild_id: The parent ticket's guild snowflake.
        current_guild_id: The child ticket's guild snowflake.
        current_id: The child ticket's UUID (optional; used only for the
            self-reference check).

    Raises ``ValueError`` on any invariant violation.
    """
    if parent is None:
        raise ValueError("Subticket parent not found")
    if current_id is not None and parent.get("id") == current_id:
        raise ValueError("A ticket cannot be its own parent (self-reference)")
    if parent.get("parentId") is not None:
        raise ValueError("Subticket parent is itself a subticket (depth limit is 2)")
    if parent_guild_id != current_guild_id:
        raise ValueError("Subticket parent must belong to the same guild as the child")


# ---------------------------------------------------------------------------
# /reopen ticket reference parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TicketRef:
    """A parsed /reopen ticket reference — exactly one of *number*/*uuid* set.

    The cog resolves a *number* via ``Database.get_ticket_by_number(guild_id, n)``
    and a *uuid* via ``Database.get_ticket(id)`` plus a guild-scope check.
    """

    number: int | None = None
    uuid: str | None = None


# UUID v4-ish (we do not enforce version — any 8-4-4-4-12 hex block).
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# A run of digits, optionally prefixed with '#'.
_NUMBER_RE = re.compile(r"^#?(\d+)$")


def parse_ticket_ref(ref_str: str | None) -> TicketRef | None:
    """Parse a ``/reopen`` ticket reference into a :class:`TicketRef`.

    Accepts (after stripping an optional ``ticket:`` prefix):
        - ``#0003`` or ``0003`` → ``TicketRef(number=3)``
        - a UUID (``8-4-4-4-12`` hex) → ``TicketRef(uuid=...)``

    Returns ``None`` for empty/whitespace input or unparseable strings so the
    caller (``/reopen`` cog) can distinguish "no arg" (legacy channel lookup)
    from "bad arg" (user-facing error).

    The literal guidance text ``/reopen ticket:#0003`` is valid: the slash
    option is ``ticket_ref`` whose value ``ticket:#0003`` the parser strips to
    ``#0003`` → ``number=3``. A bare ``#0003`` value also parses to ``3``.
    """
    if ref_str is None:
        return None
    value = ref_str.strip()
    if not value:
        return None
    # Strip an optional 'ticket:' prefix (case-insensitive).
    if value.lower().startswith("ticket:"):
        value = value[len("ticket:") :]
    value = value.strip()
    if not value:
        return None
    # UUID?
    if _UUID_RE.match(value):
        return TicketRef(uuid=value.lower())
    # #0003 / 0003?
    num_match = _NUMBER_RE.match(value)
    if num_match is not None:
        return TicketRef(number=int(num_match.group(1)))
    return None
