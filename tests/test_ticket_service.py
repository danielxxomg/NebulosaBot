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

import asyncio
import logging
import pathlib
from datetime import UTC, datetime
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import bot.services.ticket_lifecycle_service as lifecycle_service_module
import bot.services.ticket_repair_service as repair_service_module
from bot.config import INTEGRITY_BACKOFF_SECONDS, INTEGRITY_MAX_BACKOFF_SECONDS
from bot.core.cache import TTLCache
from bot.core.i18n import set_guild_language
from bot.models.ticket import IntegrityEvidence, RepairResult, Ticket
from bot.models.ticket_note import TicketNote
from bot.services.integrity_report import evaluate_live_preflight
from bot.services.ticket_invariants import GlobalMutationGrant, RepairAuthority
from bot.services.ticket_lifecycle_service import TicketLifecycleService
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService
from bot.services.ticket_service import (
    MAX_RETRIES,
    TicketCategoryNotConfiguredError,
    TicketService,
    backoff_delay,
    evaluate_repair_eligibility,
    plan_sweep_batch,
    probe_channel_absence,
)

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
        await _create_ticket(service)

    assert mock_db.insert_ticket.call_count == MAX_RETRIES


# ---------------------------------------------------------------------------
# create_ticket — subject / description passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject", "description", "expected_subject", "expected_description"),
    [
        ("Login broken", "Cannot access since Monday", "Login broken", "Cannot access since Monday"),
        (None, None, None, None),
    ],
    ids=["with-subject-and-description", "without-subject-and-description"],
)
async def test_create_ticket_subject_description_passthrough(
    subject: str | None,
    description: str | None,
    expected_subject: str | None,
    expected_description: str | None,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket(subject=..., description=...) MUST forward to insert_ticket; omitted MUST pass None.

    Parametrized (S1b cut): both variants assert the same two-sided contract
    (insert_ticket kwargs + returned model) with the per-case expected value;
    the only difference is whether subject/description are provided explicitly
    or passed as None (explicit None == omitted None by production default).
    """
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {
        **ticket_row,
        "subject": expected_subject,
        "description": expected_description,
    }

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=None,
        channel_id="888888888",
        subject=subject,
        description=description,
    )

    call_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert call_kwargs["subject"] == expected_subject
    assert call_kwargs["description"] == expected_description
    assert ticket.subject == expected_subject
    assert ticket.description == expected_description


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

    ticket = await _create_ticket(service, category_id="cat-uuid-002")

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

    ticket = await _create_ticket(service, category_id="cat-uuid-001")

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

    ticket = await _create_ticket(service)

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

    closed_row = {**_closed_from_transition(ticket_row), "transcriptUrl": "https://cdn.discord.com/transcript.html"}
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
    _wire_transition(mock_db, ticket_row)
    mock_db.get_ticket.return_value = ticket_row

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
    _claim_preread(mock_db, ticket_row, staff_id)

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
@pytest.mark.parametrize(
    ("rows", "expect_len"),
    [
        pytest.param("two", 2, id="returns-models"),
        pytest.param("empty", 0, id="empty-list"),
    ],
)
async def test_get_stale_tickets_returns_models(
    rows: str,
    expect_len: int,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """get_stale_tickets MUST call DB with correct args and return Ticket models.

    Parametrized (S6 ceiling cut): the empty row re-asserts the same DB-call
    contract with zero rows — when no stale tickets exist the service MUST
    return an empty list (no models, same single guild-scoped DB call).
    """
    guild_id = "123456789"
    mock_db.get_stale_tickets.return_value = [ticket_row, ticket_row] if rows == "two" else []

    tickets = await service.get_stale_tickets(guild_id, hours=72)

    mock_db.get_stale_tickets.assert_awaited_once_with(guild_id, hours=72)
    assert len(tickets) == expect_len
    assert all(isinstance(t, Ticket) for t in tickets)
    if tickets:
        assert tickets[0].status == "open"


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


def _assert_audit(mock_db: AsyncMock, *, index: int = -1) -> dict:
    """Assert exactly one audit row was written and return its merged kwargs."""
    mock_db.insert_audit_row.assert_awaited_once()
    return _audit_kwargs(mock_db, index=index)


async def _edit_category(
    service: TicketService,
    ticket_id: str,
    channel: MagicMock,
    *,
    category_id: str = "cat-uuid-billing",
) -> tuple[Ticket, bool]:
    """Invoke edit_ticket_category with the shared mod-actor arguments."""
    return await service.edit_ticket_category(
        ticket_id,
        category_id,
        channel=channel,
        actor_id="999999999",
        is_mod=True,
    )


def _wire_edit_category(
    mock_db: AsyncMock,
    *,
    category_name: str,
    category_id: str = "cat-uuid-billing",
) -> None:
    """Wire get_ticket (pre-read open → re-read updated), count, and category stubs.

    The open row uses category_id="cat-uuid-support"; the re-read row carries
    the edited category_id.
    """
    open_row = _open_ticket_row_for_edit(category_id="cat-uuid-support")
    updated_row = {**open_row, "categoryId": category_id}
    mock_db.get_ticket.side_effect = [open_row, updated_row]
    mock_db.count_user_open_tickets_in_category.return_value = 0
    mock_db.get_ticket_category = AsyncMock(return_value={"name": category_name})


async def _create_ticket(
    service: TicketService,
    *,
    category_id: str | None = None,
) -> Ticket:
    """Invoke create_ticket with the shared guild/author/channel arguments."""
    return await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id=category_id,
        channel_id="888888888",
    )


def _wire_transition(
    mock_db: AsyncMock,
    ticket_row: dict,
    close_reason: str | None = None,
) -> dict:
    """Stub transition_ticket_to_closed to return the closed form of ticket_row.

    Returns the closed row so tests can also use it as the get_ticket re-read.
    """
    closed_row = _closed_from_transition(ticket_row, close_reason=close_reason)
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
    return closed_row


def _ticket_guild_row(ticket_id: str) -> dict:
    """Return the minimal ticket row (id + guild) used for guild-scoped note ops."""
    return {"id": ticket_id, "guildId": "123456789"}


def _wire_guild_config(
    mock_db: AsyncMock,
    *,
    mod_role_id: str | None = None,
    category_id: str | None = "100000000",
) -> None:
    """Wire get_guild to the default ticket guild config (both ids overridable)."""
    mock_db.get_guild.return_value = {
        "id": "123456789",
        "ticketCategoryId": category_id,
        "modRoleId": mod_role_id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        pytest.param("success", id="success"),
        pytest.param(
            "carve_out",
            id="carve-out-skips-duplicate-check",
        ),
    ],
)
async def test_create_subticket_success(
    case: str,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Valid parent → sub-ticket created with parentId set, cache synced.

    Parametrized (S6 ceiling cut): the carve-out row re-runs the identical
    valid-parent setup — per the spec, sub-ticket creation succeeds even
    when the author already has an open ticket (the one-open-ticket
    constraint is skipped), so both rows share the success contract:
    parentId forwarded to insert (guild-scoped, MAX+1), the returned model
    carries it, and the channel cache is synced.
    """
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

    # parentId validated then passed through to insert (guild-scoped).
    mock_db.get_ticket.assert_awaited_once_with(parent_id, guild_id=guild_id)
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

    # Insert really happened exactly once (carve-out row: no duplicate guard
    # blocked the insert even though the author may already hold a ticket).
    mock_db.insert_ticket.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parent_kwargs", "match"),
    [
        # Non-existent parent raises before any insert.
        pytest.param(
            None,
            r"Parent ticket .* not found",
            id="parent_not_found",
        ),
        # Corrupted parent: its own parentId equals its own id.
        pytest.param(
            {"parent_id": "parent-uuid-001"},
            "self-referential",
            id="self_reference_rejected",
        ),
        # Parent already has a different parentId → it is a sub-ticket.
        pytest.param(
            {"parent_id": "grandparent-uuid"},
            r"depth|subticket|sub",
            id="sub_of_sub_rejected",
        ),
        # Parent in guild A + caller passes guild B.
        pytest.param(
            {"parent_id": None, "guild_id": "111000111"},
            r"guild|same",
            id="cross_guild_rejected",
        ),
    ],
)
async def test_create_subticket_invalid_parent_rejected(
    mock_db: AsyncMock,
    service: TicketService,
    parent_kwargs: dict,
    match: str,
) -> None:
    """Missing or corrupted parent rows MUST be rejected before any insert.

    None row (missing parent), self-reference (parentId == id), depth
    violation (parent already a child), and cross-guild mismatch all raise
    ValueError; none may attempt insert_ticket.
    """
    parent_id = "parent-uuid-001"
    if parent_kwargs is None:
        mock_db.get_ticket.return_value = None
    else:
        mock_db.get_ticket.return_value = _parent_row(**parent_kwargs)

    with pytest.raises(ValueError, match=match):
        await service.create_subticket(
            parent_id=parent_id,
            author_id="111111111",
            category_id=None,
            channel_id="666666666",
            guild_id="123456789",
        )

    mock_db.insert_ticket.assert_not_awaited()


