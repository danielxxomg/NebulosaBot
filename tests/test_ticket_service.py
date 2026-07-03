"""Unit tests for bot.services.ticket_service.TicketService.

Covers:
    - Sequential numbering (MAX+1 normal path + retry on conflict)
    - create_ticket with mock DB insert + cache sync
    - close_ticket with status/closedAt updates
    - claim_ticket with status/claimedBy updates
    - get_stale_tickets query → Ticket model list
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import Ticket
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

    # Mock DB: update is a fire-and-forget, get returns updated row.
    mock_db.get_ticket.return_value = {
        **ticket_row,
        "status": "closed",
        "closedAt": "2026-06-16T18:00:00+00:00",
        "transcriptUrl": "https://cdn.discord.com/transcript.html",
    }

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

    # Re-read from DB.
    mock_db.get_ticket.assert_awaited_once_with(ticket_id)

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

    mock_db.get_ticket.return_value = {
        **ticket_row,
        "status": "claimed",
        "claimedBy": staff_id,
    }

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
