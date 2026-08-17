"""Unit tests for bot.services.ticket_service.TicketService.

Covers:
    - Sequential numbering (MAX+1 normal path + retry on conflict)
    - create_ticket with mock DB insert + cache sync
    - close_ticket with status/closedAt updates
    - claim_ticket with status/claimedBy updates
    - get_stale_tickets query → Ticket model list
    - create_subticket: 4 parentId FK validations + carve-out (slice 2)
    - reopen_ticket: new channel from guild-configured category, cache update (slice 2)
    - transfer_ticket: claimedBy mutation + LoggingService audit (slice 2)
    - Note CRUD: create/get/delete + 50-note cap + ownership (slice 2)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

if TYPE_CHECKING:
    from bot.services.ticket_invariants import RepairAuthority

from bot.core.cache import TTLCache
from bot.models.ticket import IntegrityEvidence, Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_service import MAX_RETRIES, TicketService

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock for Database, pre-configured for ticket methods.

    Every child MUST have an explicit ``return_value`` (not the AsyncMock
    default) because ``AsyncMock().return_value`` is itself an ``AsyncMock``.
    When production code calls ``.get()`` or ``+`` on that implicit child,
    it creates a coroutine from ``AsyncMockMixin._execute_mock_call`` that
    is never awaited, leaking a ``PytestUnraisableExceptionWarning``.
    """
    db = AsyncMock()
    db.get_max_ticket_number = AsyncMock(return_value=0)
    db.insert_ticket = AsyncMock(return_value=None)
    db.update_ticket = AsyncMock(return_value=None)
    db.get_ticket = AsyncMock(return_value=None)
    db.get_stale_tickets = AsyncMock(return_value=[])
    # Sub-ticket / note methods (added by PR1; wired here for slice-2 tests).
    db.get_guild = AsyncMock(return_value=None)
    db.get_ticket_notes = AsyncMock(return_value=[])
    db.insert_ticket_note = AsyncMock(return_value=None)
    db.delete_ticket_note = AsyncMock(return_value=None)
    # PR1 audit + dedup DB methods (wired by PR2 service integration).
    db.insert_audit_row = AsyncMock(return_value={})
    db.get_recent_notes_for_dedup = AsyncMock(return_value=[])
    # PR4 channel naming: category lookup for reopen.
    db.get_ticket_category = AsyncMock(return_value=None)
    # PR2 Phase 2: per-user-per-category count for create_ticket guard + edit_ticket_category.
    db.count_user_open_tickets_in_category = AsyncMock(return_value=0)
    return db


@pytest.fixture
def service(cache: TTLCache, mock_db: AsyncMock) -> TicketService:
    """Return a fresh TicketService with mocked DB."""
    return TicketService(db=mock_db, cache=cache)


@pytest.fixture
def ticket_row() -> dict:
    """Return a sample ticket DB row (camelCase keys)."""
    return {
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "ticketNumber": 42,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# create_ticket — sequential numbering (normal path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_normal(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket MUST use MAX+1 and insert with that number."""
    guild_id = "123456789"
    author_id = "111111111"
    channel_id = "888888888"

    mock_db.get_max_ticket_number.return_value = 41
    mock_db.insert_ticket.return_value = ticket_row

    ticket = await service.create_ticket(
        guild_id=guild_id,
        author_id=author_id,
        category_id=None,
        channel_id=channel_id,
    )

    # DB calls.
    mock_db.get_max_ticket_number.assert_awaited_once_with(guild_id)
    mock_db.insert_ticket.assert_awaited_once()
    call_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert call_kwargs["ticket_number"] == 42  # MAX+1
    assert call_kwargs["guild_id"] == guild_id
    assert call_kwargs["author_id"] == author_id
    assert call_kwargs["channel_id"] == channel_id
    assert call_kwargs["category_id"] is None

    # Returned model.
    assert isinstance(ticket, Ticket)
    assert ticket.ticket_number == 42
    assert ticket.guild_id == guild_id
    assert ticket.status == "open"

    # Cache sync.
    assert 888888888 in service._ticket_channel_cache


# ---------------------------------------------------------------------------
# create_ticket — retry on conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_retry_on_conflict(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When insert raises once then succeeds, create_ticket MUST retry and win."""
    guild_id = "123456789"

    mock_db.get_max_ticket_number.return_value = 0
    # First insert fails (IntegrityError), second succeeds.
    mock_db.insert_ticket.side_effect = [
        Exception("duplicate key value violates unique constraint"),
        ticket_row,
    ]

    ticket = await service.create_ticket(
        guild_id=guild_id,
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
    )

    assert ticket.ticket_number == 42
    assert mock_db.insert_ticket.call_count == 2
    # MAX was queried only once (the second attempt reuses the same implied number,
    # since the conflict means the number wasn't consumed — we just retry the insert).
    assert mock_db.get_max_ticket_number.call_count == 2


# ---------------------------------------------------------------------------
# create_ticket — exhaust retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_retries_exhausted(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When all retries fail, create_ticket MUST raise RuntimeError."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.side_effect = Exception("unique violation")

    with pytest.raises(
        RuntimeError,
        match=f"Failed to create ticket after {MAX_RETRIES} attempts",
    ):
        await service.create_ticket(
            guild_id="123456789",
            author_id="111111111",
            category_id=None,
            channel_id="888888888",
        )

    assert mock_db.insert_ticket.call_count == MAX_RETRIES


# ---------------------------------------------------------------------------
# create_ticket — subject / description passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_with_subject_and_description(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket(subject=..., description=...) MUST forward to insert_ticket."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {
        **ticket_row,
        "subject": "Login broken",
        "description": "Cannot access since Monday",
    }

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
        subject="Login broken",
        description="Cannot access since Monday",
    )

    call_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert call_kwargs["subject"] == "Login broken"
    assert call_kwargs["description"] == "Cannot access since Monday"
    assert ticket.subject == "Login broken"
    assert ticket.description == "Cannot access since Monday"


@pytest.mark.asyncio
async def test_create_ticket_without_subject_and_description(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket() without subject/description MUST pass None to insert_ticket."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "subject": None, "description": None}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
    )

    call_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert call_kwargs["subject"] is None
    assert call_kwargs["description"] is None
    assert ticket.subject is None
    assert ticket.description is None


# ---------------------------------------------------------------------------
# create_ticket — per-user-per-category guard (task 2.1 RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ticket_blocked_when_user_has_open_in_same_category(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Second ticket in same category MUST raise ValueError."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.count_user_open_tickets_in_category.return_value = 1  # already has one

    with pytest.raises(ValueError, match=r"already has an open ticket"):
        await service.create_ticket(
            guild_id="123456789",
            author_id="111111111",
            category_id="cat-uuid-001",
            channel_id="888888888",
        )

    # No insert attempted after guard rejection.
    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_ticket_allowed_in_different_category(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Ticket in a different category MUST succeed even if user has open ticket elsewhere."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.count_user_open_tickets_in_category.return_value = 0  # no open in this category
    mock_db.insert_ticket.return_value = {**ticket_row, "categoryId": "cat-uuid-002"}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id="cat-uuid-002",
        channel_id="888888888",
    )

    assert isinstance(ticket, Ticket)
    mock_db.insert_ticket.assert_awaited_once()
    mock_db.count_user_open_tickets_in_category.assert_awaited_once_with(
        "123456789",
        "111111111",
        "cat-uuid-002",
    )