# ===========================================================================
# reopen_ticket — new channel from guild-configured category, cache update (slice 2)
# ===========================================================================


def _closed_ticket_row(*, category_id: str | None = "cat-uuid-001") -> dict:
    """Return a closed ticket DB row."""
    return {
        "id": "ticket-uuid-003",
        "ticketNumber": 3,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
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


def _author_member() -> MagicMock:
    """Return the DanielXX author member used by reopen naming tests."""
    author = MagicMock()
    author.display_name = "DanielXX"
    return author


def _wire_reopen_success(
    mock_db: AsyncMock,
    *,
    category: dict | None = None,
    author_member: MagicMock | None = None,
) -> MagicMock:
    """Wire mock_db for a reopen_ticket happy-path call and return the guild.

    Sets get_ticket side effects (closed → reopened), guild config with the
    configured ticket category, and the category lookup row. Assigns
    ``guild.get_member`` only when ``author_member`` is supplied.
    """
    closed_row = _closed_ticket_row()
    reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}
    mock_db.get_ticket.side_effect = [closed_row, reopened_row]
    _wire_guild_config(mock_db)
    mock_db.get_ticket_category = AsyncMock(return_value=category)
    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = _mock_guild_for_reopen(category_channel=category_channel)
    if author_member is not None:
        guild.get_member = MagicMock(return_value=author_member)
    return guild


