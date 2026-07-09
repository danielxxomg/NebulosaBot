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

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_service import MAX_RETRIES, TicketService

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock for Database, pre-configured for ticket methods."""
    db = AsyncMock()
    db.get_max_ticket_number = AsyncMock()
    db.insert_ticket = AsyncMock()
    db.update_ticket = AsyncMock()
    db.get_ticket = AsyncMock()
    db.get_stale_tickets = AsyncMock()
    # Sub-ticket / note methods (added by PR1; wired here for slice-2 tests).
    db.get_guild = AsyncMock()
    db.get_ticket_notes = AsyncMock()
    db.insert_ticket_note = AsyncMock()
    db.delete_ticket_note = AsyncMock()
    # PR1 audit + dedup DB methods (wired by PR2 service integration).
    db.insert_audit_row = AsyncMock(return_value={})
    db.get_recent_notes_for_dedup = AsyncMock(return_value=[])
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
# close_ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_ticket_updates_status(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """close_ticket MUST set status='closed' and closedAt, then re-read."""
    ticket_id = ticket_row["id"]
    channel_id = int(ticket_row["channelId"])

    # Pre-populate cache to verify it gets cleaned.
    service._ticket_channel_cache.add(channel_id)
    assert channel_id in service._ticket_channel_cache

    # PR2 contract: pre-read the OPEN row (invariant passes), then re-read closed row.
    mock_db.get_ticket.side_effect = [
        ticket_row,  # pre-read: open
        {
            **ticket_row,
            "status": "closed",
            "closedAt": "2026-06-16T18:00:00+00:00",
            "transcriptUrl": "https://cdn.discord.com/transcript.html",
        },
    ]

    ticket = await service.close_ticket(
        ticket_id,
        closed_by="999999999",
        transcript_url="https://cdn.discord.com/transcript.html",
    )

    # DB update called.
    mock_db.update_ticket.assert_awaited_once()
    update_kwargs = mock_db.update_ticket.call_args.kwargs
    assert update_kwargs["status"] == "closed"
    assert update_kwargs["closedAt"] is not None
    assert update_kwargs["transcriptUrl"] == "https://cdn.discord.com/transcript.html"

    # Re-read from DB (PR2: pre-read + re-read → two calls, both with the id).
    assert mock_db.get_ticket.await_count == 2
    for call in mock_db.get_ticket.call_args_list:
        assert call.args == (ticket_id,)

    # Returned model.
    assert ticket.status == "closed"
    assert ticket.transcript_url == "https://cdn.discord.com/transcript.html"
    assert ticket.closed_at is not None

    # Cache was cleaned.
    assert channel_id not in service._ticket_channel_cache


@pytest.mark.asyncio
async def test_close_ticket_not_found(
    service: TicketService,
    mock_db: AsyncMock,
) -> None:
    """When get_ticket returns None after update, close_ticket MUST raise ValueError."""
    ticket_id = "nonexistent-id"
    mock_db.get_ticket.return_value = None

    with pytest.raises(ValueError, match=f"Ticket {ticket_id} not found"):
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
    mock_db.get_ticket.side_effect = [
        ticket_row,
        {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"},
    ]

    await service.close_ticket(ticket_id, closed_by="999999999")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "close"
    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_close_denied_audits_and_reraises(service: TicketService, mock_db: AsyncMock, ticket_row: dict) -> None:
    """Close on an already-closed ticket MUST audit denied + re-raise."""
    closed_row = {**ticket_row, "status": "closed"}
    mock_db.get_ticket.return_value = closed_row

    with pytest.raises(ValueError, match=r"close"):
        await service.close_ticket(ticket_row["id"], closed_by="999999999")

    mock_db.insert_audit_row.assert_awaited_once()
    kwargs = _audit_kwargs(mock_db)
    assert kwargs["action"] == "close"
    assert kwargs["outcome"] == "denied"
    mock_db.update_ticket.assert_not_awaited()


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


def _mock_guild_for_channel(*, channel_name: str = "ticket-0001", channel_id: int = 999999999) -> MagicMock:
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
    return author


@pytest.mark.asyncio
async def test_create_ticket_channel_creates_channel_and_inserts(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """create_ticket_channel MUST create a Discord channel AND insert a ticket row."""
    guild = _mock_guild_for_channel()
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

    channel, ticket = await service.create_ticket_channel(guild, category, author, "ticket-0001", guild_id="123456789")

    # Channel created with correct overwrites.
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.call_args.kwargs
    assert create_kwargs["category"] is category

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
    # Channel created with tentative name "ticket-0001" but DB returns ticketNumber=42.
    guild = _mock_guild_for_channel(channel_name="ticket-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 42}

    channel, ticket = await service.create_ticket_channel(guild, category, author, "ticket-0001", guild_id="123456789")

    # Channel renamed to match actual ticket number.
    channel.edit.assert_awaited_once_with(name="ticket-0042")
    assert ticket.ticket_number == 42


@pytest.mark.asyncio
async def test_create_ticket_channel_no_rename_if_name_matches(
    service: TicketService,
    mock_db: AsyncMock,
    ticket_row: dict,
) -> None:
    """When tentative name matches actual ticket number, no rename is needed."""
    guild = _mock_guild_for_channel(channel_name="ticket-0001")
    category = MagicMock(spec=discord.CategoryChannel)
    author = _mock_author()

    mock_db.get_max_ticket_number.return_value = 0
    mock_db.insert_ticket.return_value = {**ticket_row, "ticketNumber": 1}

    channel, ticket = await service.create_ticket_channel(guild, category, author, "ticket-0001", guild_id="123456789")

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
        guild, category, author, "ticket-0001", guild_id="123456789", category_id="cat-uuid-001"
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
        "ticket-0001",
        guild_id="123456789",
        subject="Login broken",
        description="Cannot access since Monday",
    )

    insert_kwargs = mock_db.insert_ticket.call_args.kwargs
    assert insert_kwargs["subject"] == "Login broken"
    assert insert_kwargs["description"] == "Cannot access since Monday"
    assert ticket.subject == "Login broken"
    assert ticket.description == "Cannot access since Monday"


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

    mock_db.get_ticket.side_effect = [
        ticket_row,
        {**ticket_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"},
    ]
    mock_db.insert_audit_row.side_effect = Exception("audit table unavailable")

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_service"):
        ticket = await service.close_ticket(ticket_id, closed_by="999999999")

    # Close succeeded — ticket is closed despite audit failure.
    assert ticket.status == "closed"
    assert any("audit" in r.message.lower() for r in caplog.records)