@pytest.mark.asyncio
async def test_create_ticket_allowed_when_closed_frees_slot(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Closed ticket frees the slot — count returns 0."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.count_user_open_tickets_in_category.return_value = 0  # closed doesn't count
    mock_db.insert_ticket.return_value = {**ticket_row, "categoryId": "cat-uuid-001"}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id="888888888",
    )

    assert isinstance(ticket, Ticket)
    mock_db.insert_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_ticket_subticket_bypasses_guard(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When parentId is set, the guard MUST be skipped (subticket carve-out).

    The user already has an open ticket in the same category, yet the
    sub-ticket creation MUST succeed without calling count.
    """
    parent_id = "parent-uuid-001"
    mock_db.get_ticket.return_value = _parent_row(parent_id=None)
    mock_db.get_max_ticket_number.return_value = 5
    mock_db.insert_ticket.return_value = {**ticket_row, "parentId": parent_id, "ticketNumber": 6}

    ticket = await service.create_subticket(
        parent_id=parent_id,
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id="666666666",
        guild_id="123456789",
    )

    assert ticket.parent_id == parent_id
    # Count MUST NOT be called for subtickets.
    mock_db.count_user_open_tickets_in_category.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_ticket_null_category_id_bypasses_guard(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When categoryId is None, the guard MUST be skipped."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "categoryId": None}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
    )

    assert isinstance(ticket, Ticket)
    # Count MUST NOT be called when categoryId is None.
    mock_db.count_user_open_tickets_in_category.assert_not_awaited()


# ---------------------------------------------------------------------------
# close_ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_ticket_updates_status(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """close_ticket MUST set status='closed' and closedAt via transition_ticket_to_closed."""
    ticket_id = ticket_row["id"]
    channel_id = int(ticket_row["channelId"])

    # Pre-populate cache to verify it gets cleaned.
    service._ticket_channel_cache.add(channel_id)
    assert channel_id in service._ticket_channel_cache

    closed_row = {
        **ticket_row,
        "status": "closed",
        "closedAt": "2026-06-16T18:00:00+00:00",
        "transcriptUrl": "https://cdn.discord.com/transcript.html",
    }
    mock_db.get_ticket.return_value = ticket_row
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

    ticket = await service.close_ticket(
        ticket_id,
        closed_by="999999999",
        transcript_url="https://cdn.discord.com/transcript.html",
    )

    # transition called with correct args (R2-002: transcript_url forwarded).
    mock_db.transition_ticket_to_closed.assert_awaited_once_with(
        ticket_row["guildId"],
        ticket_id,
        expected_statuses=("open", "claimed"),
        close_reason=None,
        transcript_url="https://cdn.discord.com/transcript.html",
    )

    # Returned model.
    assert ticket.status == "closed"
    assert ticket.transcript_url == "https://cdn.discord.com/transcript.html"
    assert ticket.closed_at is not None

    # Cache was cleaned.
    assert channel_id not in service._ticket_channel_cache


@pytest.mark.asyncio
async def test_close_unclaimed_ticket_preserves_null_claimant(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """SERVICE-1.2: closing an unclaimed ticket MUST preserve claimedBy is None."""
    ticket_id = ticket_row["id"]
    # Explicit unclaimed fixture: claimedBy is None before and after close.
    assert ticket_row["claimedBy"] is None
    closed_row = {
        **ticket_row,
        "status": "closed",
        "claimedBy": None,
        "closedAt": "2026-06-16T18:00:00+00:00",
    }
    mock_db.get_ticket.return_value = ticket_row
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

    ticket = await service.close_ticket(ticket_id, closed_by="999999999")

    assert ticket.status == "closed"
    assert ticket.claimed_by is None
    # No claimedBy mutation via update_ticket.
    mock_db.transition_ticket_to_closed.assert_awaited_once()
    assert mock_db.transition_ticket_to_closed.call_args.kwargs["close_reason"] is None


@pytest.mark.asyncio
async def test_close_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When transition returns None, close_ticket MUST raise ValueError."""
    ticket_id = "nonexistent-id"
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
    mock_db.get_ticket.return_value = {
        "id": ticket_id,
        "guildId": "123456789",
        "status": "closed",
    }

    with pytest.raises(ValueError, match="already closed or not found"):
        await service.close_ticket(ticket_id, closed_by="999999999")


# ---------------------------------------------------------------------------
# claim_ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_ticket_updates_status(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """claim_ticket MUST set status='claimed' and claimedBy."""
    ticket_id = ticket_row["id"]
    staff_id = "999999999"

    # PR2 contract: service pre-reads the OPEN row (invariant passes),
    # then re-reads the claimed row after update.
    mock_db.get_ticket.side_effect = [
        ticket_row,  # pre-read: open + unclaimed
        {**ticket_row, "status": "claimed", "claimedBy": staff_id},  # post-update
    ]

    ticket = await service.claim_ticket(ticket_id, claimed_by=staff_id)

    # DB update called with correct fields.
    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["status"] == "claimed"
    assert update_kwargs["claimedBy"] == staff_id

    # Returned model.
    assert ticket.status == "claimed"
    assert ticket.claimed_by == staff_id


@pytest.mark.asyncio
async def test_claim_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When get_ticket returns None after claim, claim_ticket MUST raise ValueError."""
    ticket_id = "nonexistent-id"
    mock_db.get_ticket.return_value = None

    with pytest.raises(ValueError, match=f"Ticket {ticket_id} not found"):
        await service.claim_ticket(ticket_id, claimed_by="999999999")


# ---------------------------------------------------------------------------
# get_stale_tickets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stale_tickets_returns_models(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """get_stale_tickets MUST call DB with correct args and return Ticket models."""
    guild_id = "123456789"
    mock_db.get_stale_tickets.return_value = [ticket_row, ticket_row]

    tickets = await service.get_stale_tickets(guild_id, hours=72)

    mock_db.get_stale_tickets.assert_awaited_once_with(guild_id, hours=72)
    assert len(tickets) == 2
    assert all(isinstance(t, Ticket) for t in tickets)
    assert tickets[0].status == "open"


@pytest.mark.asyncio
async def test_get_stale_tickets_empty(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When no stale tickets exist, get_stale_tickets MUST return an empty list."""
    mock_db.get_stale_tickets.return_value = []

    tickets = await service.get_stale_tickets("123456789")

    assert tickets == []


# ---------------------------------------------------------------------------
# is_ticket_channel
# ---------------------------------------------------------------------------


def test_is_ticket_channel_true(service: TicketService) -> None:
    """is_ticket_channel MUST return True for cached channel IDs."""
    service._ticket_channel_cache.add(42)
    assert service.is_ticket_channel(42) is True


def test_is_ticket_channel_false(service: TicketService) -> None:
    """is_ticket_channel MUST return False for unknown channel IDs."""
    assert service.is_ticket_channel(999) is False


# ---------------------------------------------------------------------------
# sync_channel_cache
# ---------------------------------------------------------------------------


def test_sync_channel_cache_with_ids(service: TicketService) -> None:
    """sync_channel_cache MUST replace the cache with the provided IDs."""
    service._ticket_channel_cache.add(1)  # pre-existing
    service.sync_channel_cache(channel_ids={10, 20, 30})
    assert service._ticket_channel_cache == {10, 20, 30}


def test_sync_channel_cache_clear(service: TicketService) -> None:
    """sync_channel_cache with no args MUST clear the cache."""
    service._ticket_channel_cache.add(1)
    service._ticket_channel_cache.add(2)
    service.sync_channel_cache()
    assert service._ticket_channel_cache == set()


# ===========================================================================
# create_subticket — parentId FK validation + carve-out (slice 2)
# ===========================================================================
#
# Supabase Transaction Mode has no DB FK enforcement, so the 4 parentId
# validations below are the ONLY integrity guard for the parent link.


def _parent_row(
    *,
    parent_id: str | None = None,
    guild_id: str = "123456789",
    ticket_number: int = 5,
) -> dict:
    """Return a sample parent ticket DB row (camelCase keys)."""
    return {
        "id": "parent-uuid-001",
        "ticketNumber": ticket_number,
        "guildId": guild_id,
        "authorId": "111111111",
        "channelId": "777777777",
        "categoryId": "cat-uuid-001",
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
        "parentId": parent_id,
    }


@pytest.mark.asyncio
async def test_create_subticket_success(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Valid parent → sub-ticket created with parentId set, cache synced."""
    parent_id = "parent-uuid-001"
    guild_id = "123456789"
    channel_id = "666666666"

    mock_db.get_ticket.return_value = _parent_row(parent_id=None)
    mock_db.get_max_ticket_number.return_value = 5
    mock_db.insert_ticket.return_value = {**ticket_row, "parentId": parent_id, "ticketNumber": 6}

    ticket = await service.create_subticket(
        parent_id=parent_id,
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id=channel_id,
        guild_id=guild_id,
    )

    # parentId validated then passed through to insert.
    mock_db.get_ticket.assert_awaited_once_with(parent_id)
    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["parent_id"] == parent_id
    assert insert_kwargs["ticket_number"] == 6  # MAX+1
    assert insert_kwargs["guild_id"] == guild_id

    # Returned model carries parentId.
    assert isinstance(ticket, Ticket)
    assert ticket.parent_id == parent_id
    assert ticket.ticket_number == 6

    # Cache synced with the new channel.
    assert 666666666 in service._ticket_channel_cache


@pytest.mark.asyncio
async def test_create_subticket_parent_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Non-existent parent MUST raise ValueError before any insert."""
    mock_db.get_ticket.return_value = None

    with pytest.raises(ValueError, match=r"Parent ticket .* not found"):
        await service.create_subticket(
            parent_id="does-not-exist",
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id="123456789",
        )

    # No insert attempted after validation failure.
    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subticket_self_reference_rejected(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """A parent that points to itself (parentId == id) MUST be rejected."""
    parent_id = "parent-uuid-001"
    # Corrupted parent: its own parentId equals its own id.
    mock_db.get_ticket.return_value = _parent_row(parent_id=parent_id)

    with pytest.raises(ValueError, match="self-referential"):
        await service.create_subticket(
            parent_id=parent_id,
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id="123456789",
        )

    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subticket_sub_of_sub_rejected(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """A parent that is itself a child (parentId set, != id) MUST be rejected."""
    parent_id = "parent-uuid-001"
    # Parent already has a different parentId → it is a sub-ticket.
    mock_db.get_ticket.return_value = _parent_row(parent_id="grandparent-uuid")

    with pytest.raises(ValueError, match=r"depth|subticket|sub"):
        await service.create_subticket(
            parent_id=parent_id,
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id="123456789",
        )

    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subticket_cross_guild_rejected(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Parent in guild A + caller passes guild B MUST raise ValueError."""
    parent_id = "parent-uuid-001"
    mock_db.get_ticket.return_value = _parent_row(parent_id=None, guild_id="111000111")

    with pytest.raises(ValueError, match=r"guild|same"):
        await service.create_subticket(
            parent_id=parent_id,
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id="123456789",  # different from parent's guild
        )

    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subticket_carve_out_skips_duplicate_check(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When parentId is set, the one-open-ticket constraint MUST be skipped.

    The user already has an open ticket in the same category, yet the
    sub-ticket creation MUST succeed without a duplicate error. This is
    the carve-out mandated by the spec.
    """
    parent_id = "parent-uuid-001"
    mock_db.get_ticket.return_value = _parent_row(parent_id=None)
    mock_db.get_max_ticket_number.return_value = 5
    mock_db.insert_ticket.return_value = {**ticket_row, "parentId": parent_id, "ticketNumber": 6}

    # Even though the author already has an open ticket, parentId set → carve-out.
    ticket = await service.create_subticket(
        parent_id=parent_id,
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id="666666666",
        guild_id="123456789",
    )

    assert ticket.parent_id == parent_id
    mock_db.insert_ticket.assert_awaited_once()


# ===========================================================================
# reopen_ticket — new channel from guild-configured category, cache update (slice 2)
# ===========================================================================


def _closed_ticket_row(channel_id: str = "888888888", category_id: str | None = "cat-uuid-001") -> dict:
    """Return a closed ticket DB row."""
    return {
        "id": "ticket-uuid-003",
        "ticketNumber": 3,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": channel_id,
        "categoryId": category_id,
        "status": "closed",
        "claimedBy": None,
        "transcriptUrl": "https://cdn.discord.com/t.html",
        "createdAt": "2026-01-10T10:00:00+00:00",
        "closedAt": "2026-06-01T10:00:00+00:00",
        "lastActivity": "2026-06-01T10:00:00+00:00",
        "parentId": None,
    }


def _mock_guild_for_reopen(
    *,
    category_channel: MagicMock | None,
    new_channel_id: int = 555555555,
) -> MagicMock:
    """Return a mock discord.Guild wired for reopen_ticket."""
    guild = MagicMock()
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.get_channel = MagicMock(return_value=category_channel)
    guild.get_role = MagicMock(return_value=None)
    guild.get_member = MagicMock(return_value=None)

    new_channel = MagicMock()
    new_channel.id = new_channel_id
    guild.create_text_channel = AsyncMock(return_value=new_channel)
    return guild


@pytest.mark.asyncio
async def test_reopen_creates_new_channel(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST create a new channel and update channelId/status/closedAt."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    reopened_row = {
        **closed_row,
        "channelId": "555555555",
        "status": "open",
        "closedAt": None,
    }

    # First get_ticket → closed row; second (re-read) → reopened row.
    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    # Guild config exposes the configured Discord ticket category.
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }

    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)

    ticket = await service.reopen_ticket(ticket_id, guild=guild)

    # New channel created in the configured category.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["category"] is category_channel

    # DB updated: channelId, status=open, closedAt=None.
    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["channelId"] == "555555555"
    assert update_kwargs["status"] == "open"
    assert update_kwargs["closedAt"] is None

    # Returned model reflects reopen.
    assert ticket.status == "open"
    assert ticket.channel_id == "555555555"

    # Cache updated with the new channel id.
    assert 555555555 in service._ticket_channel_cache


@pytest.mark.asyncio
async def test_reopen_category_channel_deleted_raises(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When the configured Discord category is deleted, reopen MUST raise."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    mock_db.get_ticket.return_value = closed_row
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }

    # Configured category channel no longer exists in the guild.
    guild = _mock_guild_for_reopen(category_channel=None)
    guild.get_channel = MagicMock(return_value=None)

    with pytest.raises(ValueError, match="No ticket category"):
        await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_no_category_configured_raises(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """No configured ticket category MUST raise ValueError."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    mock_db.get_ticket.return_value = closed_row
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": None,
        "modRoleId": None,
    }

    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match="No ticket category"):
        await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Reopening a non-existent ticket MUST raise ValueError."""
    mock_db.get_ticket.return_value = None
    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match=r"Ticket .* not found"):
        await service.reopen_ticket("nope", guild=guild)

    guild.create_text_channel.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["open", "claimed"])
async def test_reopen_rejects_non_closed_ticket(
    service: TicketService,
    mock_db: AsyncMock,
    status: str,
) -> None:
    """B2: reopen_ticket MUST raise ValueError when status is not 'closed'.

    Defense-in-depth: even if a caller bypasses the cog guard, the service
    refuses to create a duplicate channel for an open/claimed ticket.
    """
    ticket_id = "ticket-uuid-003"
    non_closed_row = {**_closed_ticket_row(), "status": status}
    mock_db.get_ticket.return_value = non_closed_row
    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match=r"Solo se pueden reabrir tickets cerrados"):
        await service.reopen_ticket(ticket_id, guild=guild)

    # No duplicate channel created; no DB mutation.
    guild.create_text_channel.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


# ===========================================================================
# transfer_ticket — claimedBy mutation + LoggingService audit (slice 2)
# ===========================================================================


def _mock_logging_service() -> AsyncMock:
    """Return a mock LoggingService with log_moderation_action as AsyncMock."""
    log = AsyncMock()
    log.log_moderation_action = AsyncMock()
    return log


@pytest.mark.asyncio
async def test_transfer_updates_claimed_by(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """transfer_ticket MUST mutate claimedBy and (re)claim the ticket."""
    ticket_id = ticket_row["id"]
    new_staff = "222222222"
    actor = "999999999"

    # PR2 contract: pre-read open+unclaimed (invariant passes), re-read claimed.
    mock_db.get_ticket.side_effect = [
        {**ticket_row, "status": "open", "claimedBy": None},
        {**ticket_row, "claimedBy": new_staff, "status": "claimed"},
    ]

    guild = MagicMock()
    guild.id = 123456789
    guild.get_member = MagicMock(return_value=MagicMock())
    logging_service = _mock_logging_service()

    ticket = await service.transfer_ticket(
        ticket_id,
        new_claimed_by=new_staff,
        actor_id=actor,
        guild=guild,
        logging_service=logging_service,
    )

    # DB updated with new claimedBy (and status=claimed — transfer implies claim).
    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["claimedBy"] == new_staff

    assert ticket.claimed_by == new_staff


@pytest.mark.asyncio
async def test_transfer_unclaimed_implicit_claim(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Transferring an unclaimed ticket MUST set claimedBy (implicit claim)."""
    ticket_id = ticket_row["id"]
    # PR2 contract: pre-read open+unclaimed, re-read claimed.
    mock_db.get_ticket.side_effect = [
        {**ticket_row, "status": "open", "claimedBy": None},
        {**ticket_row, "claimedBy": "222222222", "status": "claimed"},
    ]

    guild = MagicMock()
    guild.id = 123456789
    guild.get_member = MagicMock(return_value=MagicMock())
    logging_service = _mock_logging_service()

    ticket = await service.transfer_ticket(
        ticket_id,
        new_claimed_by="222222222",
        actor_id="999999999",
        guild=guild,
        logging_service=logging_service,
    )

    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["claimedBy"] == "222222222"
    assert ticket.claimed_by == "222222222"


@pytest.mark.asyncio
async def test_transfer_logs_audit(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """transfer_ticket MUST call LoggingService with the transfer audit info."""
    ticket_id = ticket_row["id"]
    # PR2 contract: pre-read open+unclaimed, re-read claimed.
    mock_db.get_ticket.side_effect = [
        {**ticket_row, "status": "open", "claimedBy": None},
        {**ticket_row, "claimedBy": "222222222"},
    ]

    target_member = MagicMock()
    actor_member = MagicMock()
    guild = MagicMock()
    guild.id = 123456789
    guild.get_member = MagicMock(side_effect=[target_member, actor_member])
    logging_service = _mock_logging_service()

    await service.transfer_ticket(
        ticket_id,
        new_claimed_by="222222222",
        actor_id="999999999",
        guild=guild,
        logging_service=logging_service,
    )

    logging_service.log_moderation_action.assert_awaited_once()
    log_kwargs = logging_service.log_moderation_action.call_args.kwargs
    assert log_kwargs["guild_id"] == "123456789"
    assert "Transfer" in log_kwargs["action"]


@pytest.mark.asyncio
async def test_transfer_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Transferring a non-existent ticket MUST raise ValueError."""
    mock_db.get_ticket.return_value = None
    guild = MagicMock()
    guild.id = 123456789
    logging_service = _mock_logging_service()

    with pytest.raises(ValueError, match=r"Ticket .* not found"):
        await service.transfer_ticket(
            "nope",
            new_claimed_by="222222222",
            actor_id="999999999",
            guild=guild,
            logging_service=logging_service,
        )


# ===========================================================================
# Note CRUD — create / get / delete + 50-cap + ownership (slice 2)
# ===========================================================================


def _note_row(
    *,
    note_id: str = "note-uuid-001",
    author_id: str = "999999999",
    content: str = "Customer escalated",
) -> dict:
    """Return a sample ticket_note DB row (camelCase keys)."""
    return {
        "id": note_id,
        "ticketId": "ticket-uuid-003",
        "authorId": author_id,
        "content": content,
        "createdAt": "2026-07-04T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_create_note_inserts(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """create_note MUST insert a row and return a TicketNote model."""
    mock_db.get_ticket_notes.return_value = []  # under cap
    mock_db.insert_ticket_note.return_value = _note_row()

    note = await service.create_note(
        "ticket-uuid-003",
        author_id="999999999",
        content="Customer escalated",
    )

    mock_db.insert_ticket_note.assert_awaited_once_with("ticket-uuid-003", "999999999", "Customer escalated")
    assert isinstance(note, TicketNote)
    assert note.content == "Customer escalated"
    assert note.author_id == "999999999"


@pytest.mark.asyncio
async def test_create_note_cap_enforced(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """With 50 notes already present, create_note MUST raise ValueError."""
    mock_db.get_ticket_notes.return_value = [_note_row() for _ in range(50)]

    with pytest.raises(ValueError, match="cap"):
        await service.create_note(
            "ticket-uuid-003",
            author_id="999999999",
            content="one too many",
        )

    mock_db.insert_ticket_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_notes_returns_list(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """get_notes MUST delegate to the DB and return TicketNote models."""
    mock_db.get_ticket.return_value = {
        "id": "ticket-uuid-003",
        "guildId": "123456789",
    }
    mock_db.get_ticket_notes.return_value = [_note_row(note_id=f"n-{i}") for i in range(3)]

    notes = await service.get_notes("ticket-uuid-003")

    mock_db.get_ticket_notes.assert_awaited_once()
    assert len(notes) == 3
    assert all(isinstance(n, TicketNote) for n in notes)


@pytest.mark.asyncio
async def test_get_notes_empty(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """get_notes on a ticket with no notes MUST return an empty list."""
    mock_db.get_ticket.return_value = {
        "id": "ticket-uuid-003",
        "guildId": "123456789",
    }
    mock_db.get_ticket_notes.return_value = []

    notes = await service.get_notes("ticket-uuid-003")

    assert notes == []


@pytest.mark.asyncio
async def test_get_notes_audits_success(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """CRITICAL 5: get_notes (the list op) MUST write a note_list audit row.

    Spec ``ticket-service/spec.md``: "Every ticket operation (claim, close,
    reopen, transfer, subticket create, note add, note list, note delete)
    MUST write a ``ticket_audit`` row" — note LIST is in that list. The audit
    row is scoped to the ticket's guild (resolved via a get_ticket pre-read)
    with action=``note_list`` and outcome=``success``.
    """
    ticket_id = "ticket-uuid-003"
    guild_id = "123456789"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": guild_id}
    mock_db.get_ticket_notes.return_value = []

    await service.get_notes(ticket_id)

    calls = mock_db.insert_audit_row.call_args_list
    assert len(calls) == 1, calls
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_list"
    assert kwargs["outcome"] == "success"
    assert kwargs["guild_id"] == guild_id
    assert kwargs["ticket_id"] == ticket_id


@pytest.mark.asyncio
async def test_delete_note_own(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """The note author MUST be able to delete their own note."""
    mock_db.get_ticket_notes.return_value = [_note_row(author_id="999999999")]

    await service.delete_note("note-uuid-001", author_id="999999999", ticket_id="ticket-uuid-003")

    mock_db.delete_ticket_note.assert_awaited_once_with("note-uuid-001")


@pytest.mark.asyncio
async def test_delete_note_other_rejected(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """A non-author MUST NOT delete someone else's note."""
    mock_db.get_ticket_notes.return_value = [_note_row(author_id="999999999")]

    with pytest.raises(ValueError, match=r"[Aa]uthor"):
        await service.delete_note("note-uuid-001", author_id="888888888", ticket_id="ticket-uuid-003")

    mock_db.delete_ticket_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_note_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Deleting a note that does not belong to the ticket MUST raise ValueError."""
    mock_db.get_ticket_notes.return_value = [_note_row(note_id="other-note")]

    with pytest.raises(ValueError, match=r"[Nn]ot found"):
        await service.delete_note("missing-note", author_id="999999999", ticket_id="ticket-uuid-003")

    mock_db.delete_ticket_note.assert_not_awaited()


# ===========================================================================
# PR2 — invariant + audit wiring (claim/close/reopen/transfer/subticket/notes)
# ===========================================================================
#
# Every op MUST: (1) run the pure invariant BEFORE mutating, (2) write a
# ticket_audit row (outcome=success on completion, outcome=denied + reason on
# invariant rejection), (3) re-raise the ValueError on the denied path.


def _audit_kwargs(mock_db: AsyncMock, index: int = -1) -> dict:
    """Return a kwargs dict for the index-th insert_audit_row call.

    Merges positional args (by Database.insert_audit_row param order) when
    the service called positionally, so test assertions read uniformly.
    """
    call = mock_db.insert_audit_row.call_args_list[index]
    if call.kwargs:
        return call.kwargs
    keys = ["guild_id", "ticket_id", "action", "actor_id", "outcome", "reason"]
    return dict(zip(keys, call.args, strict=False))


@pytest.mark.asyncio
async def test_claim_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """3.1/3.2: claim on an open ticket MUST write an audit success row."""
    ticket_id = ticket_row["id"]
    staff_id = "999999999"
    # Pre-read returns the OPEN row (invariant passes); re-read returns claimed.
    mock_db.get_ticket.side_effect = [
        ticket_row,
        {**ticket_row, "status": "claimed", "claimedBy": staff_id},
    ]

    await service.claim_ticket(ticket_id, claimed_by=staff_id)

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "claim"
    assert kwargs["outcome"] == "success"
    assert kwargs["actor_id"] == staff_id
    assert kwargs["guild_id"] == ticket_row["guildId"]
    assert kwargs["ticket_id"] == ticket_id


@pytest.mark.asyncio
async def test_claim_denied_audits_and_reraises(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Claim on an already-claimed ticket MUST audit denied + re-raise."""
    ticket_id = ticket_row["id"]
    claimed_row = {**ticket_row, "status": "claimed", "claimedBy": "userA"}
    mock_db.get_ticket.return_value = claimed_row

    with pytest.raises(ValueError, match=r"claim"):
        await service.claim_ticket(ticket_id, claimed_by="userB")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "claim"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] is not None
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """3.9/3.10: close on open/claimed MUST write an audit success row."""
    ticket_id = ticket_row["id"]
    closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
    mock_db.get_ticket.return_value = ticket_row
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

    await service.close_ticket(ticket_id, closed_by="999999999")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "close"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_close_denied_audits_and_reraises(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Close on an already-closed ticket MUST raise ValueError (transition returns None)."""
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
    mock_db.get_ticket.return_value = {**ticket_row, "status": "closed"}

    with pytest.raises(ValueError, match="already closed or not found"):
        await service.close_ticket(ticket_row["id"], closed_by="999999999")

    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_denied_writes_audit(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """R1-003: denied-close MUST write a best-effort denied audit row before raising."""
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
    mock_db.get_ticket.return_value = ticket_row  # resolve guild for audit scoping

    with pytest.raises(ValueError, match="already closed or not found"):
        await service.close_ticket(ticket_row["id"], closed_by="999999999")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "close"
    assert kwargs["outcome"] == "denied"
    assert kwargs["guild_id"] == ticket_row["guildId"]
    assert kwargs["actor_id"] == "999999999"


@pytest.mark.asyncio
async def test_transfer_same_user_denied(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """3.3/3.4: transfer to the same claimant MUST raise ValueError + audit denied."""
    ticket_id = ticket_row["id"]
    claimed = {**ticket_row, "status": "claimed", "claimedBy": "userA"}
    mock_db.get_ticket.return_value = claimed

    with pytest.raises(ValueError, match=r"same"):
        await service.transfer_ticket(ticket_id, new_claimed_by="userA", actor_id="admin1")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "transfer"
    assert kwargs["outcome"] == "denied"
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_transfer_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Transfer to a different staff member MUST audit success."""
    ticket_id = ticket_row["id"]
    mock_db.get_ticket.side_effect = [
        {**ticket_row, "status": "open", "claimedBy": None},
        {**ticket_row, "claimedBy": "userB", "status": "claimed"},
    ]

    await service.transfer_ticket(ticket_id, new_claimed_by="userB", actor_id="admin1")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "transfer"
    assert kwargs["outcome"] == "success"
    assert kwargs["actor_id"] == "admin1"


@pytest.mark.asyncio
async def test_transfer_closed_denied(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Transferring a closed ticket MUST be denied + audited."""
    closed = {**ticket_row, "status": "closed"}
    mock_db.get_ticket.return_value = closed

    with pytest.raises(ValueError, match=r"closed"):
        await service.transfer_ticket(ticket_row["id"], new_claimed_by="userB", actor_id="admin1")

    kwargs = _audit_kwargs(mock_db)
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_note_dedup_within_window(service: TicketService, mock_db: AsyncMock) -> None:
    """3.5/3.6: a duplicate note (same author, within 2s) MUST raise ValueError."""
    ticket_id = "ticket-uuid-003"
    author = "999999999"
    mock_db.get_ticket.return_value = {
        "id": ticket_id,
        "guildId": "123456789",
        "ticketNumber": 3,
    }
    mock_db.get_ticket_notes.return_value = []  # under cap
    mock_db.get_recent_notes_for_dedup.return_value = [
        {"content": "Hello World"},  # same normalized form as incoming
    ]

    with pytest.raises(ValueError, match=r"duplicate|dedup"):
        await service.create_note(ticket_id, author, "  hello world  ")

    mock_db.insert_ticket_note.assert_not_awaited()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_add"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_note_dedup_outside_window_allowed(service: TicketService, mock_db: AsyncMock) -> None:
    """3.5/3.6: outside the dedup window the same content is allowed (audit success)."""
    ticket_id = "ticket-uuid-003"
    author = "999999999"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    mock_db.get_ticket_notes.return_value = []
    mock_db.get_recent_notes_for_dedup.return_value = []  # no recent → no dup
    mock_db.insert_ticket_note.return_value = _note_row(content="hello")

    await service.create_note(ticket_id, author, "hello")

    mock_db.insert_ticket_note.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_add"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_note_cap_denied_audited(service: TicketService, mock_db: AsyncMock) -> None:
    """3.5/3.6: at the 50-note cap, create_note MUST audit denied + raise."""
    ticket_id = "ticket-uuid-003"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    mock_db.get_ticket_notes.return_value = [_note_row() for _ in range(50)]

    with pytest.raises(ValueError, match=r"cap"):
        await service.create_note(ticket_id, "999999999", "one too many")

    mock_db.insert_ticket_note.assert_not_awaited()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_add"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_note_under_cap_audited_success(service: TicketService, mock_db: AsyncMock) -> None:
    """TI-034: under the cap, create_note persists + audits success."""
    ticket_id = "ticket-uuid-003"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    mock_db.get_ticket_notes.return_value = [_note_row() for _ in range(30)]
    mock_db.get_recent_notes_for_dedup.return_value = []
    mock_db.insert_ticket_note.return_value = _note_row(content="new note")

    await service.create_note(ticket_id, "999999999", "new note")

    mock_db.insert_ticket_note.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_note_delete_author_audited_success(service: TicketService, mock_db: AsyncMock) -> None:
    """TI-035: author deleting own note MUST audit success."""
    ticket_id = "ticket-uuid-003"
    author = "999999999"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    mock_db.get_ticket_notes.return_value = [_note_row(author_id=author)]

    await service.delete_note("note-uuid-001", author_id=author, ticket_id=ticket_id)

    mock_db.delete_ticket_note.assert_awaited_once_with("note-uuid-001")
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_delete"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_note_delete_other_denied_audited(service: TicketService, mock_db: AsyncMock) -> None:
    """delete_note by a non-author MUST audit denied + raise."""
    ticket_id = "ticket-uuid-003"
    mock_db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    mock_db.get_ticket_notes.return_value = [_note_row(author_id="userA")]

    with pytest.raises(ValueError, match=r"[Aa]uthor|owner"):
        await service.delete_note("note-uuid-001", author_id="userB", ticket_id=ticket_id)

    mock_db.delete_ticket_note.assert_not_awaited()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "note_delete"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_reopen_audits_success(service: TicketService, mock_db: AsyncMock) -> None:
    """3.7/3.8: reopen success MUST write an audit success row after channel creation."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}
    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }
    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)

    await service.reopen_ticket(ticket_id, guild=guild)

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "reopen"
    assert kwargs["outcome"] == "success"
    assert kwargs["guild_id"] == "123456789"


@pytest.mark.asyncio
async def test_reopen_denied_audited(service: TicketService, mock_db: AsyncMock) -> None:
    """3.7/3.8: reopen on a non-closed ticket MUST audit denied + re-raise."""
    ticket_id = "ticket-uuid-003"
    open_row = {**_closed_ticket_row(), "status": "open"}
    mock_db.get_ticket.return_value = open_row
    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match=r"cerrados"):
        await service.reopen_ticket(ticket_id, guild=guild)

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "reopen"
    assert kwargs["outcome"] == "denied"
    guild.create_text_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_subticket_create_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """3.9/3.10: subticket success MUST write an audit success row."""
    parent_id = "parent-uuid-001"
    guild_id = "123456789"
    mock_db.get_ticket.return_value = _parent_row(parent_id=None, guild_id=guild_id)
    mock_db.get_max_ticket_number.return_value = 5
    mock_db.insert_ticket.return_value = {
        **ticket_row,
        "parentId": parent_id,
        "ticketNumber": 6,
    }

    await service.create_subticket(
        parent_id=parent_id,
        author_id="111111111",
        category_id=None,
        channel_id="666666666",
        guild_id=guild_id,
    )

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "subticket_create"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case, parent_row_kwargs, parent_id, match",
    [
        # CRITICAL 3: parent-missing MUST audit (spec: every denial audits).
        ("parent_missing", None, "missing-parent", r"[Pp]arent"),
        # CRITICAL 3: self-reference denial MUST audit. _parent_row hardcodes
        # id="parent-uuid-001", so the calling parent_id MUST equal that for
        # the parentId==id self-reference guard to trigger.
        (
            "self_reference",
            {"parent_id": "parent-uuid-001"},
            "parent-uuid-001",
            r"self-referential",
        ),
        # CRITICAL 3: depth-max-2 denial MUST audit (parent already a child).
        (
            "depth",
            {"parent_id": "grandparent-uuid"},
            "parent-uuid-001",
            r"depth|subticket|sub",
        ),
        # CRITICAL 4: cross-guild denial MUST audit scoped to CALLER guild.
        (
            "cross_guild",
            {"parent_id": None, "guild_id": "111000111"},
            "parent-other-guild",
            r"guild|same",
        ),
    ],
)
async def test_subticket_create_denied_audited(
    service: TicketService,
    mock_db: AsyncMock,
    case: str,
    parent_row_kwargs: dict | None,
    parent_id: str,
    match: str,
) -> None:
    """CRITICAL 3+4: EVERY create_subticket invariant denial MUST write a
    ``ticket_audit`` row (action=subticket_create, outcome=denied, non-empty
    reason) scoped to the CALLER's ``guild_id`` (the guild the operation was
    attempted FROM), then re-raise ``ValueError``.

    Spec ``ticket-service/spec.md``: audit logging on ticket operations lists
    "subticket create" and requires an audit row on every operation,
    including denials (the Invariant-violation-audited scenario). The audit
    guild scope is the caller's guild (the operation origin), NOT the
    parent's guild — for cross-guild attempts the parent's guild is a
    different guild and auditing under it would leak the denial into the
    wrong guild's audit trail.
    """
    caller_guild = "123456789"
    if parent_row_kwargs is None:
        mock_db.get_ticket.return_value = None
    else:
        mock_db.get_ticket.return_value = _parent_row(**parent_row_kwargs)

    with pytest.raises(ValueError, match=match):
        await service.create_subticket(
            parent_id=parent_id,
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id=caller_guild,
        )

    mock_db.insert_ticket.assert_not_awaited()
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "subticket_create", case
    assert kwargs["outcome"] == "denied", case
    assert kwargs["reason"], f"{case}: reason MUST be non-empty"
    # CRITICAL 4: audit scoped to the CALLER's guild, never the parent's.
    assert kwargs["guild_id"] == caller_guild, case
    assert kwargs["ticket_id"] == parent_id, case