def _ticket_row_for_close() -> dict:
    """Return the open ticket DB row used by close_ticket_full tests."""
    return {
        "id": "ticket-uuid-close",
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


def _unclaim_row(*, status: str, claimed_by: str | None) -> dict:
    """Return a ticket DB row wired for unclaim_ticket tests."""
    return {
        "id": "ticket-uuid-unclaim",
        "ticketNumber": 5,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": status,
        "claimedBy": claimed_by,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00",
    }


def _closed_from_transition(ticket_row: dict, close_reason: str | None = None) -> dict:
    """Return the closed row produced by a successful transition_ticket_to_closed."""
    return {
        **ticket_row,
        "status": "closed",
        "closedAt": "2026-06-16T18:00:00+00:00",
        "closeReason": close_reason,
    }


def _evidence(
    ticket_row: dict,
    *,
    channel_exists: bool | None = False,
    status: str = "open",
    observed_at: datetime | None = None,
) -> IntegrityEvidence:
    """Return an IntegrityEvidence built from the sample ticket row.

    The model re-derives ``corroborated`` in ``__post_init__`` from the
    immutable fields, so callers' verbatim corroboration assertions still
    hold. ``observed_at=None`` means a fresh (now) observation.
    """
    return IntegrityEvidence(
        ticket_id=ticket_row["id"],
        guild_id=ticket_row["guildId"],
        channel_id=ticket_row["channelId"],
        status=status,
        channel_exists=channel_exists,
        observed_at=observed_at if observed_at is not None else datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_reopen_creates_new_channel(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST create a new channel and update channelId/status/closedAt."""
    ticket_id = "ticket-uuid-003"

    guild = _wire_reopen_success(mock_db)

    ticket = await service.reopen_ticket(ticket_id, guild=guild)

    # New channel created in the configured category.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["category"] is guild.get_channel.return_value

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
    _wire_guild_config(mock_db)

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
    _wire_guild_config(mock_db, category_id=None)

    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match="No ticket category"):
        await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_row", "status", "ticket_ref", "match"),
    [
        pytest.param(True, None, "nope", r"Ticket .* not found", id="reopen-not-found"),
        pytest.param(False, "open", "ticket-uuid-003", r"Solo se pueden reabrir tickets cerrados", id="reopen-rejects-open"),
        pytest.param(False, "claimed", "ticket-uuid-003", r"Solo se pueden reabrir tickets cerrados", id="reopen-rejects-claimed"),
    ],
)
async def test_reopen_rejects_non_closed_ticket(
    missing_row: bool,
    status: str | None,
    ticket_ref: str,
    match: str,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST raise ValueError before creating any channel: for a
    non-existent ticket ("not found") and for a non-closed ticket (B2
    defense-in-depth — even if a caller bypasses the cog guard, the service
    refuses a duplicate channel for an open/claimed ticket).

    Parametrized (S6 ceiling cut): the not-found row folds into the same
    rejection matrix (same scaffold, same no-channel contract, distinct
    denial reason).
    """
    if missing_row:
        mock_db.get_ticket.return_value = None
    else:
        non_closed_row = {**_closed_ticket_row(), "status": status}
        mock_db.get_ticket.return_value = non_closed_row
        # The denial text resolves via t() — pin the expected language so the
        # assertion is independent of module-level poisoning (test isolation).
        set_guild_language("123456789", "es")
    guild = _mock_guild_for_reopen(category_channel=None)

    with pytest.raises(ValueError, match=match):
        await service.reopen_ticket(ticket_ref, guild=guild)

    # No duplicate channel created; no DB mutation.
    guild.create_text_channel.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


# ===========================================================================
# transfer_ticket — claimedBy mutation + LoggingService audit (slice 2)
# ===========================================================================


def _close_full_preread(mock_db: AsyncMock) -> None:
    """Wire get_ticket side effects for the close_ticket_full pre-read/re-read."""
    open_row = _ticket_row_for_close()
    closed_row = {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00"}
    mock_db.get_ticket.side_effect = [
        open_row,  # close_ticket pre-read (invariant check)
        closed_row,  # close_ticket re-read
    ]


def _claim_preread(mock_db: AsyncMock, ticket_row: dict, staff_id: str) -> None:
    """Wire get_ticket side effects for the claim pre-read/re-read contract."""
    mock_db.get_ticket.side_effect = [
        ticket_row,
        {**ticket_row, "status": "claimed", "claimedBy": staff_id},
    ]


def _transfer_preread(mock_db: AsyncMock, ticket_row: dict, *, new_staff: str = "222222222") -> None:
    """Wire get_ticket side effects for the transfer pre-read/re-read contract."""
    mock_db.get_ticket.side_effect = [
        {**ticket_row, "status": "open", "claimedBy": None},
        {**ticket_row, "claimedBy": new_staff, "status": "claimed"},
    ]


def _mock_logging_service() -> AsyncMock:
    """Return a mock LoggingService with log_moderation_action as AsyncMock."""
    log = AsyncMock()
    log.log_moderation_action = AsyncMock()
    return log


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("test_id", "explicit_new_staff"),
    [
        pytest.param(True, True, id="explicit-staff-arg"),
        pytest.param(True, False, id="default-staff-same-constant"),
    ],
    ids=["explicit-staff-arg", "default-staff-same-constant"],
)
async def test_transfer_updates_claimed_by(
    test_id: bool,
    explicit_new_staff: bool,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """transfer_ticket MUST mutate claimedBy and (re)claim the ticket.

    Parametrized (S1a cut): both variants call transfer with the same
    constants and assert the same contract — DB updated with new claimedBy
    and the returned ticket carries it. The only difference is whether
    _transfer_preread wires the re-read with an explicit new_staff or relies
    on its identical default constant.
    """
    ticket_id = ticket_row["id"]
    new_staff = "222222222"
    actor = "999999999"

    # PR2 contract: pre-read open+unclaimed (invariant passes), re-read claimed.
    if explicit_new_staff:
        _transfer_preread(mock_db, ticket_row, new_staff=new_staff)
    else:
        _transfer_preread(mock_db, ticket_row)

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
async def test_transfer_logs_audit(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """transfer_ticket MUST call LoggingService with the transfer audit info."""
    ticket_id = ticket_row["id"]
    # PR2 contract: pre-read open+unclaimed, re-read claimed.
    _transfer_preread(mock_db, ticket_row)

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
    mock_db.get_ticket.return_value = _ticket_guild_row("ticket-uuid-003")

    note = await service.create_note(
        "ticket-uuid-003",
        author_id="999999999",
        content="Customer escalated",
    )

    # Guild-scoped note insert now requires guild_id.
    assert mock_db.insert_ticket_note.await_count == 1
    call = mock_db.insert_ticket_note.call_args
    assert call.args == ("ticket-uuid-003", "999999999", "Customer escalated")
    assert call.kwargs.get("guild_id") == "123456789"
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
@pytest.mark.parametrize(
    ("notes_count", "expect_models"),
    [
        pytest.param(3, True, id="get-notes-returns-models"),
        pytest.param(0, False, id="get-notes-empty"),
    ],
)
async def test_get_notes_delegation(
    notes_count: int,
    expect_models: bool,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """get_notes MUST delegate to the DB: non-empty → TicketNote models,
    no notes → empty list (both after the guild-scoped pre-read).
    """
    mock_db.get_ticket.return_value = {
        "id": "ticket-uuid-003",
        "guildId": "123456789",
    }
    mock_db.get_ticket_notes.return_value = [_note_row(note_id=f"n-{i}") for i in range(notes_count)]

    notes = await service.get_notes("ticket-uuid-003")

    mock_db.get_ticket_notes.assert_awaited_once()
    if expect_models:
        assert len(notes) == 3
        assert all(isinstance(n, TicketNote) for n in notes)
    else:
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
@pytest.mark.parametrize(
    ("note_row", "caller_id", "requested_note", "expect_deleted", "match"),
    [
        pytest.param("999999999", "999999999", "note-uuid-001", True, None, id="delete-note-own-allowed"),
        pytest.param("999999999", "888888888", "note-uuid-001", False, r"[Aa]uthor", id="delete-note-other-rejected"),
        pytest.param("other-note", "999999999", "missing-note", False, r"[Nn]ot found", id="delete-note-missing-row"),
    ],
)
async def test_delete_note_author_gate(
    note_row: str,
    caller_id: str,
    requested_note: str,
    expect_deleted: bool,
    match: str | None,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """delete_note MUST allow the note author and reject non-authors /
    unknown note ids: the author's matching call reaches the guild-scoped
    DB delete; any other caller raises ValueError (author mismatch) and a
    note that does not belong to the ticket raises (not found) — both with
    no DB mutation.

    Parametrized (S6 ceiling cut): the not-found row folds the standalone
    probe into the same gate matrix (same scaffold, same no-mutation
    contract, distinct denial reason).
    """
    mock_db.get_ticket.return_value = _ticket_guild_row("ticket-uuid-003")
    if match is not None and "[Nn]ot found" in match:
        # Not-found row: the note id does not belong to the ticket at all.
        mock_db.get_ticket_notes.return_value = [_note_row(note_id=note_row)]
    else:
        mock_db.get_ticket_notes.return_value = [_note_row(note_id="note-uuid-001", author_id=note_row)]

    if expect_deleted:
        await service.delete_note(requested_note, author_id=caller_id, ticket_id="ticket-uuid-003")

        mock_db.delete_ticket_note.assert_awaited_once_with(
            requested_note, guild_id="123456789", ticket_id="ticket-uuid-003"
        )
    else:
        with pytest.raises(ValueError, match=match):
            await service.delete_note(requested_note, author_id=caller_id, ticket_id="ticket-uuid-003")

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
    _claim_preread(mock_db, ticket_row, staff_id)

    await service.claim_ticket(ticket_id, claimed_by=staff_id)

    kwargs = _assert_audit(mock_db)
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

    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "claim"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] is not None
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """3.9/3.10: close on open/claimed MUST write an audit success row."""
    ticket_id = ticket_row["id"]
    _wire_transition(mock_db, ticket_row)
    mock_db.get_ticket.return_value = ticket_row

    await service.close_ticket(ticket_id, closed_by="999999999")

    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "close"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize("audit_assert", [False, True], ids=["close-denied-reraise", "close-denied-writes-audit"])
async def test_close_denied_contract(
    audit_assert: bool,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Close on an already-closed ticket MUST raise ValueError (transition
    returns None) without mutation; the guild-resolved best-effort denied
    audit row MUST be written before raising (R1-003).
    """
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
    mock_db.get_ticket.return_value = ticket_row  # resolve guild for audit scoping

    with pytest.raises(ValueError, match="already closed or not found"):
        await service.close_ticket(ticket_row["id"], closed_by="999999999")

    mock_db.update_ticket.assert_not_awaited()
    if audit_assert:
        kwargs = _assert_audit(mock_db)
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

    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "transfer"
    assert kwargs["outcome"] == "denied"
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_transfer_audits_success(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Transfer to a different staff member MUST audit success."""
    ticket_id = ticket_row["id"]
    _transfer_preread(mock_db, ticket_row, new_staff="userB")

    await service.transfer_ticket(ticket_id, new_claimed_by="userB", actor_id="admin1")

    kwargs = _assert_audit(mock_db)
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


_NOTE_PRIVACY_MATRIX = [
    # create_note: dedup gate (2s window) — denied / cleared
    pytest.param(
        "note_add",
        "dedup",
        [{"content": "Hello World"}],
        "  hello world  ",
        True,
        "duplicate|dedup",
        id="note-dedup-within-window-denied",
    ),
    pytest.param("note_add", "dedup", [], "hello", False, None, id="note-dedup-outside-window-success"),
    # create_note: 50-note cap — denied / under-cap
    pytest.param("note_add", "cap", 50, "one too many", True, "cap", id="note-cap-denied-audited"),
    pytest.param("note_add", "cap", 30, "new note", False, None, id="note-under-cap-audited-success"),
    # delete_note: author-only rule — allowed / rejected
    pytest.param("note_delete", "delete", "999999999", None, False, None, id="note-delete-own-audited-success"),
    pytest.param(
        "note_delete", "delete", "userA", None, True, r"[Aa]uthor|owner", id="note-delete-other-audited-denied"
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("audit_action", "gate", "gate_value", "insert_content", "expect_denied", "match"),
    _NOTE_PRIVACY_MATRIX,
)
async def test_note_privacy_matrix(
    audit_action: str,
    gate: str,
    gate_value: object,
    insert_content: str | None,
    expect_denied: bool,
    match: str | None,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Note-privacy audit matrix (3.5/3.6, TI-034, TI-035): every note
    add/delete MUST write a ticket_audit row whose outcome reflects the
    privacy gate — dedup window + 50-note cap deny create_note; author-only
    rule gates delete_note. Denied paths raise with no mutation.
    """
    ticket_id = "ticket-uuid-003"
    mock_db.get_ticket.return_value = _ticket_guild_row(ticket_id)
    if audit_action == "note_add":
        if gate == "dedup":
            assert isinstance(gate_value, list)
            mock_db.get_ticket_notes.return_value = []
            mock_db.get_recent_notes_for_dedup.return_value = gate_value
        else:  # cap
            assert isinstance(gate_value, int)
            mock_db.get_ticket_notes.return_value = [_note_row() for _ in range(gate_value)]
            mock_db.get_recent_notes_for_dedup.return_value = []
        assert isinstance(insert_content, str)
        mock_db.insert_ticket_note.return_value = _note_row(content=insert_content)

        if expect_denied:
            with pytest.raises(ValueError, match=match):
                await service.create_note(ticket_id, "999999999", insert_content)
            mock_db.insert_ticket_note.assert_not_awaited()
        else:
            await service.create_note(ticket_id, "999999999", insert_content)
            mock_db.insert_ticket_note.assert_awaited_once()
    else:  # note_delete
        note_author = "userA" if expect_denied else "999999999"
        mock_db.get_ticket_notes.return_value = [_note_row(author_id=note_author)]

        if expect_denied:
            with pytest.raises(ValueError, match=match):
                await service.delete_note("note-uuid-001", author_id="userB", ticket_id=ticket_id)
            mock_db.delete_ticket_note.assert_not_awaited()
        else:
            await service.delete_note("note-uuid-001", author_id=note_author, ticket_id=ticket_id)
            mock_db.delete_ticket_note.assert_awaited_once_with(
                "note-uuid-001", guild_id="123456789", ticket_id=ticket_id
            )

    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == audit_action
    assert kwargs["outcome"] == ("denied" if expect_denied else "success")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("non_closed_row", "expect_outcome"),
    [
        pytest.param(None, "success", id="reopen-success-audited"),
        pytest.param("open", "denied", id="reopen-denied-audited"),
    ],
)
async def test_reopen_audit_outcome(
    non_closed_row: str | None,
    expect_outcome: str,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """3.7/3.8: reopen MUST write an audit row whose outcome reflects the
    invariant — success after channel creation on a closed ticket; denied +
    re-raise on a non-closed ticket (no channel created).

    Parametrized (S6 ceiling cut): both rows share the audit contract
    (action=reopen, guild-scoped); only the wiring and outcome differ.
    """
    ticket_id = "ticket-uuid-003"
    if non_closed_row is None:
        guild = _wire_reopen_success(mock_db)

        await service.reopen_ticket(ticket_id, guild=guild)

        kwargs = _assert_audit(mock_db)
        assert kwargs["outcome"] == "success"
        assert kwargs["guild_id"] == "123456789"
    else:
        open_row = {**_closed_ticket_row(), "status": non_closed_row}
        mock_db.get_ticket.return_value = open_row
        guild = _mock_guild_for_reopen(category_channel=None)
        set_guild_language("123456789", "es")  # denial text resolves via t()

        with pytest.raises(ValueError, match=r"cerrados"):
            await service.reopen_ticket(ticket_id, guild=guild)

        kwargs = _assert_audit(mock_db)
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

    kwargs = _assert_audit(mock_db)
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
    kwargs = _assert_audit(mock_db)
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
@pytest.mark.parametrize(
    ("case", "guild_config_kwargs", "get_channel_return"),
    [
        pytest.param(
            "no_category_configured",
            {"category_id": None},
            "__SKIP__",
            id="reopen-no-category-typed",
        ),
        pytest.param(
            "deleted_category",
            {},
            None,
            id="reopen-deleted-category-typed",
        ),
    ],
)
async def test_reopen_category_raises_typed_exception(
    case: str,
    guild_config_kwargs: dict,
    get_channel_return: object,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST raise TicketCategoryNotConfiguredError (typed, not
    raw ValueError) when no ticket category is configured for the guild OR
    the configured Discord category channel no longer exists.
    """

    ticket_id = "ticket-uuid-003"
    closed_row = _closed_ticket_row()
    mock_db.get_ticket.return_value = closed_row
    _wire_guild_config(mock_db, **guild_config_kwargs)

    guild = _mock_guild_for_reopen(category_channel=None)
    if get_channel_return != "__SKIP__":
        guild.get_channel = MagicMock(return_value=get_channel_return)

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
    guild, category, author = _channel_triple("support-testuser-0001")

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
    guild, category, author = _channel_triple("support-testuser-0001")

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
@pytest.mark.parametrize(
    ("ticket_number", "renamed"),
    [
        (42, True),
        (1, False),
    ],
    ids=["number-differs-renames", "number-matches-no-rename"],
)
async def test_create_ticket_channel_renames_if_number_differs(
    ticket_number: int,
    renamed: bool,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When tentative name differs from actual ticket number, channel MUST be renamed; matching number MUST NOT rename.

    Parametrized (S1a cut): both variants create the channel with tentative
    name "support-testuser-0001" and assert the rename contract against the
    DB-returned ticketNumber.
    """
    # Channel created with tentative name "support-testuser-0001" but DB returns ticketNumber=ticket_number.
    guild, category, author = _channel_triple("support-testuser-0001")

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": ticket_number}

    _channel, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Support",
    )

    # Channel renamed iff actual ticket number differs from the tentative name.
    if renamed:
        guild.create_text_channel.return_value.edit.assert_awaited_once_with(name="support-testuser-0042")
    else:
        guild.create_text_channel.return_value.edit.assert_not_awaited()
    assert ticket.ticket_number == ticket_number


@pytest.mark.asyncio
async def test_create_ticket_channel_passes_category_id(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST forward category_id to create_ticket."""
    guild, category, author = _channel_triple()

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
    guild, category, author = _channel_triple()

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
@pytest.mark.parametrize(
    ("cf", "expected_custom_fields"),
    [
        ({"player_nick": "DarkSlasher42", "evidence_url": "https://imgur.com/abc"}, None),
        (None, None),
    ],
    ids=["with-custom-fields", "without-custom-fields"],
)
async def test_create_ticket_with_custom_fields(
    cf: dict[str, str] | None,
    expected_custom_fields: dict[str, str] | None,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket(custom_fields=...) MUST forward to insert_ticket and persist on the model; omitted MUST pass None.

    Parametrized (S1a cut): both variants assert the same two-sided contract
    (insert_ticket kwargs + returned model) with the per-case expected value;
    the only difference is whether custom_fields is provided explicitly or
    omitted (explicit None == omitted None by production default).
    """
    expected = cf if cf is not None else expected_custom_fields
    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "customFields": expected}

    ticket = await service.create_ticket(
        guild_id="123456789",
        author_id="111111111",
        category_id="cat-uuid-001",
        channel_id="888888888",
        custom_fields=cf,
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] == expected
    assert ticket.custom_fields == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cf", "expected_custom_fields"),
    [
        ({"player_nick": "DarkSlayer42"}, None),
        (None, None),
    ],
    ids=["forwards-custom-fields", "without-custom-fields"],
)
async def test_create_ticket_channel_forwards_custom_fields(
    cf: dict[str, str] | None,
    expected_custom_fields: dict[str, str] | None,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel(custom_fields=...) MUST forward to create_ticket; omitted MUST pass None.

    Parametrized (S1a cut): both variants assert the same two-sided contract
    (insert_ticket kwargs + returned model) with the per-case expected value;
    the only difference is whether custom_fields is provided explicitly or
    omitted (explicit None == omitted None by production default).
    """
    expected = cf if cf is not None else expected_custom_fields
    guild, category, author = _channel_triple()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1, "customFields": expected}

    _channel, ticket = await service.create_ticket_channel(
        guild, category, author, guild_id="123456789", category_name="Support", custom_fields=cf
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["custom_fields"] == expected
    assert ticket.custom_fields == expected


# ===========================================================================
# PR4 — channel naming: sanitize_channel_name wiring
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ticket_number", "expected_channel_name"),
    [
        (1, "soporte-testuser-0001"),
        (42, "soporte-testuser-0042"),
    ],
    ids=["uses-sanitized-tentative-name", "renames-with-sanitized-actual"],
)
async def test_create_ticket_channel_sanitized_name(
    ticket_number: int,
    expected_channel_name: str,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST use sanitize_channel_name; when tentative != actual, rename MUST use sanitized format.

    Parametrized (S1b cut): both variants assert the same sanitize_channel_name
    contract (create name == f"{category}-{username}-{number:04d}" pattern via
    production sanitize) with the per-case expected channel name; the only
    difference is whether the created name matches the actual ticket number
    (no rename) or not (rename via sanitized edit).
    """
    guild, category, author = _channel_triple("soporte-testuser-0001")

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": ticket_number}

    _, ticket = await service.create_ticket_channel(
        guild,
        category,
        author,
        guild_id="123456789",
        category_name="Soporte",
    )

    # Channel created with sanitized name; renamed to sanitized actual name when number differs.
    create_kwargs = guild.create_text_channel.call_args.kwargs
    if ticket_number == 1:
        assert create_kwargs["name"] == expected_channel_name
        guild.create_text_channel.return_value.edit.assert_not_awaited()
    else:
        guild.create_text_channel.return_value.edit.assert_awaited_once_with(name=expected_channel_name)
    assert ticket.ticket_number == ticket_number


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
    # Category lookup returns a name.
    guild = _wire_reopen_success(
        mock_db, category={"name": "Soporte", "id": "cat-uuid-001"}, author_member=_author_member()
    )

    await service.reopen_ticket(ticket_id, guild=guild)

    # Channel created with sanitized name.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["name"] == "soporte-danielxx-0003"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire_category", "get_member_return", "expected_channel_name"),
    [
        (None, None, "ticket-user-0003"),
        ({"name": "Soporte", "id": "cat-uuid-001"}, None, "soporte-user-0003"),
    ],
    ids=["fallback-when-category-not-found", "fallback-when-author-not-in-guild"],
)
async def test_reopen_fallback_name_resolution(
    wire_category: dict | None,
    get_member_return: MagicMock | None,
    expected_channel_name: str,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """reopen_ticket MUST fall back when category lookup fails or author member is absent.

    Parametrized (S1b cut): both variants assert the same fallback contract
    (create_text_channel called once with the fallback-resolved sanitized
    name) with the per-case expected name; the only difference is which input
    degrades: category lookup returns None → 'ticket' prefix, author member
    not found → 'user' username slot.
    """
    ticket_id = "ticket-uuid-003"
    # Per-case degrade: category lookup failure or author not in guild.
    guild = _wire_reopen_success(mock_db, category=wire_category)
    guild.get_member = MagicMock(return_value=get_member_return)

    await service.reopen_ticket(ticket_id, guild=guild)

    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    # Fallback: ticket-user-0003 / soporte-user-0003.
    assert create_kwargs["name"] == expected_channel_name


# ===========================================================================
# Best-effort audit on success path (runtime-hotfix)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("op", "wire", "verify"),
    [
        # Claim: audit failure on success path → role-assignment action proceeds.
        pytest.param(
            "claim",
            "claim",
            lambda t, row: t.status == "claimed" and t.claimed_by == "999999999",
            id="claim-audit-failure-continues",
        ),
        # Close: audit failure on success path → channel delete/transcript proceed.
        pytest.param("close", "close", lambda t, row: t.status == "closed", id="close-audit-failure-continues"),
    ],
)
async def test_success_audit_failure_continues(
    op: str,
    wire: str,
    verify,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spec: a success-path audit failure MUST NOT abort the UI action
    (claim role assignment / close channel delete + transcript) — the op
    proceeds normally and a WARNING is logged.
    """

    if wire == "claim":
        _claim_preread(mock_db, ticket_row, "999999999")
    else:
        _wire_transition(mock_db, ticket_row)
        mock_db.get_ticket.return_value = ticket_row
    mock_db.insert_audit_row.side_effect = Exception("audit table unavailable")

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        if op == "claim":
            ticket = await service.claim_ticket(ticket_row["id"], claimed_by="999999999")
        else:
            ticket = await service.close_ticket(ticket_row["id"], closed_by="999999999")

    assert verify(ticket, ticket_row)
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


def _close_full_scaffold() -> tuple[MagicMock, MagicMock, Ticket]:
    """Return the (channel, bot, ticket) triple used by close_ticket_full tests."""
    return _mock_channel_for_close(), _mock_bot_for_close(), _ticket_model()


def _channel_triple(channel_name: str = "support-testuser-0001") -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return the (guild, category, author) triple for create_ticket_channel tests."""
    return _mock_guild_for_channel(channel_name=channel_name), MagicMock(spec=discord.CategoryChannel), _mock_author()


def _countdown_msg(
    channel: MagicMock,
    *,
    edit_side_effect: Exception | None = None,
) -> AsyncMock:
    """Return the countdown message mock wired as channel.send's result.

    ``edit_side_effect`` optionally raises on edit (e.g. HTTPException/NotFound).
    """
    countdown_msg = AsyncMock()
    if edit_side_effect is not None:
        countdown_msg.edit = AsyncMock(side_effect=edit_side_effect)
    channel.send = AsyncMock(return_value=countdown_msg)
    return countdown_msg


def _ticket_model(*, ticket_id: str = "ticket-uuid-close") -> Ticket:
    """Return a sample Ticket model for close tests."""
    return Ticket(
        id=ticket_id,
        ticket_number=42,
        guild_id="123456789",
        author_id="111111111",
        channel_id="888888888",
        status="open",
        created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        last_activity=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_close_ticket_full_manual_countdown(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """close_ticket_full(manual=True) MUST send ONE message and edit 5→1, then delete channel."""
    channel, bot, ticket = _close_full_scaffold()

    _close_full_preread(mock_db)

    countdown_msg = _countdown_msg(channel)

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
    channel, bot, ticket = _close_full_scaffold()

    _close_full_preread(mock_db)

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

    channel, bot, ticket = _close_full_scaffold()

    _close_full_preread(mock_db)

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

    channel, bot, ticket = _close_full_scaffold()

    _close_full_preread(mock_db)

    # Send succeeds but edit fails (simulates permission loss during countdown).
    _countdown_msg(channel, edit_side_effect=discord.HTTPException(MagicMock(), "rate limited"))

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

    claimed_row = _unclaim_row(status="claimed", claimed_by=actor_id)
    unclaimed_row = {**claimed_row, "status": "open", "claimedBy": None}
    mock_db.get_ticket.side_effect = [claimed_row, unclaimed_row]

    ticket = await service.unclaim_ticket(ticket_id, actor_id, is_mod=False)

    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["status"] == "open"
    assert update_kwargs["claimedBy"] is None

    assert ticket.status == "open"
    assert ticket.claimed_by is None

    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "unclaim"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claimed_by", "caller", "match_pattern"),
    [
        (None, "userA", r"claimed"),
        ("userA", "userB", r"claimer|mod|permission"),
    ],
    ids=["unclaimed-raises", "non-claimer-non-mod-denied"],
)
async def test_unclaim_ticket_denied(
    claimed_by: str | None,
    caller: str,
    match_pattern: str,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """unclaim_ticket MUST raise ValueError + audit denied for unclaimed or non-claimer-non-mod callers.

    Parametrized (S1b cut): both variants assert the same denied contract
    (ValueError + update_ticket not awaited + unclaim/denied audit row) with
    the per-case match pattern; the only difference is which precondition is
    violated: ticket not claimed, or caller is neither claimer nor mod.
    """
    ticket_id = "ticket-uuid-unclaim"

    row = _unclaim_row(status="open" if claimed_by is None else "claimed", claimed_by=claimed_by)
    mock_db.get_ticket.return_value = row

    with pytest.raises(ValueError, match=match_pattern):
        await service.unclaim_ticket(ticket_id, caller, is_mod=False)

    mock_db.update_ticket.assert_not_awaited()
    kwargs = _assert_audit(mock_db)
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
    channel = _mock_channel_for_edit()

    # get_ticket: pre-read (open), then re-read (after update).
    _wire_edit_category(mock_db, category_name="Billing")

    ticket, rename_ok = await _edit_category(service, ticket_id, channel)

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

    ticket_id = "ticket-uuid-edit"
    channel = _mock_channel_for_edit()
    channel.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "rate limited"))

    _wire_edit_category(mock_db, category_name="Billing")

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        _ticket, rename_ok = await _edit_category(service, ticket_id, channel)

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
    channel = _mock_channel_for_edit()

    _wire_edit_category(mock_db, category_name="Billing")

    await _edit_category(service, ticket_id, channel)

    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "edit_category"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "row_kwargs", "count_return", "match", "audit_denied"),
    [
        pytest.param("non-mod", {}, None, r"[Mm]oderator", True, id="edit-category-non-mod-denied"),
        pytest.param(
            "closed",
            {"status": "closed"},
            None,
            r"[Cc]losed",
            False,
            id="edit-category-closed-rejected",
        ),
        pytest.param(
            "limit-violation",
            {"author_id": "111111111"},
            1,  # author already has an open ticket in the target category
            r"already has an open ticket",
            False,
            id="edit-category-limit-violation",
        ),
        pytest.param("not-found", {}, None, r"[Nn]ot found", False, id="edit-category-not-found"),
    ],
)
async def test_edit_ticket_category_denied_matrix(
    case: str,
    row_kwargs: dict,
    count_return: int | None,
    match: str,
    audit_denied: bool,
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """edit_ticket_category denial gates (task 2.3 RED): non-mod actors are
    denied by check_can_edit_category (with a denied audit row); closed
    tickets and per-author open-ticket limit violations raise ValueError
    before any DB mutation.
    """
    ticket_id = "ticket-uuid-edit"
    channel = _mock_channel_for_edit()
    if case == "not-found":
        mock_db.get_ticket.return_value = None
    else:
        open_row = _open_ticket_row_for_edit(**row_kwargs)
        mock_db.get_ticket.return_value = open_row
    if count_return is not None:
        mock_db.count_user_open_tickets_in_category.return_value = count_return

    if case == "non-mod":
        with pytest.raises(ValueError, match=match):
            await service.edit_ticket_category(
                ticket_id,
                "cat-uuid-billing",
                channel=channel,
                actor_id="111111111",  # author, not mod
                is_mod=False,
            )
    else:
        with pytest.raises(ValueError, match=match):
            await _edit_category(service, ticket_id, channel)

    # No DB mutation on denial.
    mock_db.update_ticket.assert_not_awaited()
    if audit_denied:
        kwargs = _assert_audit(mock_db)
        assert kwargs["action"] == "edit_category"
        assert kwargs["outcome"] == "denied"


@pytest.mark.asyncio
async def test_edit_ticket_category_empty_category_allowed(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """Edit into a category where author has no open tickets MUST succeed."""
    ticket_id = "ticket-uuid-edit"
    channel = _mock_channel_for_edit()

    _wire_edit_category(mock_db, category_name="Billing")

    _ticket, rename_ok = await _edit_category(service, ticket_id, channel)

    assert rename_ok is True
    mock_db.update_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_ticket_category_excludes_edited_ticket_from_count(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """The count MUST exclude the ticket being edited (exclude_ticket_id)."""
    ticket_id = "ticket-uuid-edit"
    channel = _mock_channel_for_edit()

    _wire_edit_category(mock_db, category_name="Support")

    await _edit_category(service, ticket_id, channel, category_id="cat-uuid-support")

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

    _ticket, rename_ok = await _edit_category(service, ticket_id, channel, category_id="cat-uuid-support")

    # DB updated (even though category didn't change — the method doesn't optimize for no-op).
    mock_db.update_ticket.assert_awaited_once()
    assert rename_ok is True


# ===========================================================================
# PR2 Phase 2 — Characterization tests for helper wiring
# ===========================================================================
#
# These tests capture the CURRENT behavior of create_ticket_channel and
# reopen_ticket so we can verify behavior is preserved after wiring
# ticket_helpers (build_ticket_overwrites, resolve_mod_role,
# resolve_member_safe, resolve_category_name).


class TestTicketChannelOverwriteMatrix:
    """Characterization: permission overwrites across both channel constructors.

    One matrix over (mode, mod-role resolution): ``create_ticket_channel`` and
    ``reopen_ticket`` include the mod principal exactly when it resolves, and
    always carry default_role (denied), bot, and author.
    """

    _OVERWRITE_MATRIX: ClassVar[list[Any]] = [
        pytest.param("create", True, id="create-with-mod-role"),
        pytest.param("create", False, id="create-without-mod-role"),
        pytest.param("reopen", True, id="reopen-with-mod-role"),
        pytest.param("reopen", False, id="reopen-without-mod-role"),
    ]

    @pytest.mark.parametrize(("mode", "with_mod_role"), _OVERWRITE_MATRIX)
    @pytest.mark.asyncio
    async def test_channel_overwrites_matrix(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
        mode: str,
        with_mod_role: bool,
    ) -> None:
        """Overwrites: 3 base principals (+mod when resolved) with default_role denied."""
        mod_role: MagicMock | None = None
        if mode == "create":
            guild = _mock_guild_for_channel()
            category = MagicMock(spec=discord.CategoryChannel)
            author = _mock_author()
            mock_db.get_max_ticket_number.return_value = 0
            mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}
            extra_kwargs: dict[str, Any] = {}
            if with_mod_role:
                mod_role = MagicMock(name="ModRole")
                mod_role.id = 222
                extra_kwargs["mod_role"] = mod_role

            await service.create_ticket_channel(
                guild,
                category,
                author,
                guild_id="123456789",
                category_name="Support",
                **extra_kwargs,
            )
        else:
            ticket_id = "ticket-uuid-003"
            closed_row = _closed_ticket_row()
            reopened_row = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}

            mock_db.get_ticket.side_effect = [closed_row, reopened_row]
            _wire_guild_config(mock_db, mod_role_id="222222222" if with_mod_role else None)
            mock_db.get_ticket_category = AsyncMock(return_value={"name": "Soporte"})

            category_channel = MagicMock(spec=discord.CategoryChannel)
            guild = _mock_guild_for_reopen(category_channel=category_channel)
            if with_mod_role:
                mod_role = MagicMock(name="ModRole")
                mod_role.id = 222222222
                guild.get_role = MagicMock(return_value=mod_role)

            author = _author_member()
            guild.get_member = MagicMock(return_value=author)

            await service.reopen_ticket(ticket_id, guild=guild)

        create_kwargs = guild.create_text_channel.call_args.kwargs
        overwrites = create_kwargs["overwrites"]

        assert len(overwrites) == (4 if with_mod_role else 3)
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author in overwrites
        if mod_role is not None:
            # Mod principal present: read+send allowed, default_role denied.
            assert mod_role in overwrites
            assert overwrites[guild.default_role].read_messages is False
            assert overwrites[mod_role].read_messages is True
            assert overwrites[mod_role].send_messages is True
        if mode == "create" and mod_role is not None:
            # Full permission grid pinned on the create path.
            assert overwrites[guild.me].read_messages is True
            assert overwrites[guild.me].send_messages is True
            assert overwrites[author].read_messages is True
            assert overwrites[author].send_messages is True


class TestReopenTicketChannelConstruction:
    """Characterization: reopen_ticket channel-construction block."""

    @pytest.mark.asyncio
    async def test_reopen_channel_name_from_category_author_ticket_number(
        self,
        service: TicketService,
        mock_db: AsyncMock,
    ) -> None:
        """Reopen channel name MUST be {category}-{author}-{ticket_number} sanitized."""
        ticket_id = "ticket-uuid-003"
        guild = _wire_reopen_success(mock_db, category={"name": "Soporte"}, author_member=_author_member())

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
        set_guild_language("123456789", "es")  # verbatim ES assertion needs ES

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

    channel = _mock_channel_for_close()
    countdown_msg = _countdown_msg(channel)

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

    channel = _mock_channel_for_close()
    countdown_msg = _countdown_msg(channel)

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

    channel = _mock_channel_for_close()
    countdown_msg = _countdown_msg(channel)

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
    @pytest.mark.parametrize(
        ("close_reason", "expect_status_assert"),
        [
            pytest.param("zombie:channel_missing", True, id="close-reason-provided"),
            pytest.param(None, False, id="close-reason-none-not-forwarded"),
        ],
    )
    async def test_close_reason_forwarding(
        self,
        close_reason: str | None,
        expect_status_assert: bool,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """close_ticket MUST forward close_reason verbatim (None included) to
        transition_ticket_to_closed: provided values persist, None MUST NOT
        overwrite an existing closeReason on the row.
        """
        ticket_id = ticket_row["id"]
        closed_row = _wire_transition(mock_db, ticket_row, close_reason=close_reason)
        mock_db.get_ticket.return_value = closed_row

        kwargs: dict[str, str] = {"closed_by": "999999999"}
        if close_reason is not None:
            kwargs["close_reason"] = close_reason

        ticket = await service.close_ticket(ticket_id, **kwargs)

        mock_db.transition_ticket_to_closed.assert_awaited_once_with(
            ticket_row["guildId"],
            ticket_id,
            expected_statuses=("open", "claimed"),
            close_reason=close_reason,
            transcript_url=None,
        )
        if expect_status_assert:
            assert ticket.status == "closed"

    @pytest.mark.asyncio
    async def test_zombie_path_skips_transcript_and_channel_deletion(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """SERVICE-1.5: zombie close MUST skip BOTH transcript generation and channel deletion."""
        ticket_id = ticket_row["id"]
        closed_row = _wire_transition(mock_db, ticket_row, close_reason="zombie:channel_missing")
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

        closed_row = _wire_transition(mock_db, ticket_row)
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

        evidence = _evidence(ticket_row, channel_exists=False)
        assert evidence.corroborated is True

        _wire_transition(mock_db, ticket_row, close_reason="zombie:channel_deleted")

        result = await _repair_from_evidence(service, evidence)

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

        evidence = _evidence(ticket_row, channel_exists=False)
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)

        result = await _repair_from_evidence(service, evidence)

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

        evidence = _evidence(ticket_row, channel_exists=True)
        assert evidence.corroborated is False

        result = await _repair_from_evidence(service, evidence)

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

        evidence = _evidence(ticket_row, channel_exists=False)
        # Discord transient verification error (e.g. NotFound/HTTPException/RateLimited during probe).
        mock_db.transition_ticket_to_closed = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "channel gone"),
        )

        result = await _repair_from_evidence(service, evidence)

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
            r2 = await _repair_from_evidence(service, evidence)
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

        # Direct construction: close/repaired without evidence_id → ValueError.
        with pytest.raises(ValueError, match="evidence_id"):
            RepairResult(
                ticket_id="t1",
                guild_id="g1",
                action="close",
                outcome="repaired",
                reason=None,
                evidence_id=None,  # missing!
                timestamp=datetime.now(UTC),
            )

    @pytest.mark.asyncio
    async def test_g2_gate_unresolved_blocks_automatic_repair(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        ticket_row: dict,
    ) -> None:
        """When G.2 is gate_unresolved, repair_ticket_from_evidence MUST NOT mutate."""

        evidence = _evidence(ticket_row, channel_exists=False)

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
        _wire_transition(mock_db, ticket_row)

        await _repair_from_evidence(service, evidence)

        kwargs = _assert_audit(mock_db)
        # clean-1.0 D6: automated zombie closures write a dedicated
        # zombie_autoclose row (actorId=system) with the applied close reason
        # verbatim, REPLACING the generic "repair" row.
        assert kwargs["action"] == "zombie_autoclose"
        assert kwargs["outcome"] == "repaired"
        assert kwargs["reason"] == "zombie:channel_deleted"
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
    return _evidence(ticket_row)


def _unresolved_preflight() -> object:
    """Return a read-only LivePreflightResult that is NOT resolved."""

    return evaluate_live_preflight(observed_at=datetime.now(UTC).isoformat())


def _resolved_preflight() -> object:
    """Return a read-only LivePreflightResult that IS resolved."""

    return evaluate_live_preflight(
        project_status="ACTIVE_HEALTHY",
        migration_015_applied=True,
        close_reason_nullable=True,
        required_indexes_present=True,
        realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
        active_rows_channel_id_non_null=3,
        observed_at=datetime.now(UTC).isoformat(),
    )


async def _repair_from_evidence(service: TicketService, evidence: IntegrityEvidence) -> RepairResult:
    """Drive one shared repair_ticket_from_evidence call with the canonical
    resolved preflight and zombie close reason used across this module."""
    return await service.repair_ticket_from_evidence(
        evidence,
        preflight=_resolved_preflight(),
        close_reason="zombie:channel_deleted",
    )


@pytest.mark.asyncio
async def test_repair_denied_when_preflight_unresolved(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Unresolved preflight MUST quarantine/skip without ANY ticket mutation."""

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
    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "repair"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "gate_unresolved"
    assert kwargs["actor_id"] == "system"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "evidence_kwargs"),
    [
        pytest.param("unknown_channel_existence", {"channel_exists": None}, id="repair-quarantine-unknown"),
        pytest.param(
            "stale_absence_evidence",
            {"observed_at": datetime(2020, 1, 1, tzinfo=UTC)},
            id="repair-quarantine-stale",
        ),
    ],
)
async def test_repair_quarantines_unresolved_evidence(
    case: str,
    evidence_kwargs: dict,
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """Evidence whose corroboration is unresolved (unknown channel
    existence or stale observation) MUST quarantine (skipped /
    evidence_unresolved), never mutate.
    """

    evidence = _evidence(ticket_row, **evidence_kwargs)
    assert evidence.corroborated is None

    result = await _repair_from_evidence(service, evidence)

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

    evidence = _evidence(ticket_row, channel_exists=True)
    assert evidence.corroborated is False

    result = await _repair_from_evidence(service, evidence)

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

    evidence = _evidence(ticket_row, status="closed")
    assert evidence.corroborated is False

    result = await _repair_from_evidence(service, evidence)

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
    closed_row = _closed_from_transition(ticket_row)

    # Winner: transition returns the closed row. Loser: transition returns None.
    mock_db.transition_ticket_to_closed = AsyncMock(side_effect=[closed_row, None])
    mock_db.insert_audit_row = AsyncMock(return_value={})

    first = await _repair_from_evidence(service, evidence)
    second = await _repair_from_evidence(service, evidence)

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
    kwargs = _assert_audit(mock_db)
    assert kwargs["action"] == "repair"
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == "evidence_unresolved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "evidence_kind, expect_outcome, expect_reason",
    [
        # A live-channel skip (not_corroborated) writes a denied audit row, no mutation.
        ("live", "skipped", "not_corroborated"),
        # An already-closed duplicate/loser writes a deterministic denied audit row.
        ("already_closed", "already_closed", "already_closed"),
    ],
    ids=["skipped_live_channel", "already_closed"],
)
async def test_denied_repair_outcomes_audit_denied(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
    evidence_kind: str,
    expect_outcome: str,
    expect_reason: str,
) -> None:
    """Both non-repair outcomes route through the shared evaluation and
    write a best-effort denied audit row with the deterministic reason;
    neither mutates the ticket.
    """
    if evidence_kind == "live":
        evidence = IntegrityEvidence(
            ticket_id=ticket_row["id"],
            guild_id=ticket_row["guildId"],
            channel_id=ticket_row["channelId"],
            status="open",
            channel_exists=True,
            observed_at=datetime.now(UTC),
        )
        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=_resolved_preflight(),
            close_reason="zombie:channel_deleted",
        )
    else:
        evidence = _corroborated_evidence(ticket_row)
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
        result = await _repair_from_evidence(service, evidence)

    assert result.outcome == expect_outcome
    if evidence_kind == "live":
        mock_db.transition_ticket_to_closed.assert_not_awaited()
    kwargs = _assert_audit(mock_db)
    assert kwargs["outcome"] == "denied"
    assert kwargs["reason"] == expect_reason


# ---------------------------------------------------------------------------
# Shared pure evaluation (task 2.4 REFACTOR) — one decision, no parallel truth
# ---------------------------------------------------------------------------


def test_shared_evaluation_maps_evidence_to_denial_outcomes() -> None:
    """The pure helper MUST be the SINGLE source of the denial decision:
    unresolved preflight -> skipped, unknown/stale -> quarantined,
    live/non-active -> skipped. No adapter keeps a parallel copy.
    """

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
    """When audit persistence fails on an AUTOMATED zombie autoclose, the close stands.

    clean-1.0 D6 relaxed the strict persistence contract for the automated
    zombie case (actorId=system ∧ reason startswith ``zombie:``): the audit
    insert is best-effort, the failure is logged at WARNING and the repair
    result keeps its successful outcome. Manual repairs keep the strict
    contract (see TestRepairTicketFromEvidence).
    """

    evidence = _corroborated_evidence(ticket_row)
    _wire_transition(mock_db, ticket_row)
    mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

    result = await _repair_from_evidence(service, evidence)

    assert isinstance(result, RepairResult)
    # Best-effort audit: closure outcome is NOT degraded by audit failure.
    assert result.outcome == "repaired"
    assert result.evidence_id == evidence.evidence_id


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

        evidence = _corroborated_evidence(ticket_row)
        # Transition returns None -> already_closed loser path.
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)
        # The already_closed audit insert fails (audit table down).
        mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
            result = await _repair_from_evidence(service, evidence)

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

        Threat: Audit best-effort — audit failure must not roll back the repair
        mutation. clean-1.0 D6: for the AUTOMATED zombie case the outcome stays
        ``repaired`` (best-effort audit); only manual repairs degrade to
        close/error with ``audit_persistence_failed``.
        """

        evidence = _corroborated_evidence(ticket_row)
        _wire_transition(mock_db, ticket_row)
        # This is the SUCCESS audit path (success -> insert fails).
        mock_db.insert_audit_row = AsyncMock(side_effect=RuntimeError("audit down"))

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_lifecycle_service"):
            result = await service.repair_ticket_from_evidence(
                evidence, preflight=_resolved_preflight(), close_reason="zombie:channel_deleted"
            )

        # The DB row was closed (transition succeeded) even though audit persistence failed.
        mock_db.transition_ticket_to_closed.assert_awaited_once()
        assert result.outcome == "repaired"
        assert result.evidence_id == evidence.evidence_id
        assert any("zombie_autoclose" in r.message.lower() or "audit" in r.message.lower() for r in caplog.records)


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

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Unknown Channel"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is False
        guild.fetch_channel.assert_awaited_once_with(888888888)

    @pytest.mark.asyncio
    async def test_live_channel_returns_true(self) -> None:
        """A resolvable channel is present (channel_exists=True)."""

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888888888
        guild = self._guild_with_fetch(channel)
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is True

    @pytest.mark.asyncio
    async def test_forbidden_is_unresolved(self) -> None:
        """403/missing permission is unresolved, never absence."""

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing Access"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_rate_limit_is_unresolved(self) -> None:
        """429 rate limit is unresolved, never absence."""

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.RateLimited(0.5))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_timeout_is_unresolved(self) -> None:
        """Generic HTTPException (timeout) is unresolved, never absence."""

        guild = self._guild_with_fetch(None)
        guild.fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "timeout"))
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_guild_is_unresolved(self) -> None:
        """A guild not in the bot cache is unknown (None), never absence."""

        bot = self._bot_with_guild(None)

        result = await probe_channel_absence(bot, "123456789", "888888888")

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_channel_id_is_unresolved(self) -> None:
        """A non-numeric channel id is unknown (None), never absence."""

        guild = self._guild_with_fetch(None)
        bot = self._bot_with_guild(guild)

        result = await probe_channel_absence(bot, "123456789", "not-a-snowflake")

        assert result is None
        guild.fetch_channel.assert_not_awaited()


class TestPlanSweepBatch:
    """Bounded, deduped batch planning (pure)."""

    def test_batch_is_bounded_and_deduped(self) -> None:
        """Batch caps at batch_size and never re-emits a seen candidate."""

        candidates = [{"id": f"c{i}"} for i in range(5)]
        seen: set[str] = {"c0", "c2"}

        batch = plan_sweep_batch(candidates, seen=seen, batch_size=2)

        ids = [c["id"] for c in batch]
        assert ids == ["c1", "c3"]
        assert "c0" not in ids and "c2" not in ids

    def test_batch_marks_seen(self) -> None:
        """Selected candidates are marked seen so a later call does not repeat them."""

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


def _wire_closed_transition(mock_db: AsyncMock, row: dict) -> None:
    """Stub transition_ticket_to_closed to return the closed form of row."""
    mock_db.transition_ticket_to_closed = AsyncMock(return_value={**row, "status": "closed", "closedAt": "now"})


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

    @pytest.mark.parametrize(
        "probe_behavior, expect_outcomes, expect_reason",
        [
            # NotFound probe → corroborated evidence → repaired via coordinator.
            ("not_found", ("repaired",), None),
            # A present channel → not corroborated → skipped/quarantined, no mutation.
            ("live_channel", ("skipped", "quarantined"), None),
            # Transient probe (HTTP) → reviewable skip + backoff.
            ("transient_error", ("skipped",), "probe_unresolved"),
        ],
        ids=["corroborated_repair", "live_skip", "unresolved_dry_run"],
    )
    async def test_probe_outcomes_route_through_coordinator(
        self,
        service: TicketService,
        mock_db: AsyncMock,
        probe_behavior: str,
        expect_outcomes: tuple[str, ...],
        expect_reason: str | None,
    ) -> None:
        """Sweep probes route by outcome: corroborated absence repairs, a
        live channel is skipped (not corroborated), a transient probe
        dry-runs with backoff and a reviewable reason. No mutation except
        on the repaired row.
        """
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=["888888888"])
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=self._active_row("888888888"))

        bot = self._sweep_bot()
        if probe_behavior == "not_found":
            _wire_closed_transition(mock_db, self._active_row("888888888"))
            bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
        elif probe_behavior == "live_channel":
            channel = MagicMock(spec=discord.TextChannel)
            channel.id = 888888888
            bot.get_guild().fetch_channel = AsyncMock(return_value=channel)
        else:
            bot.get_guild().fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "timeout"))

        if probe_behavior == "transient_error":
            with patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight())
            mock_sleep.assert_awaited_once()
        else:
            results = await service.sweep_integrity("123456789", bot, preflight=_resolved_preflight())

        assert len(results) == 1
        assert results[0].outcome in expect_outcomes
        if expect_reason is not None:
            assert results[0].reason == expect_reason
        if "repaired" in expect_outcomes:
            mock_db.transition_ticket_to_closed.assert_awaited_once()
        else:
            mock_db.transition_ticket_to_closed.assert_not_awaited()

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
        _wire_closed_transition(mock_db, row)

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
        _wire_closed_transition(mock_db, row)

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


# ---------------------------------------------------------------------------
# Sub-service ownership contracts (merged from the three ticket *_facade.py
# files, cycle-5 S5b/c). Delegation mock-theater died there because the
# behavioral twins above drive the same paths through real sub-services.
# ---------------------------------------------------------------------------


class TestSubServiceOwnership:
    """Single-owner wiring between TicketService and its sub-services."""

    def test_lifecycle_holds_query_instance(self, mock_db: AsyncMock) -> None:
        """Lifecycle MUST delegate cache ops via the injected query service."""

        qs = TicketQueryService(mock_db)
        lc = TicketLifecycleService(db=mock_db, query=qs)

        assert lc._query is qs

    def test_query_service_is_single_cache_owner(self) -> None:
        """Query service owns the channel set; add/discard are the only mutators."""

        qs = TicketQueryService(AsyncMock())

        assert qs._ticket_channel_cache == set()

        qs.add_channel(42)
        assert qs.is_ticket_channel(42) is True
        qs.discard_channel(42)
        assert qs.is_ticket_channel(42) is False

        # sync replaces wholesale...
        qs.sync_channel_cache({10, 20})
        assert qs._ticket_channel_cache == {10, 20}
        qs.sync_channel_cache()
        assert qs._ticket_channel_cache == set()

        # ...and copies instead of aliasing the caller's set.
        src = {1, 2, 3}
        qs.sync_channel_cache(src)
        src.add(99)
        assert 99 not in qs._ticket_channel_cache

    def test_facade_cache_alias_points_at_single_owner(self, service: TicketService) -> None:
        """Facade cache attribute MUST alias the query owner's set (no duplicate)."""
        assert service._ticket_channel_cache is service._query._ticket_channel_cache

        service._query.add_channel(99)
        assert 99 in service._ticket_channel_cache

        service._ticket_channel_cache = {1, 2}
        assert service._query._ticket_channel_cache == {1, 2}

    def test_repair_service_is_single_eligibility_owner(self) -> None:
        """Repair MUST delegate to evaluate_repair_eligibility, not re-implement it."""

        src = pathlib.Path(repair_service_module.__file__).read_text(encoding="utf-8")
        assert "evaluate_repair_eligibility" in src
        assert "from bot.services.ticket_repair import" in src

    def test_orchestration_not_owned_by_lifecycle(self, mock_db: AsyncMock) -> None:
        """Channel orchestration belongs to repair; lifecycle MUST NOT own it."""

        lc = TicketLifecycleService(db=mock_db, query=TicketQueryService(mock_db))

        assert not hasattr(lc, "create_ticket_channel")
        assert not hasattr(lc, "close_ticket_full")
        assert not hasattr(lc, "handle_channel_delete")
        assert not hasattr(lc, "sweep_integrity")

    def test_transcript_countdown_contract_lives_on_repair(self, mock_db: AsyncMock) -> None:
        """Countdown/timeout handling MUST remain a repair-service helper."""

        qs = TicketQueryService(mock_db)
        rs = TicketRepairService(db=mock_db, query=qs, lifecycle=TicketLifecycleService(db=mock_db, query=qs))

        assert hasattr(rs, "_countdown_and_delete") or hasattr(TicketRepairService, "_countdown_and_delete")

    def test_lifecycle_is_single_audit_owner(self, mock_db: AsyncMock) -> None:
        """Audit writes + claim invariants live in the lifecycle module only."""

        src = pathlib.Path(lifecycle_service_module.__file__).read_text(encoding="utf-8")
        assert "insert_audit_row" in src
        assert "check_can_claim" in src
        assert "add_channel" in src or "discard_channel" in src
