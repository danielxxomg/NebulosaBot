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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


def check_can_unclaim(actor_id: str, ticket: dict[str, Any], *, is_mod: bool) -> None:
    """Validate that *actor_id* may unclaim the *ticket*.

    Unclaim is allowed when the actor is the current claimer OR has the mod
    role. The ticket MUST be currently claimed (``claimedBy`` is not ``None``).

    Raises ``ValueError`` on any violation.
    """
    claimed_by = ticket.get("claimedBy")
    if claimed_by is None:
        raise ValueError("Cannot unclaim a ticket that is not currently claimed")
    if actor_id == claimed_by or is_mod:
        return
    raise ValueError("Only the claimer or a moderator can unclaim this ticket")


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
# Per-user-per-category limit
# ---------------------------------------------------------------------------


def check_one_ticket_per_user_per_category(
    user_id: str,
    category_id: str | None,
    parent_id: str | None,
    count_fn: Callable[[str, str], int],
) -> None:
    """Validate that *user_id* does not already have an open ticket in *category_id*.

    An open ticket is one with status ``open`` or ``claimed``.  The check is
    skipped when *parent_id* is not ``None`` (subticket carve-out) or when
    *category_id* is ``None`` (uncategorized tickets have no limit).

    *count_fn* is injected for testability — it receives ``(user_id,
    category_id)`` and must return the number of open/claimed tickets the user
    already has in that category.

    Raises ``ValueError`` when the user already has an open ticket in the
    given category.
    """
    if parent_id is not None:
        return
    if category_id is None:
        return
    open_count = count_fn(user_id, category_id)
    if open_count > 0:
        raise ValueError(
            f"User {user_id} already has an open ticket in category {category_id!r}"
        )


# ---------------------------------------------------------------------------
# Edit category permission
# ---------------------------------------------------------------------------


def check_can_edit_category(
    actor_id: str,
    ticket: dict[str, Any],
    *,
    is_mod: bool,
) -> None:
    """Validate that *actor_id* may edit the ticket's category.

    Edit is allowed only when the actor has the mod role or admin permission
    (``is_mod=True``).  Ticket authors without the mod role are denied.

    Mirrors :func:`check_can_unclaim`'s ``is_mod`` keyword signature so the
    pure invariant is not coupled to Discord objects.

    Raises ``ValueError`` on any violation.
    """
    if is_mod:
        return
    raise ValueError("Only moderators can edit a ticket's category")


# ---------------------------------------------------------------------------
# Subticket parentId FK invariants
# ---------------------------------------------------------------------------


def check_subticket_parent(
    parent: dict[str, Any] | None,
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


# ---------------------------------------------------------------------------
# Repair authority — provisional one-role core model + scoped exceptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairAuthority:
    """Facts about the actor requesting a ticket-integrity repair.

    Pure — no Discord objects. ``guild_id`` is the actor's own guild (``None``
    for a cross-guild operator). ``deletion_actor`` records that the actor
    performed the channel deletion, and is INFORMATIONAL ONLY: it never
    participates in the authorization decision.
    """

    actor_id: str
    guild_id: str | None
    target_guild_id: str
    is_guild_owner: bool = False
    is_administrator: bool = False
    has_mod_role: bool = False
    is_bot_owner: bool = False
    deletion_actor: bool = False


@dataclass(frozen=True)
class GlobalMutationGrant:
    """An explicit, targeted, audited grant for a cross-guild/global mutation.

    Operator diagnosis is read-only by default; mutation requires this grant
    naming the actor, the scope, the target guild, a non-empty auditable
    reason, and explicit confirmation.
    """

    actor_id: str
    scope: str
    target_guild_id: str
    reason: str
    confirmed: bool


@dataclass(frozen=True)
class AuthorityDecision:
    """The outcome of evaluating repair authority for one attempt."""

    allowed: bool
    scope: str  # "guild" | "global"
    reason: str | None


def evaluate_repair_authority(
    authority: RepairAuthority,
    global_grant: GlobalMutationGrant | None = None,
) -> AuthorityDecision:
    """Evaluate whether *authority* may mutate a ticket in its target guild.

    Two distinct audiences:

    - **Guild-scoped actors** (the configured moderator role, the guild owner,
      and Discord Administrators) are authorized ONLY for their own guild.
      The configured moderator role is the single canonical role; the owner
      and Administrator bypass the role check only inside their own guild.
      Cross-guild targeting is always denied.
    - **The bot owner** (``is_bot_owner=True``) receives read-only diagnosis
      globally. Any cross-guild/global mutation requires an explicit
      :class:`GlobalMutationGrant` that names this actor, the target, a
      non-empty auditable reason, and explicit confirmation. A silent
      mutation bypass never exists.

    ``deletion_actor`` is ignored — it is informational context only and can
    never make an unsafe claim actionable.
    """
    # Bot owner: diagnosis is read-only; mutation needs an explicit grant.
    if authority.is_bot_owner:
        if global_grant is None:
            return AuthorityDecision(False, "global", "operator_mutation_requires_grant")
        if not global_grant.confirmed:
            return AuthorityDecision(False, "global", "grant_unconfirmed")
        if not global_grant.reason or not global_grant.reason.strip():
            return AuthorityDecision(False, "global", "grant_missing_reason")
        if global_grant.actor_id != authority.actor_id:
            return AuthorityDecision(False, "global", "grant_actor_mismatch")
        if global_grant.target_guild_id != authority.target_guild_id:
            return AuthorityDecision(False, "global", "grant_target_mismatch")
        return AuthorityDecision(True, "global", global_grant.reason)

    # Guild-scoped actors: only their own guild.
    if authority.guild_id is None or authority.guild_id != authority.target_guild_id:
        return AuthorityDecision(False, "guild", "cross_guild_denied")

    if authority.is_guild_owner or authority.is_administrator or authority.has_mod_role:
        return AuthorityDecision(True, "guild", None)

    return AuthorityDecision(False, "guild", "insufficient_authority")


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