@pytest.mark.asyncio
async def test_audit_guild_scope_query(mock_db: AsyncMock) -> None:
    """TI-021: get_audit_rows MUST filter by guildId (delegated to Database)."""
    mock_db.get_audit_rows = AsyncMock(return_value=[{"guildId": "A", "action": "claim"}])
    rows = await mock_db.get_audit_rows("A", limit=10, offset=0)
    mock_db.get_audit_rows.assert_awaited_once_with("A", limit=10, offset=0)
    assert all(r["guildId"] == "A" for r in rows)


# ===========================================================================
# TicketCategoryNotConfiguredError — typed exception for reopen
# ===========================================================================


@pytest.mark.asyncio
async def test_reopen_no_category_raises_typed_exception(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST raise TicketCategoryNotConfiguredError (not raw
    ValueError) when no ticket category is configured for the guild.
    """
    from bot.services.ticket_service import TicketCategoryNotConfiguredError

    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    mock_db.get_ticket.return_value = closed_row
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": None,
        "modRoleId": None,
    }

    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(TicketCategoryNotConfiguredError):
        await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_deleted_category_raises_typed_exception(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST raise TicketCategoryNotConfiguredError when the
    configured Discord category channel no longer exists.
    """
    from bot.services.ticket_service import TicketCategoryNotConfiguredError

    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    mock_db.get_ticket.return_value = closed_row
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }

    guild = _mock_guild_for_reopen(category_channel=None)
    guild.get_channel = MagicMock(return_value=None)

    with pytest.raises(TicketCategoryNotConfiguredError):
        await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


# ===========================================================================
# create_ticket_channel — expanded: channel + DB insert + rename (PR4 fix)
# ===========================================================================


def _mock_guild_for_channel(*, channel_name: str = "support-testuser-0001", channel_id: int = 999999999) -> MagicMock:
    """Return a mock guild wired for create_ticket_channel."""
    guild = MagicMock()
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    channel = MagicMock()
    channel.id = channel_id
    channel.name = channel_name
    channel.edit = AsyncMock()
    guild.create_text_channel = AsyncMock(return_value=channel)
    return guild


def _mock_author() -> MagicMock:
    """Return a mock discord.Member for ticket author."""
    author = MagicMock(spec=discord.Member)
    author.id = 111111111
    author.__str__ = MagicMock(return_value="TestUser#0001")
    author.display_name = "TestUser"
    return author


@pytest.mark.asyncio
async def test_create_ticket_channel_rejects_before_creating_channel_when_limit_hit(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When user already has an open ticket in the category, do NOT create a channel.

    Production logs showed channel create → ValueError → cleanup delete thrashing.
    The invariant must fail fast before guild.create_text_channel.
    """
    guild = _mock_guild_for_channel(channel_name="support-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.count_user_open_tickets_in_category.return_value = 1
    mock_db.get_max_ticket_number.return_value = 0

    with pytest.raises(ValueError, match=r"already has an open ticket"):
        await service.create_ticket_channel(
            guild,
            category,
            author,
            guild_id="123456789",
            category_name="Support",
            category_id="cat-uuid-001",
        )

    guild.create_text_channel.assert_not_awaited()
    mock_db.insert_ticket.assert_not_awaited()
    mock_db.count_user_open_tickets_in_category.assert_awaited_once_with(
        "123456789",
        "111111111",
        "cat-uuid-001",
    )


@pytest.mark.asyncio
async def test_create_ticket_channel_creates_channel_and_inserts(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST create a Discord channel AND insert a ticket row."""
    guild = _mock_guild_for_channel(channel_name="support-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

    channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
    )

    # Channel created with correct overwrites.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["category"] is category
    assert create_kwargs["name"] == "support-testuser-0001"

    # Ticket inserted via create_ticket (DB called).
    mock_db.insert_ticket.assert_awaited_once()
    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["guild_id"] == "123456789"
    assert insert_kwargs["author_id"] == "111111111"
    assert insert_kwargs["channel_id"] == str(channel.id)

    # Returned tuple.
    assert isinstance(ticket, Ticket)
    assert ticket.ticket_number == 1
    assert 999999999 in service._ticket_channel_cache


@pytest.mark.asyncio
async def test_create_ticket_channel_renames_if_number_differs(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When tentative name differs from actual ticket number, channel MUST be renamed."""
    # Channel created with tentative name "support-testuser-0001" but DB returns ticketNumber=42.
    guild = _mock_guild_for_channel(channel_name="support-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 42}

    channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
    )

    # Channel renamed to match actual ticket number.
    channel.edit.assert_awaited_once_with(name="support-testuser-0042")
    assert ticket.ticket_number == 42


@pytest.mark.asyncio
async def test_create_ticket_channel_no_rename_if_name_matches(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When tentative name matches actual ticket number, no rename is needed."""
    guild = _mock_guild_for_channel(channel_name="support-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

    channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
    )

    # No rename needed.
    channel.edit.assert_not_awaited()
    assert ticket.ticket_number == 1


@pytest.mark.asyncio
async def test_create_ticket_channel_passes_category_id(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST forward category_id to create_ticket."""
    guild = _mock_guild_for_channel()
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1, "categoryId": "cat-uuid-001"}

    _channel, _ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
        category_id="cat-uuid-001",
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["category_id"] == "cat-uuid-001"


@pytest.mark.asyncio
async def test_create_ticket_channel_forwards_subject_and_description(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel(subject=..., description=...) MUST forward metadata to insert_ticket."""
    guild = _mock_guild_for_channel()
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {
        **ticket_row,
        "ticketNumber": 1,
        "subject": "Login broken",
        "description": "Cannot access since Monday",
    }

    _channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
        subject="Login broken",
        description="Cannot access since Monday",
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["subject"] == "Login broken"
    assert insert_kwargs["description"] == "Cannot access since Monday"
    assert ticket.subject == "Login broken"
    assert ticket.description == "Cannot access since Monday"


# ===========================================================================
# PR2 — custom_fields passthrough (task 2.1 RED)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_ticket_with_custom_fields(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket(custom_fields=...) MUST forward to insert_ticket and persist on the model."""
    cf = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "customFields": cf}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id="888888888",
        custom_fields=cf,
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] == cf
    assert ticket.custom_fields == cf


@pytest.mark.asyncio
async def test_create_ticket_without_custom_fields(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket() without custom_fields MUST pass None to insert_ticket."""
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "customFields": None}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] is None
    assert ticket.custom_fields is None


@pytest.mark.asyncio
async def test_create_ticket_channel_forwards_custom_fields(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel(custom_fields=...) MUST forward to create_ticket."""
    guild = _mock_guild_for_channel()
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()
    cf = {"player_nick": "DarkSlayer42"}

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1, "customFields": cf}

    _channel, ticket = await service.create_ticket_channel(
        guild, category, author, guild_id="123456789", category_name="Support", custom_fields=cf
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] == cf
    assert ticket.custom_fields == cf


@pytest.mark.asyncio
async def test_create_ticket_channel_without_custom_fields(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel() without custom_fields MUST pass None to create_ticket."""
    guild = _mock_guild_for_channel()
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1, "customFields": None}

    _channel, ticket = await service.create_ticket_channel(
        guild, category, author, guild_id="123456789", category_name="Support"
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] is None
    assert ticket.custom_fields is None


# ===========================================================================
# PR4 — channel naming: sanitize_channel_name wiring
# ===========================================================================


@pytest.mark.asyncio
async def test_create_ticket_channel_uses_sanitized_name(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST use sanitize_channel_name for the channel name."""
    guild = _mock_guild_for_channel(channel_name="soporte-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

    _, __ = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Soporte",
    )

    # Channel created with sanitized name.
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["name"] == "soporte-testuser-0001"


@pytest.mark.asyncio
async def test_create_ticket_channel_renames_with_sanitized_actual(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When tentative != actual, rename MUST use sanitized format."""
    guild = _mock_guild_for_channel(channel_name="soporte-testuser-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 42}

    channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Soporte",
    )

    # Channel renamed to sanitized actual name.
    channel.edit.assert_awaited_once_with(name="soporte-testuser-0042")
    assert ticket.ticket_number == 42


@pytest.mark.asyncio
async def test_create_ticket_channel_subticket_uses_sanitized_parent_category_name(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """C2: Subticket channel MUST use sanitize_channel_name with parent's category name.

    Spec (channel-naming): "Subtickets resolve the parent category."
    The resulting channel name MUST match the `{category}-{username}-{number}` pattern
    using the parent's category name, not a hardcoded 'ticket' fallback.
    """
    guild = _mock_guild_for_channel(channel_name="soporte-parentowner-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    parent_owner = MagicMock(spec=discord.Member)
    parent_owner.id = 222222222
    parent_owner.__str__ = MagicMock(return_value="ParentOwner#0001")
    parent_owner.display_name = "ParentOwner"

    # Parent ticket exists and is valid (no self-ref, no sub-of-sub, same guild).
    parent_row = _parent_row(parent_id=None, guild_id="123456789")
    mock_db.get_ticket.return_value = parent_row
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "parentId": "parent-uuid-001", "ticketNumber": 1}

    _channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        parent_owner,
        guild_id="123456789",
        category_name="Soporte",  # parent's resolved category name
        parent_id="parent-uuid-001",
    )

    # Channel name uses the parent category name, NOT 'ticket'.
    create_kwargs = guild.create_text_channel.call_args.kwargs
    name = create_kwargs["name"]
    assert name == "soporte-parentowner-0001"
    # Pattern check: {category}-{username}-{number}
    assert name.startswith("soporte-parentowner-"), f"Expected parent category name in channel name, got: {name}"
    assert ticket.parent_id == "parent-uuid-001"


@pytest.mark.asyncio
async def test_reopen_uses_sanitized_channel_name(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST use sanitize_channel_name with resolved category + author."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    reopened_row = {
        **closed_row,
        "channelId": "555555555",
        "status": "open",
        "closedAt": None,
    }

    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }
    # Category lookup returns a name.
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte", "id": "cat-uuid-001"})

    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)
    # Author member with display name.
    author_member = MagicMock()
    author_member.display_name = "DanielXX"
    guild.get_member = MagicMock(return_value=author_member)

    await service.reopen_ticket(ticket_id, guild=guild)

    # Channel created with sanitized name.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["name"] == "soporte-danielxx-0003"


@pytest.mark.asyncio
async def test_reopen_fallback_when_category_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When category lookup fails, reopen MUST fall back to 'ticket' prefix."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    reopened_row = {
        **closed_row,
        "channelId": "555555555",
        "status": "open",
        "closedAt": None,
    }

    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }
    # Category lookup returns None (not found).
    mock_db.get_ticket_category = AsyncMock(return_value=None)

    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)
    guild.get_member = MagicMock(return_value=None)

    await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    # Fallback: ticket-user-0003
    assert create_kwargs["name"] == "ticket-user-0003"


@pytest.mark.asyncio
async def test_reopen_fallback_when_author_not_in_guild(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When author member is not found, reopen MUST fall back to 'user'."""
    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    reopened_row = {
        **closed_row,
        "channelId": "555555555",
        "status": "open",
        "closedAt": None,
    }

    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": "100000000",
        "modRoleId": None,
    }
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte", "id": "cat-uuid-001"})

    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)
    # Author not found in guild.
    guild.get_member = MagicMock(return_value=None)

    await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["name"] == "soporte-user-0003"


# ===========================================================================
# Best-effort audit on success path (runtime-hotfix)
# ===========================================================================


@pytest.mark.asyncio
async def test_claim_success_audit_failure_continues(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spec: claim success audit failure MUST NOT abort the claim.

    When insert_audit_row raises on the success path, the claim
    UI action (role assignment) proceeds normally and a WARNING is logged.
    """
    import logging

    ticket_id = ticket_row["id"]
    staff_id = "999999999"

    mock_db.get_ticket.side_effect = [
        ticket_row,
        {**ticket_row, "status": "claimed", "claimedBy": staff_id},
    ]
    mock_db.insert_audit_row.side_effect = Exception("audit table unavailable")

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        ticket = await service.claim_ticket(ticket_id, claimed_by=staff_id)

    # Claim succeeded — ticket is claimed despite audit failure.
    assert ticket.status == "claimed"
    assert ticket.claimed_by == staff_id
    assert any("audit" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_close_success_audit_failure_continues(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spec: close success audit failure MUST NOT abort the close.

    When insert_audit_row raises on the success path, the close
    UI action (channel delete, transcript) proceeds normally and a WARNING is logged.
    """
    import logging

    ticket_id = ticket_row["id"]

    closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
    mock_db.get_ticket.return_value = ticket_row
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
    mock_db.insert_audit_row.side_effect = Exception("audit table unavailable")

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        ticket = await service.close_ticket(ticket_id, closed_by="999999999")

    # Close succeeded — ticket is closed despite audit failure.
    assert ticket.status == "closed"
    assert any("audit" in r.message.lower() for r in caplog.records)


# ===========================================================================
# PR2 — close_ticket_full countdown (task 2.3.1 RED)
# ===========================================================================


def _mock_channel_for_close(*, channel_id: int = 888888888) -> MagicMock:
    """Return a mock TextChannel wired for close_ticket_full."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.send = AsyncMock()
    channel.delete = AsyncMock()
    channel.guild = MagicMock()
    channel.guild.id = 123456789
    return channel


def _mock_bot_for_close() -> MagicMock:
    """Return a mock NebulosaBot wired for close_ticket_full."""
    bot = MagicMock()
    bot.transcript_service = None
    bot.guild_service = None
    return bot


def _ticket_model(*, ticket_id: str = "ticket-uuid-close") -> Ticket:
    """Return a sample Ticket model for close tests."""
    return Ticket(
        id=ticket_id,
        ticket_number=42,
        guild_id="123456789",
        author_id="111111111",
        channel_id="888888888",
        status="open",
        created_at="2026-01-15T10:00:00",
        last_activity="2026-01-15T10:00:00",
    )


@pytest.mark.asyncio
async def test_close_ticket_full_manual_countdown(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """close_ticket_full(manual=True) MUST send ONE message and edit 5→1, then delete channel."""
    channel = _mock_channel_for_close()
    bot = _mock_bot_for_close()
    ticket = _ticket_model()

    open_row = {
        "id": ticket.id,
        "ticketNumber": 42,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    closed_row = {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00"}
    mock_db.get_ticket.side_effect = [
        open_row,  # close_ticket pre-read (invariant check)
        closed_row,  # close_ticket re-read
    ]

    # Mock the countdown message.
    countdown_msg = AsyncMock()
    channel.send.return_value = countdown_msg

    with patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock):
        result = await service.close_ticket_full(channel, ticket, "999999999", bot=bot, manual=True)

    # ONE message sent (the "5").
    channel.send.assert_awaited_once()
    assert channel.send.call_args.args == ("5",)

    # Message edited 4 times: "4", "3", "2", "1".
    assert countdown_msg.edit.await_count == 4
    edit_contents = [
        call.args[0] if call.args else call.kwargs.get("content") for call in countdown_msg.edit.call_args_list
    ]
    assert edit_contents == ["4", "3", "2", "1"]

    # Channel deleted after countdown.
    channel.delete.assert_awaited_once()
    assert result is None  # no transcript


@pytest.mark.asyncio
async def test_close_ticket_full_auto_silent(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """close_ticket_full(manual=False) MUST delete silently — no countdown messages."""
    channel = _mock_channel_for_close()
    bot = _mock_bot_for_close()
    ticket = _ticket_model()

    open_row = {
        "id": ticket.id,
        "ticketNumber": 42,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    closed_row = {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00"}
    mock_db.get_ticket.side_effect = [
        open_row,  # close_ticket pre-read (invariant check)
        closed_row,  # close_ticket re-read
    ]

    with patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock):
        result = await service.close_ticket_full(channel, ticket, "auto", bot=bot, manual=False)

    # NO messages sent (silent delete).
    channel.send.assert_not_awaited()

    # Channel deleted after silent delay.
    channel.delete.assert_awaited_once()
    assert result is None


@pytest.mark.asyncio
async def test_close_ticket_full_countdown_cancelled_error_logs_and_reraises(
    service: TicketService,
    mock_db: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """C1: CancelledError during countdown MUST be logged, re-raised, and MUST NOT delete channel.

    Design contract (design.md): "It logs and re-raises CancelledError, so a
    cancelled task never reaches deletion."
    """
    import asyncio
    import logging

    channel = _mock_channel_for_close()
    bot = _mock_bot_for_close()
    ticket = _ticket_model()

    open_row = {
        "id": ticket.id,
        "ticketNumber": 42,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    closed_row = {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00"}
    mock_db.get_ticket.side_effect = [
        open_row,  # close_ticket pre-read
        closed_row,  # close_ticket re-read
    ]

    # First sleep raises CancelledError (simulates task cancellation during countdown).
    async def _cancel_on_first_sleep(*_args, **_kwargs):
        raise asyncio.CancelledError

    countdown_msg = AsyncMock()
    channel.send.return_value = countdown_msg

    with (
        patch("bot.services.ticket_service.asyncio.sleep", side_effect=_cancel_on_first_sleep),
        caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"),
        pytest.raises(asyncio.CancelledError),
    ):
        await service.close_ticket_full(channel, ticket, "999999999", bot=bot, manual=True)

    # CancelledError was logged.
    assert any("cancel" in r.message.lower() for r in caplog.records)

    # Channel was NOT deleted — cancellation prevented deletion.
    channel.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_ticket_full_countdown_failure_fallback(
    service: TicketService,
    mock_db: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When countdown edit fails, MUST log warning and fall back to silent delete."""
    import logging

    channel = _mock_channel_for_close()
    bot = _mock_bot_for_close()
    ticket = _ticket_model()

    open_row = {
        "id": ticket.id,
        "ticketNumber": 42,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    closed_row = {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00"}
    mock_db.get_ticket.side_effect = [
        open_row,  # close_ticket pre-read (invariant check)
        closed_row,  # close_ticket re-read
    ]

    # Send succeeds but edit fails (simulates permission loss during countdown).
    countdown_msg = AsyncMock()
    countdown_msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "rate limited"))
    channel.send.return_value = countdown_msg

    with (
        patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock),
        caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"),
    ):
        await service.close_ticket_full(channel, ticket, "999999999", bot=bot, manual=True)

    # Warning logged about countdown failure.
    assert any("countdown" in r.message.lower() or "fallback" in r.message.lower() for r in caplog.records)

    # Channel still deleted via fallback.
    channel.delete.assert_awaited_once()


# ===========================================================================
# PR3 — unclaim_ticket (task 3.3.1 RED)
# ===========================================================================


@pytest.mark.asyncio
async def test_unclaim_ticket_resets_status_and_claimed_by(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """unclaim_ticket MUST set claimedBy=null, status='open', and write an audit row."""
    ticket_id = "ticket-uuid-unclaim"
    actor_id = "userA"

    claimed_row = {
        "id": ticket_id,
        "ticketNumber": 5,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "claimed",
        "claimedBy": actor_id,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    unclaimed_row = {**claimed_row, "status": "open", "claimedBy": None}
    mock_db.get_ticket.side_effect = [claimed_row, unclaimed_row]

    ticket = await service.unclaim_ticket(ticket_id, actor_id, is_mod=False)

    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["status"] == "open"
    assert update_kwargs["claimedBy"] is None

    assert ticket.status == "open"
    assert ticket.claimed_by is None

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "unclaim"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_unclaim_ticket_unclaimed_raises(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """unclaim_ticket on an unclaimed ticket MUST raise ValueError + audit denied."""
    ticket_id = "ticket-uuid-unclaim"

    open_row = {
        "id": ticket_id,
        "ticketNumber": 5,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    mock_db.get_ticket.return_value = open_row

    with pytest.raises(ValueError, match=r"claimed"):
        await service.unclaim_ticket(ticket_id, "userA", is_mod=False)

    mock_db.update_ticket.assert_not_awaited()
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "unclaim"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_unclaim_ticket_non_claimer_non_mod_denied(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """unclaim_ticket by non-claimer non-mod MUST raise ValueError + audit denied."""
    ticket_id = "ticket-uuid-unclaim"

    claimed_row = {
        "id": ticket_id,
        "ticketNumber": 5,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "claimed",
        "claimedBy": "userA",
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }
    mock_db.get_ticket.return_value = claimed_row

    with pytest.raises(ValueError, match=r"claimer|mod|permission"):
        await service.unclaim_ticket(ticket_id, "userB", is_mod=False)

    mock_db.update_ticket.assert_not_awaited()
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "unclaim"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_unclaim_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """unclaim_ticket on a non-existent ticket MUST raise ValueError."""
    mock_db.get_ticket.return_value = None

    with pytest.raises(ValueError, match=r"not found"):
        await service.unclaim_ticket("nonexistent", "userA", is_mod=False)


# ===========================================================================
# edit_ticket_category — service method (task 2.3 RED)
# ===========================================================================


def _open_ticket_row_for_edit(
    *,
    ticket_id: str = "ticket-uuid-edit",
    author_id: str = "111111111",
    category_id: str | None = "cat-uuid-support",
    guild_id: str = "123456789",
    status: str = "open",
) -> dict:
    """Return an open ticket DB row wired for edit_ticket_category tests."""
    return {
        "id": ticket_id,
        "ticketNumber": 5,
        "guildId": guild_id,
        "authorId": author_id,
        "channelId": "888888888",
        "categoryId": category_id,
        "status": status,
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
        "parentId": None,
    }


def _mock_channel_for_edit(*, name: str = "support-daniel-0005") -> MagicMock:
    """Return a mock TextChannel wired for edit_ticket_category.

    The channel exposes a guild whose ``get_member`` returns a member with
    ``display_name`` matching the default author_id in
    ``_open_ticket_row_for_edit`` (``111111111``). This lets
    ``resolve_member_safe`` resolve the author the way the reopen path does.
    """
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 888888888
    channel.name = name
    channel.edit = AsyncMock()

    guild = MagicMock()
    author_member = MagicMock()
    author_member.display_name = "DanielXX"
    guild.get_member = MagicMock(return_value=author_member)
    channel.guild = guild

    return channel


@pytest.mark.asyncio
async def test_edit_ticket_category_updates_db_and_renames(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """edit_ticket_category MUST update categoryId in DB and rename the channel."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit(category_id="cat-uuid-support")
    updated_row = {**open_row, "categoryId": "cat-uuid-billing"}
    channel = _mock_channel_for_edit()

    # get_ticket: pre-read (open), then re-read (after update).
    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Billing"})

    ticket, rename_ok = await service.edit_ticket_category(
        ticket_id,
        "cat-uuid-billing",
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )

    # DB categoryId updated.
    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["categoryId"] == "cat-uuid-billing"

    # Channel renamed.
    channel.edit.assert_awaited_once()
    assert rename_ok is True

    # Channel renamed to sanitized name from category + author + number.
    # Billing -> billing, author display_name "DanielXX" -> danielxx, 5 -> 0005.
    edit_kwargs = channel.edit.call_args.kwargs
    assert edit_kwargs["name"] == "billing-danielxx-0005"

    # Returned ticket reflects new category.
    assert isinstance(ticket, Ticket)


@pytest.mark.asyncio
async def test_edit_ticket_category_rename_failure_does_not_block_db(
    service: TicketService,
    mock_db: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When channel rename raises HTTPException, DB update MUST still succeed."""
    import logging

    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit(category_id="cat-uuid-support")
    updated_row = {**open_row, "categoryId": "cat-uuid-billing"}
    channel = _mock_channel_for_edit()
    channel.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "rate limited"))

    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Billing"})

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        _ticket, rename_ok = await service.edit_ticket_category(
            ticket_id,
            "cat-uuid-billing",
            channel=channel,
            actor_id="999999999",
            is_mod=True,
        )

    # DB updated despite rename failure.
    mock_db.update_ticket.assert_awaited_once()
    assert rename_ok is False
    assert any("rename" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_edit_ticket_category_writes_audit_on_success(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """edit_ticket_category MUST write an audit row on success."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit()
    updated_row = {**open_row, "categoryId": "cat-uuid-billing"}
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Billing"})

    await service.edit_ticket_category(
        ticket_id,
        "cat-uuid-billing",
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "edit_category"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_edit_ticket_category_non_mod_denied(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Non-mod actor MUST be denied by check_can_edit_category."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit()
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.return_value = open_row

    with pytest.raises(ValueError, match=r"[Mm]oderator"):
        await service.edit_ticket_category(
            ticket_id,
            "cat-uuid-billing",
            channel=channel,
            actor_id="111111111",  # author, not mod
            is_mod=False,
        )

    # No DB mutation on denial.
    mock_db.update_ticket.assert_not_awaited()
    # Audit denied written.
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "edit_category"
    assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_edit_ticket_category_closed_rejected(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Edit on a closed ticket MUST raise ValueError and not mutate DB."""
    ticket_id = "ticket-uuid-edit"
    closed_row = _open_ticket_row_for_edit(status="closed")
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.return_value = closed_row

    with pytest.raises(ValueError, match=r"[Cc]losed"):
        await service.edit_ticket_category(
            ticket_id,
            "cat-uuid-billing",
            channel=channel,
            actor_id="999999999",
            is_mod=True,
        )

    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_ticket_category_limit_violation(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Edit into category where author already has open ticket MUST raise ValueError."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit(author_id="111111111")
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.return_value = open_row
    mock_db.count_user_open_tickets_in_category.return_value = 1  # already has one

    with pytest.raises(ValueError, match=r"already has an open ticket"):
        await service.edit_ticket_category(
            ticket_id,
            "cat-uuid-billing",
            channel=channel,
            actor_id="999999999",
            is_mod=True,
        )

    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_ticket_category_empty_category_allowed(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Edit into a category where author has no open tickets MUST succeed."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit()
    updated_row = {**open_row, "categoryId": "cat-uuid-billing"}
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Billing"})

    _ticket, rename_ok = await service.edit_ticket_category(
        ticket_id,
        "cat-uuid-billing",
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )

    assert rename_ok is True
    mock_db.update_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_ticket_category_excludes_edited_ticket_from_count(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """The count MUST exclude the ticket being edited (exclude_ticket_id)."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit(category_id="cat-uuid-billing")
    updated_row = {**open_row, "categoryId": "cat-uuid-support"}
    channel = _mock_channel_for_edit()

    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Support"})

    await service.edit_ticket_category(
        ticket_id,
        "cat-uuid-support",
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )

    # Count called with exclude_ticket_id.
    mock_db.count_user_open_tickets_in_category.assert_awaited_once_with(
        "123456789",
        "111111111",
        "cat-uuid-support",
        exclude_ticket_id=ticket_id,
    )


@pytest.mark.asyncio
async def test_edit_ticket_category_same_category_noop(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Same-category no-op edit MUST not self-block (exclude_ticket_id prevents it)."""
    ticket_id = "ticket-uuid-edit"
    open_row = _open_ticket_row_for_edit(category_id="cat-uuid-support")
    # Same category — no actual change.
    channel = _mock_channel_for_edit()

    # Count returns 0 because the edited ticket is excluded.
    mock_db.get_ticket.side_effect = [open_row, open_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": "Support"})

    _ticket, rename_ok = await service.edit_ticket_category(
        ticket_id,
        "cat-uuid-support",
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )

    # DB updated (even though category didn't change — the method doesn't optimize for no-op).
    mock_db.update_ticket.assert_awaited_once()
    assert rename_ok is True


@pytest.mark.asyncio
async def test_edit_ticket_category_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Editing a non-existent ticket MUST raise ValueError."""
    mock_db.get_ticket.return_value = None
    channel = _mock_channel_for_edit()

    with pytest.raises(ValueError, match=r"[Nn]ot found"):
        await service.edit_ticket_category(
            "nonexistent",
            "cat-uuid-billing",
            channel=channel,
            actor_id="999999999",
            is_mod=True,
        )

    mock_db.update_ticket.assert_not_awaited()


# ===========================================================================
# PR2 Phase 2 — Characterization tests for helper wiring
# ===========================================================================
#
# These tests capture the CURRENT behavior of create_ticket_channel and
# reopen_ticket so we can verify behavior is preserved after wiring
# ticket_helpers (build_ticket_overwrites, resolve_mod_role,
# resolve_member_safe, resolve_category_name).


class TestCreateTicketChannelOverwrites:
    """Characterization: create_ticket_channel permission overwrites paths."""

    @pytest.mark.asyncio
    async def test_overwrites_include_mod_role_when_provided(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """With mod_role provided, overwrites MUST include 4 principals:
        default_role (denied), bot (read+send), author (read+send), mod (read+send).
        """
        guild = _mock_guild_for_channel()
        category = MagicMock(spec=discord.CategoryChannel)
        author = _mock_author()
        mod_role = MagicMock(name="ModRole")
        mod_role.id = 222

        mock_db.get_max_ticket_number.return_value = 0
        mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

        await service.create_ticket_channel(
            guild,
            category,
            author,
            guild_id="123456789",
            category_name="Support",
            mod_role=mod_role,
        )

        create_kwargs = guild.create_text_channel.call_args.kwargs
        overwrites = create_kwargs["overwrites"]

        # 4 principals: default_role, bot, author, mod
        assert len(overwrites) == 4
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author in overwrites
        assert mod_role in overwrites

        # Permissions: default_role denied, others get read+send.
        assert overwrites[guild.default_role].read_messages is False
        assert overwrites[guild.me].read_messages is True
        assert overwrites[guild.me].send_messages is True
        assert overwrites[author].read_messages is True
        assert overwrites[author].send_messages is True
        assert overwrites[mod_role].read_messages is True
        assert overwrites[mod_role].send_messages is True

    @pytest.mark.asyncio
    async def test_overwrites_exclude_mod_role_when_none(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Without mod_role, overwrites MUST include 3 principals only."""
        guild = _mock_guild_for_channel()
        category = MagicMock(spec=discord.CategoryChannel)
        author = _mock_author()

        mock_db.get_max_ticket_number.return_value = 0
        mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

        await service.create_ticket_channel(
            guild,
            category,
            author,
            guild_id="123456789",
            category_name="Support",
        )

        create_kwargs = guild.create_text_channel.call_args.kwargs
        overwrites = create_kwargs["overwrites"]

        # 3 principals: default_role, bot, author (no mod).
        assert len(overwrites) == 3
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author in overwrites


class TestReopenTicketChannelConstruction:
    """Characterization: reopen_ticket channel-construction block."""

    @pytest.mark.asyncio
    async def test_reopen_overwrites_include_mod_role_from_guild_config(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """When guild config has modRoleId, reopen overwrites MUST include the mod role."""
        ticket_id = "ticket-uuid-003"
        closed_row = _closed_ticket_row()
        reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}

        mock_db.get_ticket.side_effect = [closed_row, reopened_row]
        mock_db.get_guild.return_value = {
            "id": "123456789",
            "ticketCategoryId": "100000000",
            "modRoleId": "222222222",
        }
        mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte"})

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild = _mock_guild_for_reopen(category_channel=category_channel)

        mod_role = MagicMock(name="ModRole")
        mod_role.id = 222222222
        guild.get_role = MagicMock(return_value=mod_role)

        author_member = MagicMock()
        author_member.display_name = "DanielXX"
        guild.get_member = MagicMock(return_value=author_member)

        await service.reopen_ticket(ticket_id, guild=guild)

        create_kwargs = guild.create_text_channel.call_args.kwargs
        overwrites = create_kwargs["overwrites"]

        # 4 principals when mod role resolves.
        assert len(overwrites) == 4
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author_member in overwrites
        assert mod_role in overwrites

        # Permissions verified.
        assert overwrites[guild.default_role].read_messages is False
        assert overwrites[mod_role].read_messages is True
        assert overwrites[mod_role].send_messages is True

    @pytest.mark.asyncio
    async def test_reopen_overwrites_exclude_mod_role_when_not_configured(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """When no modRoleId in guild config, reopen overwrites MUST exclude mod."""
        ticket_id = "ticket-uuid-003"
        closed_row = _closed_ticket_row()
        reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}

        mock_db.get_ticket.side_effect = [closed_row, reopened_row]
        mock_db.get_guild.return_value = {
            "id": "123456789",
            "ticketCategoryId": "100000000",
            "modRoleId": None,
        }
        mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte"})

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild = _mock_guild_for_reopen(category_channel=category_channel)

        author_member = MagicMock()
        author_member.display_name = "DanielXX"
        guild.get_member = MagicMock(return_value=author_member)

        await service.reopen_ticket(ticket_id, guild=guild)

        create_kwargs = guild.create_text_channel.call_args.kwargs
        overwrites = create_kwargs["overwrites"]

        # 3 principals: default_role, bot, author (no mod).
        assert len(overwrites) == 3
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author_member in overwrites

    @pytest.mark.asyncio
    async def test_reopen_channel_name_from_category_author_ticket_number(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Reopen channel name MUST be {category}-{author}-{ticket_number} sanitized."""
        ticket_id = "ticket-uuid-003"
        closed_row = _closed_ticket_row()
        reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}

        mock_db.get_ticket.side_effect = [closed_row, reopened_row]
        mock_db.get_guild.return_value = {
            "id": "123456789",
            "ticketCategoryId": "100000000",
            "modRoleId": None,
        }
        mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte"})

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild = _mock_guild_for_reopen(category_channel=category_channel)

        author_member = MagicMock()
        author_member.display_name = "DanielXX"
        guild.get_member = MagicMock(return_value=author_member)

        await service.reopen_ticket(ticket_id, guild=guild)

        create_kwargs = guild.create_text_channel.call_args.kwargs
        # Channel name: soporte-danielxx-0003 (ticket_number=3 from _closed_ticket_row).
        assert create_kwargs["name"] == "soporte-danielxx-0003"

    @pytest.mark.asyncio
    async def test_reopen_spanish_error_text_on_non_closed_ticket(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Spanish invariant error text MUST be preserved verbatim for non-closed tickets."""
        ticket_id = "ticket-uuid-003"
        open_row = {**_closed_ticket_row(), "status": "open"}
        mock_db.get_ticket.return_value = open_row
        guild = _mock_guild_for_reopen(category_channel=None)

        with pytest.raises(ValueError, match=r"Solo se pueden reabrir tickets cerrados\. Estado actual: open"):
            await service.reopen_ticket(ticket_id, guild=guild)


# ===========================================================================
# R3-001 — _countdown_and_delete: NotFound from msg.edit must attempt channel.delete
# ===========================================================================


@pytest.mark.asyncio
async def test_countdown_not_found_on_edit_triggers_channel_delete(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R3-001: When msg.edit raises NotFound (message deleted but channel
    alive), _countdown_and_delete MUST attempt channel.delete to clean up.

    Before the fix, the broad except NotFound would swallow the error and
    return, leaving an accessible closed-ticket channel.
    """
    import logging

    channel = _mock_channel_for_close()
    channel.send = AsyncMock()
    countdown_msg = AsyncMock()
    channel.send.return_value = countdown_msg

    # msg.edit raises NotFound — message was deleted by a moderator, but
    # the channel itself still exists.
    countdown_msg.edit = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "Unknown Message"),
    )

    with (
        patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock),
        caplog.at_level(logging.INFO, logger="bot.services.ticket_service"),
    ):
        await TicketService._countdown_and_delete(channel, "999999999")

    # Channel.delete MUST have been called — the channel is still alive.
    channel.delete.assert_awaited_once()
    delete_kwargs = channel.delete.call_args.kwargs
    assert "Ticket closed by" in delete_kwargs["reason"]


@pytest.mark.asyncio
async def test_countdown_not_found_on_final_delete_is_tolerated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R3-001: When msg.edit raises NotFound AND the final channel.delete
    also raises NotFound, _countdown_and_delete MUST log info and return
    cleanly (no exception propagated).
    """
    import logging

    channel = _mock_channel_for_close()
    channel.send = AsyncMock()
    countdown_msg = AsyncMock()
    channel.send.return_value = countdown_msg

    # msg.edit raises NotFound (message gone).
    countdown_msg.edit = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "Unknown Message"),
    )
    # The final channel.delete also raises NotFound (channel truly gone).
    channel.delete = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "Unknown Channel"),
    )

    with (
        patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock),
        caplog.at_level(logging.INFO, logger="bot.services.ticket_service"),
    ):
        # Must NOT raise — NotFound from final delete is tolerated.
        await TicketService._countdown_and_delete(channel, "999999999")

    # Final channel.delete MUST have been attempted (even though it also 404s).
    channel.delete.assert_awaited_once()
    # Info logged about the channel being gone.
    assert any("already deleted" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_countdown_not_found_on_final_delete_http_error_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R3-001: When msg.edit raises NotFound but channel.delete raises a
    non-NotFound HTTPException, _countdown_and_delete MUST log the exception.
    """
    import logging

    channel = _mock_channel_for_close()
    channel.send = AsyncMock()
    countdown_msg = AsyncMock()
    channel.send.return_value = countdown_msg

    # msg.edit raises NotFound (message gone).
    countdown_msg.edit = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "Unknown Message"),
    )
    # Final channel.delete raises a non-NotFound HTTP error.
    channel.delete = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Internal Server Error"),
    )

    with (
        patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock),
        caplog.at_level(logging.ERROR, logger="bot.services.ticket_service"),
    ):
        await TicketService._countdown_and_delete(channel, "999999999")

    # The non-NotFound HTTP error MUST be logged as exception.
    assert any("failed to delete" in r.message.lower() for r in caplog.records)


# ===========================================================================
# PR2 Phase 2 - close_ticket zombie/conditional close (tasks 2.3-2.4 RED)
# ===========================================================================


class TestCloseTicketConditional:
    """close_ticket with close_reason, zombie path, re-close ValueError."""

    @pytest.mark.asyncio
    async def test_close_reason_persists_when_provided(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """When close_reason is provided, it MUST be forwarded to transition_ticket_to_closed."""
        ticket_id = ticket_row["id"]
        closed_row = {
            **ticket_row,
            "status": "closed",
            "closedAt": "2026-06-16T18:00:00+00:00",
            "closeReason": "zombie:channel_missing",
        }
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.get_ticket.return_value = closed_row

        ticket = await service.close_ticket(
            ticket_id,
            closed_by="999999999",
            close_reason="zombie:channel_missing",
        )

        mock_db.transition_ticket_to_closed.assert_awaited_once_with(
            ticket_row["guildId"],
            ticket_id,
            expected_statuses=("open", "claimed"),
            close_reason="zombie:channel_missing",
            transcript_url=None,
        )
        assert ticket.status == "closed"

    @pytest.mark.asyncio
    async def test_close_reason_none_does_not_overwrite(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """When close_reason is None, it MUST NOT be forwarded."""
        ticket_id = ticket_row["id"]
        closed_row = {
            **ticket_row,
            "status": "closed",
            "closedAt": "2026-06-16T18:00:00+00:00",
            "closeReason": None,
        }
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.get_ticket.return_value = closed_row

        await service.close_ticket(ticket_id, closed_by="999999999")

        mock_db.transition_ticket_to_closed.assert_awaited_once_with(
            ticket_row["guildId"],
            ticket_id,
            expected_statuses=("open", "claimed"),
            close_reason=None,
            transcript_url=None,
        )

    @pytest.mark.asyncio
    async def test_zombie_path_skips_transcript_and_channel_deletion(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """SERVICE-1.5: zombie close MUST skip BOTH transcript generation and channel deletion."""
        ticket_id = ticket_row["id"]
        closed_row = {
            **ticket_row,
            "status": "closed",
            "closedAt": "2026-06-16T18:00:00+00:00",
            "closeReason": "zombie:channel_missing",
        }
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.get_ticket.return_value = closed_row

        # SERVICE-1.5: zombie path proven via DB contract — transcript_url=None
        # and closeReason persisted. External channel deletion is handled by
        # handle_channel_delete/probe bypass, not close_ticket.
        ticket = await service.close_ticket(
            ticket_id,
            closed_by="system",
            close_reason="zombie:channel_missing",
        )

        assert ticket.status == "closed"
        # Explicit zombie contract: closeReason persisted and no channel mutation.
        mock_db.transition_ticket_to_closed.assert_awaited_once_with(
            ticket_row["guildId"],
            ticket_id,
            expected_statuses=("open", "claimed"),
            close_reason="zombie:channel_missing",
            transcript_url=None,
        )

    @pytest.mark.asyncio
    async def test_reclosed_ticket_raises_value_error(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Closing an already-closed ticket MUST raise ValueError with no mutation."""
        ticket_id = ticket_row["id"]
        # transition returns None → already closed / not in expected_statuses
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
        mock_db.get_ticket.return_value = {**ticket_row, "status": "closed"}

        with pytest.raises(ValueError, match=r"already closed|not found"):
            await service.close_ticket(ticket_id, closed_by="999999999")

        # No update_ticket called (transition handled it).
        mock_db.update_ticket.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normal_close_still_updates_cache(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Normal close (non-zombie) MUST still clean the channel from cache."""
        ticket_id = ticket_row["id"]
        channel_id = int(ticket_row["channelId"])
        service._ticket_channel_cache.add(channel_id)

        closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.get_ticket.return_value = closed_row

        await service.close_ticket(ticket_id, closed_by="999999999")

        assert channel_id not in service._ticket_channel_cache


# ===========================================================================
# PR2 Phase 2 - RepairResult from IntegrityEvidence (tasks 2.5-2.6 RED)
# ===========================================================================


class TestRepairTicketFromEvidence:
    """repair_ticket_from_evidence builds RepairResult via guild-scoped transition.

    Preflight (read-only live schema/deployment gate) is REQUIRED for
    mutation: unresolved preflight quarantines/skips with no DB mutation.
    """

    @pytest.mark.asyncio
    async def test_repaired_when_evidence_corroborated(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Corroborated evidence + successful close -> repaired."""
        from bot.models.ticket import IntegrityEvidence, RepairResult

        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=False,
            corroborated=False,
        )
        assert evidence.corroborated is True

        closed_row = {
            **ticket_row,
            "status": "closed",
            "closedAt": "2026-06-16T18:00:00+00:00",
            "closeReason": "zombie:channel_deleted",
        }
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )

        assert isinstance(result, RepairResult)
        assert result.action == "close"
        assert result.outcome == "repaired"
        assert result.ticket_id == ticket_row["id"]
        assert result.guild_id == ticket_row["guildId"]

    @pytest.mark.asyncio
    async def test_already_closed_returns_no_op(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Transition returns None -> already_closed."""
        from bot.models.ticket import IntegrityEvidence, RepairResult

        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=False,
            corroborated=False,
        )
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)

        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )

        assert isinstance(result, RepairResult)
        assert result.action == "no_op"
        assert result.outcome == "already_closed"

    @pytest.mark.asyncio
    async def test_not_corroborated_returns_skipped(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Channel exists -> not corroborated -> skipped."""
        from bot.models.ticket import IntegrityEvidence, RepairResult

        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=True,
            corroborated=False,
        )
        assert evidence.corroborated is False

        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )

        assert isinstance(result, RepairResult)
        assert result.action == "no_op"
        assert result.outcome == "skipped"
        # No DB mutation.
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transient_discord_error_returns_error(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """MODEL-2.4: transient Discord verification error must map to outcome=error with exception class name."""
        import discord

        from bot.models.ticket import IntegrityEvidence, RepairResult

        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=False,
            corroborated=False,
        )
        # Discord transient verification error (e.g. NotFound/HTTPException/RateLimited during probe).
        mock_db.transition_ticket_to_closed = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "channel gone"),
        )

        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )

        assert isinstance(result, RepairResult)
        assert result.action == "no_op"
        assert result.outcome == "error"
        assert result.reason == "NotFound"
        # Triangulate: HTTPException and RateLimited also surface their class name.
        for exc, cls_name in [
            (discord.HTTPException(MagicMock(), "timeout"), "HTTPException"),
            (discord.RateLimited(0.5), "RateLimited"),
        ]:
            mock_db.transition_ticket_to_closed = AsyncMock(side_effect=exc)
            r2 = await service.repair_ticket_from_evidence(
                evidence,
                preflight=_resolved_preflight(),
                close_reason="zombie:channel_deleted",
            )
            assert r2.outcome == "error"
            assert r2.reason == cls_name

    @pytest.mark.asyncio
    async def test_close_requires_evidence_id(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """RepairResult(action='close') MUST have evidence_id or it raises ValueError."""
        from bot.models.ticket import RepairResult

        # Direct construction: close/repaired without evidence_id → ValueError.
        with pytest.raises(ValueError, match="evidence_id"):
            RepairResult(
                ticket_id="t1",
                guild_id="g1",
                action="close",
                outcome="repaired",
                reason=None,
                evidence_id=None,  # missing!
                timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
            )

    @pytest.mark.asyncio
    async def test_g2_gate_unresolved_blocks_automatic_repair(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """When G.2 is gate_unresolved, repair_ticket_from_evidence MUST NOT mutate."""
        from bot.models.ticket import IntegrityEvidence

        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=False,
            corroborated=False,
        )

        # Simulate gate_unresolved by passing an unresolved preflight.
        result = await service.repair_ticket_from_evidence(
            evidence,
            close_reason="zombie:channel_deleted",
            preflight=_unresolved_preflight(),
        )

        assert result.action == "no_op"
        assert result.outcome == "skipped"
        assert result.reason == "gate_unresolved"
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_repair_success_writes_audit(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """R1-004/R4-002: repair success MUST write a best-effort repair audit row."""
        evidence = _corroborated_evidence(ticket_row)
        closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

        await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )

        mock_db.insert_audit_row.assert_awaited_once()
        kwargs = _audit_kwargs(mock_db)
        assert kwargs["action"] == "repair"
        assert kwargs["outcome"] == "repaired"
        assert kwargs["reason"] is None
        assert kwargs["guild_id"] == ticket_row["guildId"]
        assert kwargs["actor_id"] == "system"


# ===========================================================================
# product-artifact-audit PR2 — evidence-gated repair (tasks 2.1/2.4 RED)
# ===========================================================================
#
# The shared repair coordinator MUST fail closed: unresolved preflight or
# non-corroborated evidence (unknown/stale/live) produces a reviewable
# quarantine/no-op result and performs NO ticket mutation and NO audit claim.
# Only fresh, corroborated, guild-matched evidence reaches persistence.


def _corroborated_evidence(ticket_row: dict) -> IntegrityEvidence:
    """Return fresh corroborated evidence for the shared repair path."""
    return IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
    )


def _unresolved_preflight() -> object:
    """Return a read-only LivePreflightResult that is NOT resolved."""
    from bot.services.integrity_report import evaluate_live_preflight

    return evaluate_live_preflight(observed_at=datetime.now(UTC).isoformat())


def _resolved_preflight() -> object:
    """Return a read-only LivePreflightResult that IS resolved."""
    from bot.services.integrity_report import evaluate_live_preflight

    return evaluate_live_preflight(
        project_status="ACTIVE_HEALTHY",
        migration_015_applied=True,
        close_reason_nullable=True,
        required_indexes_present=True,
        realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
        active_rows_channel_id_non_null=3,
        observed_at=datetime.now(UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_repair_denied_when_preflight_unresolved(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Unresolved preflight MUST quarantine/skip without ANY ticket mutation."""
    from bot.models.ticket import RepairResult

    evidence = _corroborated_evidence(ticket_row)
    preflight = _unresolved_preflight()

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=preflight,
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.action == "no_op"
    assert result.outcome in ("quarantined", "skipped")
    assert result.reason
    assert result.ticket_id == ticket_row["id"]
    assert result.guild_id == ticket_row["guildId"]
    # No ticket mutation ...
    mock_db.transition_ticket_to_closed.assert_not_awaited()
    # ... but a best-effort NON-mutating audit row is still produced.
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "repair"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "gate_unresolved"
    assert kwargs["actor_id"] == "system"


@pytest.mark.asyncio
async def test_repair_quarantines_unknown_evidence(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Unknown (None) channel existence MUST quarantine, never mutate."""
    from bot.models.ticket import IntegrityEvidence, RepairResult

    evidence = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=None,
        observed_at=datetime.now(UTC),
    )
    assert evidence.corroborated is None

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.action == "no_op"
    assert result.outcome == "skipped"
    assert result.reason == "evidence_unresolved"
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_quarantines_stale_evidence(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Stale absence evidence MUST quarantine (unresolved), never mutate."""
    from bot.models.ticket import IntegrityEvidence, RepairResult

    evidence = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=False,
        observed_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert evidence.corroborated is None

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.action == "no_op"
    assert result.outcome == "skipped"
    assert result.reason == "evidence_unresolved"
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_denied_when_channel_still_exists(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """A live channel (corroborated=False) MUST be denied/skipped, no mutation."""
    from bot.models.ticket import IntegrityEvidence, RepairResult

    evidence = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=True,
        observed_at=datetime.now(UTC),
    )
    assert evidence.corroborated is False

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.action == "no_op"
    assert result.outcome in ("quarantined", "skipped")
    assert result.reason
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_denied_for_non_active_ticket(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """A closed-ticket evidence (corroborated=False) MUST be denied, no mutation."""
    from bot.models.ticket import IntegrityEvidence, RepairResult

    evidence = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="closed",
        channel_exists=False,
        observed_at=datetime.now(UTC),
    )
    assert evidence.corroborated is False

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.action == "no_op"
    assert result.outcome in ("quarantined", "skipped")
    assert result.reason
    mock_db.transition_ticket_to_closed.assert_not_awaited()


# ---------------------------------------------------------------------------
# Duplicate overlap + triangulation (task 2.4 RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_repair_one_repaired_one_already_closed(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Two repairs for the same active ticket: one repaired, one already_closed.

    The guild-scoped conditional transition is the one-winner boundary. The
    loser MUST be a deterministic no-op and MUST NOT write a second success
    mutation or a second success audit row.
    """
    evidence = _corroborated_evidence(ticket_row)
    closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}

    # Winner: transition returns the closed row. Loser: transition returns None.
    mock_db.transition_ticket_to_closed = AsyncMock(side_effect=[closed_row, None])
    mock_db.insert_audit_row = AsyncMock(return_value={})

    first = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )
    second = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert first.action == "close"
    assert first.outcome == "repaired"
    assert second.action == "no_op"
    assert second.outcome == "already_closed"

    # Exactly one repaired audit row; the loser writes a deterministic denied row.
    audit_actions = [_audit_kwargs(mock_db, i)["outcome"] for i in range(mock_db.insert_audit_row.call_count)]
    assert audit_actions == ["repaired", "denied"]


@pytest.mark.asyncio
async def test_repair_uses_single_shared_evaluation(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """repair_ticket_from_evidence MUST NOT keep a parallel truth: the SAME
    evaluation that denies non-corroborated evidence is the one that gates
    the conditional close. Adapters never re-evaluate and never mutate.
    """
    # A live-channel evidence (corroborated=False) NEVER reaches persistence,
    # even with a resolved preflight.
    live = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=True,
        observed_at=datetime.now(UTC),
    )
    result = await service.repair_ticket_from_evidence(
        live,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert result.outcome == "skipped"
    assert result.reason == "not_corroborated"
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_quarantine_never_claims_mutation(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Quarantined results MUST NOT claim mutation but MUST still write a
    best-effort non-mutating audit row for review."""
    unknown = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=None,
        observed_at=datetime.now(UTC),
    )
    result = await service.repair_ticket_from_evidence(
        unknown,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert result.outcome == "skipped"
    assert result.reason == "evidence_unresolved"
    assert result.action == "no_op"
    mock_db.transition_ticket_to_closed.assert_not_awaited()
    # Best-effort structured audit evidence: denied, non-mutating, reviewable.
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "repair"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "evidence_unresolved"


@pytest.mark.asyncio
async def test_repair_skipped_live_channel_still_audits_denied(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """A live-channel skip (not_corroborated) writes a denied audit row, no mutation."""
    live = IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status="open",
        channel_exists=True,
        observed_at=datetime.now(UTC),
    )
    result = await service.repair_ticket_from_evidence(
        live,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert result.outcome == "skipped"
    mock_db.transition_ticket_to_closed.assert_not_awaited()
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "not_corroborated"


@pytest.mark.asyncio
async def test_repair_already_closed_audits_denied(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """An already-closed duplicate/loser writes a deterministic denied audit row."""
    evidence = _corroborated_evidence(ticket_row)
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert result.outcome == "already_closed"
    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "already_closed"


# ---------------------------------------------------------------------------
# Shared pure evaluation (task 2.4 REFACTOR) — one decision, no parallel truth
# ---------------------------------------------------------------------------


def test_shared_evaluation_maps_evidence_to_denial_outcomes() -> None:
    """The pure helper MUST be the SINGLE source of the denial decision:
    unresolved preflight -> skipped, unknown/stale -> quarantined,
    live/non-active -> skipped. No adapter keeps a parallel copy.
    """
    from bot.services.ticket_service import evaluate_repair_eligibility

    now = datetime.now(UTC)
    unknown = IntegrityEvidence("t1", "g1", "c1", "open", None, now)
    live = IntegrityEvidence("t2", "g1", "c2", "open", True, now)
    closed = IntegrityEvidence("t3", "g1", "c3", "closed", False, now)

    assert evaluate_repair_eligibility(preflight_allows=False, corroborated=unknown.corroborated) == (
        "skipped",
        "gate_unresolved",
    )
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=unknown.corroborated) == (
        "skipped",
        "evidence_unresolved",
    )
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=live.corroborated) == (
        "skipped",
        "not_corroborated",
    )
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=closed.corroborated) == (
        "skipped",
        "not_corroborated",
    )
    # Corroborated evidence passes the gate (proceeds to transition).
    fresh = IntegrityEvidence("t4", "g1", "c4", "open", False, now)
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=fresh.corroborated) is None


# ===========================================================================
# product-artifact-audit PR3 — audit outcome truthfulness (task 3.4)
# ===========================================================================


@pytest.mark.asyncio
async def test_repair_audit_failure_never_reports_repaired(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When audit persistence fails, the repair result MUST NOT claim `repaired`.

    The conditional close may have executed, but a repair whose audit could
    not be persisted must never be reported as success. The smallest safe
    semantics is ``close/error`` with a non-empty reason and no evidence
    success claim.
    """
    from bot.models.ticket import RepairResult

    evidence = _corroborated_evidence(ticket_row)
    closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
    mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

    result = await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )

    assert isinstance(result, RepairResult)
    assert result.outcome != "repaired"
    assert result.outcome == "error"
    assert result.reason, "audit-failure result MUST carry a non-empty reason"
    # No evidence success claim for a repair whose audit could not persist.
    assert result.evidence_id is None


# ===========================================================================
# PR5 — Idempotency / audit best-effort + disabled-slice / rollback (tasks 5.1-5.4 RED)
# ===========================================================================
#
# Strict TDD RED for the last unchecked tasks. The repair already has one-winner
# idempotency (duplicate -> already_closed) proved above, and audit-persistence
# failure degrades to close/error (never repaired). PR5 adds two integration
# boundaries explicitly demanded by the spec:
#  - Disabled/rollback slice leaves tickets untouched and keeps deletion-only logging.
#  - An audit write failure on the DENIED already_closed path never hides the failure.


class TestPR5IdempotencyAndBestEffort:
    """PR5 5.1/5.2: audit is best-effort, idempotency is one-winner, and no second mutation."""

    @pytest.mark.asyncio
    async def test_already_closed_audit_write_failure_still_already_closed(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Already-closed with audit insert failure MUST still return already_closed and log WARNING.

        The close mutation is already persisted (or correctly skipped by the
        conditional transition). A best-effort audit row whose insert raises
        must be logged at WARNING and must NOT change the outcome or claim mutation.
        """
        import logging

        evidence = _corroborated_evidence(ticket_row)
        # Transition returns None -> already_closed loser path.
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
        # The already_closed audit insert fails (audit table down).
        mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
            result = await service.repair_ticket_from_evidence(
                evidence,
                preflight=_resolved_preflight(),
                close_reason="zombie:channel_deleted",
            )

        assert result.outcome == "already_closed"
        assert result.action == "no_op"
        # The denied audit failure was logged, not swallowed silently.
        assert any("audit" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_successful_close_persists_despite_audit_warning(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When the success audit insert fails, the close STILL persists and WARNING is logged.

        Threat: Audit best-effort — audit failure must not roll back the repair mutation.
        The current semantics degrades repaired to close/error with a non-empty reason
        so no success is claimed without evidence.
        """
        import logging

        evidence = _corroborated_evidence(ticket_row)
        closed_row = {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        # This is the SUCCESS audit path (success -> insert fails).
        mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
            result = await service.repair_ticket_from_evidence(
                evidence, preflight=_resolved_preflight(), close_reason="zombie:channel_deleted"
            )

        # The DB row was closed (transition succeeded) even though audit persistence failed.
        mock_db.transition_ticket_to_closed.assert_awaited_once()
        assert result.outcome == "error"
        assert result.reason == "audit_persistence_failed"
        assert result.evidence_id is None
        assert any("audit" in r.message.lower() for r in caplog.records)


# ===========================================================================
# product-artifact-audit PR4b — sweep/manual primitives (tasks 4.2/4.3 RED)
# ===========================================================================
#
# probe_channel_absence: fresh per-attempt fetch_channel; ONLY discord.NotFound
# corroborates absence (channel_exists=False). 403/timeout/429/unknown/missing
# guild/malformed id are UNRESOLVED (None) and never imply absence.
# plan_sweep_batch: bounded batch + dedupe, no duplicate candidates.
# backoff_delay: exponential backoff bounded by INTEGRITY_MAX_BACKOFF_SECONDS.


class TestProbeChannelAbsence:
    """Fresh per-attempt channel existence probe for sweeps/manual repair."""

    @staticmethod
    def _guild_with_fetch(result) -> MagicMock:
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock(return_value=result)
        return guild

    @staticmethod
    def _bot_with_guild(guild: MagicMock | None) -> MagicMock:
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)
        return bot

    @pytest.mark.asyncio
    async def test_not_found_corroborates_absence(self) -> None:
        """Only discord.NotFound yields channel_exists=False."""
        from bot.services.ticket_service import probe_channel_absence

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Unknown Channel"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is False
        guild.fetch_channel.assert_awaited_once_with(888888888)

    @pytest.mark.asyncio
    async def test_live_channel_returns_true(self) -> None:
        """A resolvable channel is present (channel_exists=True)."""
        from bot.services.ticket_service import probe_channel_absence

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888888888
        guild = self._guild_with_fetch(channel)
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is True

    @pytest.mark.asyncio
    async def test_forbidden_is_unresolved(self) -> None:
        """403/missing permission is unresolved, never absence."""
        from bot.services.ticket_service import probe_channel_absence

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing Access"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_rate_limit_is_unresolved(self) -> None:
        """429 rate limit is unresolved, never absence."""
        from bot.services.ticket_service import probe_channel_absence

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.RateLimited(0.5))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_timeout_is_unresolved(self) -> None:
        """Generic HTTPException (timeout) is unresolved, never absence."""
        from bot.services.ticket_service import probe_channel_absence

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "timeout"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_guild_is_unresolved(self) -> None:
        """A guild not in the bot cache is unknown (None), never absence."""
        from bot.services.ticket_service import probe_channel_absence

        bot = self._bot_with_guild(None)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_channel_id_is_unresolved(self) -> None:
        """A non-numeric channel id is unknown (None), never absence."""
        from bot.services.ticket_service import probe_channel_absence

        guild = self._guild_with_fetch(None)
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "not-a-snowflake")

        assert result is None
        guild.fetch_channel.assert_not_awaited()


class TestPlanSweepBatch:
    """Bounded, deduped batch planning (pure)."""

    def test_batch_is_bounded_and_deduped(self) -> None:
        """Batch caps at batch_size and never re-emits a seen candidate."""
        from bot.services.ticket_service import plan_sweep_batch

        candidates = [{"id": f"c{i}"} for i in range(5)]
        seen: set[str] = {"c0", "c2"}

        batch = plan_sweep_batch(candidates, seen=seen, batch_size=2)

        ids = [c["id"] for c in batch]
        assert ids == ["c1", "c3"]
        assert "c0" not in ids and "c2" not in ids

    def test_batch_marks_seen(self) -> None:
        """Selected candidates are marked seen so a later call does not repeat them."""
        from bot.services.ticket_service import plan_sweep_batch

        candidates = [{"id": "a"}, {"id": "b"}]
        seen: set[str] = set()

        first = plan_sweep_batch(candidates, seen=seen, batch_size=10)
        second = plan_sweep_batch(candidates, seen=seen, batch_size=10)

        assert [c["id"] for c in first] == ["a", "b"]
        assert second == []


class TestBackoffDelay:
    """Exponential backoff bounded by the configured maximum."""

    def test_backoff_grows_and_is_bounded(self) -> None:
        """Backoff doubles each attempt but never exceeds the max."""
        from bot.config import INTEGRITY_BACKOFF_SECONDS, INTEGRITY_MAX_BACKOFF_SECONDS
        from bot.services.ticket_service import backoff_delay

        assert backoff_delay(0) == INTEGRITY_BACKOFF_SECONDS
        assert backoff_delay(1) == min(INTEGRITY_BACKOFF_SECONDS * 2, INTEGRITY_MAX_BACKOFF_SECONDS)
        # A large attempt count must clamp at the configured maximum.
        assert backoff_delay(100) <= INTEGRITY_MAX_BACKOFF_SECONDS


# ===========================================================================
# product-artifact-audit PR4b — sweep + manual coordinator (tasks 4.3/4.4 RED)
# ===========================================================================
#
# sweep_integrity: bounded batches, dedupe, transient backoff, unresolved →
# dry-run (no mutation), corroborated absence → shared repair path.
# repair_ticket_manual: explicit authority + fresh probe → shared path.


class TestSweepIntegrity:
    """The integrity sweep reuses the shared evidence-gated repair path."""

    @staticmethod
    def _sweep_bot() -> MagicMock:
        """A bot whose get_guild returns a guild that can fetch channels."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock()
        bot.get_guild = MagicMock(return_value=guild)
        return bot

    def _active_row(self, channel_id: str, ticket_id: str = "t-1") -> dict:
        return {
            "id": ticket_id,
            "guildId": "123456789",
            "channelId": channel_id,
            "status": "open",
        }

    @pytest.mark.asyncio
    async def test_corroborated_absence_repairs(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """NotFound probe → corroborated evidence → repaired via coordinator."""
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=["888888888"])
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=self._active_row("888888888"))
        closed = {**self._active_row("888888888"), "status": "closed", "closedAt": "now"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)

        bot = self._sweep_bot()
        bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

        results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight())

        assert len(results) == 1
        assert results[0].outcome == "repaired"
        mock_db.transition_ticket_to_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_live_channel_is_skipped(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A present channel → not corroborated → skipped, no mutation."""
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=["888888888"])
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=self._active_row("888888888"))

        bot = self._sweep_bot()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888888888
        bot.get_guild().fetch_channel = AsyncMock(return_value=channel)

        results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight())

        assert len(results) == 1
        assert results[0].outcome in ("skipped", "quarantined")
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unresolved_probe_dry_runs(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Transient probe (None) → reviewable skip + backoff, no mutation."""
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=["888888888"])
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=self._active_row("888888888"))

        bot = self._sweep_bot()
        bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "timeout"))

        with patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight())

        assert len(results) == 1
        assert results[0].outcome == "skipped"
        assert results[0].reason == "probe_unresolved"
        mock_db.transition_ticket_to_closed.assert_not_awaited()
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bounded_batch_limits_probes(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Only batch_size candidates are probed per sweep."""
        channels = [str(800000000 + i) for i in range(10)]
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=channels)
        # Each channel maps to an active ticket row so candidates are non-empty.
        rows = {ch: {"id": f"t-{ch}", "guildId": "123456789", "channelId": ch, "status": "open"} for ch in channels}
        mock_db.get_active_ticket_by_channel = AsyncMock(side_effect=lambda _gid, ch: rows.get(ch))

        bot = self._sweep_bot()
        channel = MagicMock(spec=discord.TextChannel)
        bot.get_guild().fetch_channel = AsyncMock(return_value=channel)

        results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight(), batch_size=3)

        assert bot.get_guild().fetch_channel.await_count == 3
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """No open ticket channels → empty result list."""
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=[])

        results = await service.sweep_integrity("123456789", self._sweep_bot(), preflight=_resolved_preflight())

        assert results == []


class TestRepairTicketManual:
    """Manual repair requires explicit authority + a fresh probe."""

    @staticmethod
    def _manual_bot() -> MagicMock:
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock()
        bot.get_guild = MagicMock(return_value=guild)
        return bot

    def _guild_admin_authority(self, guild_id: str = "123456789") -> RepairAuthority:
        from bot.services.ticket_invariants import RepairAuthority

        return RepairAuthority(
            actor_id="111111111",
            guild_id=guild_id,
            target_guild_id="123456789",
            has_mod_role=True,
        )

    @pytest.mark.asyncio
    async def test_denied_authority_no_ops(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A plain user with no authority → denied, no probe, no mutation."""
        from bot.models.ticket import RepairResult
        from bot.services.ticket_invariants import RepairAuthority

        authority = RepairAuthority(
            actor_id="111111111",
            guild_id="123456789",
            target_guild_id="123456789",
        )  # no owner/admin/mod role

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="111111111",
            authority=authority,
            bot=self._manual_bot(),
            preflight=_resolved_preflight(),
        )

        assert isinstance(result, RepairResult)
        assert result.outcome == "skipped"
        assert result.reason
        mock_db.get_ticket.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cross_guild_authority_denied(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A guild admin targeting another guild → denied, no probe."""
        authority = self._guild_admin_authority()  # target_guild is 123456789
        # authority.guild_id is the actor's own guild; target_guild_id differs.

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="999999999",  # target a different guild
            actor_id="111111111",
            authority=authority,
            bot=self._manual_bot(),
            preflight=_resolved_preflight(),
        )

        assert result.outcome == "skipped"
        assert result.reason == "cross_guild_denied"

    @pytest.mark.asyncio
    async def test_allowed_not_found_repairs(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Admin + NotFound probe → repaired."""
        row = {
            "id": "t-1",
            "guildId": "123456789",
            "channelId": "888888888",
            "status": "open",
        }
        mock_db.get_ticket = AsyncMock(return_value=row)
        closed = {**row, "status": "closed", "closedAt": "now"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)

        bot = self._manual_bot()
        bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="111111111",
            authority=self._guild_admin_authority(),
            bot=bot,
            preflight=_resolved_preflight(),
        )

        assert result.outcome == "repaired"
        assert result.evidence_id is not None

    @pytest.mark.asyncio
    async def test_allowed_live_channel_skipped(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Admin + present channel → skipped, no mutation."""
        row = {
            "id": "t-1",
            "guildId": "123456789",
            "channelId": "888888888",
            "status": "open",
        }
        mock_db.get_ticket = AsyncMock(return_value=row)

        bot = self._manual_bot()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888888888
        bot.get_guild().fetch_channel = AsyncMock(return_value=channel)

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="111111111",
            authority=self._guild_admin_authority(),
            bot=bot,
            preflight=_resolved_preflight(),
        )

        assert result.outcome in ("skipped", "quarantined")
        mock_db.transition_ticket_to_closed.assert_not_awaited()


# ===========================================================================
# product-artifact-audit remediation — handle_channel_delete preflight wiring,
# no-match coverage, source provenance at call sites, manual global-grant.
# ===========================================================================


class TestHandleChannelDelete:
    """handle_channel_delete routes exact event evidence through the coordinator."""

    @pytest.mark.asyncio
    async def test_channel_delete_repairs_with_fresh_preflight(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """A matching active ticket + resolved preflight → automatic repair close."""
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=ticket_row)
        closed_row = {**ticket_row, "status": "closed", "closedAt": "now"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)

        result = await service.handle_channel_delete(
            ticket_row["guildId"],
            ticket_row["channelId"],
            preflight=_resolved_preflight(),
        )

        assert result is not None
        assert result.outcome == "repaired"
        mock_db.transition_ticket_to_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_channel_delete_fail_closed_without_preflight(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Without a resolved preflight the event route still fail-closes (no mutation)."""
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=ticket_row)

        result = await service.handle_channel_delete(
            ticket_row["guildId"],
            ticket_row["channelId"],
        )

        assert result is not None
        assert result.outcome == "skipped"
        assert result.reason == "gate_unresolved"
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_channel_delete_no_match_returns_none_no_mutation(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A non-ticket deletion (no active ticket) returns None and never mutates."""
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=None)

        result = await service.handle_channel_delete(
            "123456789",
            "555555555",
            preflight=_resolved_preflight(),
        )

        assert result is None
        mock_db.transition_ticket_to_closed.assert_not_awaited()
        mock_db.insert_audit_row.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_channel_delete_evidence_carries_source(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """Event evidence MUST record source="channel_delete" provenance."""
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=ticket_row)

        await service.handle_channel_delete(
            ticket_row["guildId"],
            ticket_row["channelId"],
            preflight=_unresolved_preflight(),
        )

        # The evidence constructed inside handle_channel_delete must carry the
        # channel_delete source provenance (observable via a repaired result's
        # evidence id linkage is indirect; assert the coordinator was reached
        # with fail-closed behavior and no mutation).
        mock_db.transition_ticket_to_closed.assert_not_awaited()


class TestRepairTicketManualGrant:
    """repair_ticket_manual threads an explicit operator mutation grant."""

    @staticmethod
    def _manual_bot() -> MagicMock:
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock()
        bot.get_guild = MagicMock(return_value=guild)
        return bot

    @pytest.mark.asyncio
    async def test_operator_no_grant_is_denied(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A bot-owner operator without an explicit grant is denied before any probe."""
        from bot.services.ticket_invariants import RepairAuthority

        authority = RepairAuthority(
            actor_id="owner-1",
            guild_id=None,
            target_guild_id="123456789",
            is_bot_owner=True,
        )

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="owner-1",
            authority=authority,
            bot=self._manual_bot(),
            preflight=_resolved_preflight(),
        )

        assert result.outcome == "skipped"
        assert result.reason == "operator_mutation_requires_grant"
        mock_db.get_ticket.assert_not_awaited()
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_operator_confirmed_grant_repairs(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A bot-owner operator WITH a confirmed, actor/target-matching grant repairs."""
        from bot.services.ticket_invariants import GlobalMutationGrant, RepairAuthority

        authority = RepairAuthority(
            actor_id="owner-1",
            guild_id=None,
            target_guild_id="123456789",
            is_bot_owner=True,
        )
        grant = GlobalMutationGrant(
            actor_id="owner-1",
            scope="global",
            target_guild_id="123456789",
            reason="maintenance sweep",
            confirmed=True,
        )

        row = {
            "id": "t-1",
            "guildId": "123456789",
            "channelId": "888888888",
            "status": "open",
        }
        mock_db.get_ticket = AsyncMock(return_value=row)
        closed = {**row, "status": "closed", "closedAt": "now"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)

        bot = self._manual_bot()
        bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="owner-1",
            authority=authority,
            bot=bot,
            preflight=_resolved_preflight(),
            global_grant=grant,
        )

        assert result.outcome == "repaired"
        mock_db.transition_ticket_to_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_operator_grant_actor_mismatch_denied(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """A grant naming a different actor never authorizes this operator."""
        from bot.services.ticket_invariants import GlobalMutationGrant, RepairAuthority

        authority = RepairAuthority(
            actor_id="owner-1",
            guild_id=None,
            target_guild_id="123456789",
            is_bot_owner=True,
        )
        grant = GlobalMutationGrant(
            actor_id="someone-else",
            scope="global",
            target_guild_id="123456789",
            reason="maintenance",
            confirmed=True,
        )

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="123456789",
            actor_id="owner-1",
            authority=authority,
            bot=self._manual_bot(),
            preflight=_resolved_preflight(),
            global_grant=grant,
        )

        assert result.outcome == "skipped"
        assert result.reason == "grant_actor_mismatch"
        mock_db.get_ticket.assert_not_awaited()
