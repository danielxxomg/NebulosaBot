"""RED: TicketQueryService query/cache ownership + facade delegates once (S3.3A)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import Ticket


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.get_stale_tickets = AsyncMock(return_value=[])
    return db


def test_query_service_is_single_cache_owner(mock_db: AsyncMock) -> None:
    """TicketQueryService MUST own the cache set and expose single-owner ops."""
    from bot.services.ticket_query_service import TicketQueryService

    qs = TicketQueryService(mock_db)

    # owner has the set
    assert hasattr(qs, "_ticket_channel_cache")
    assert qs._ticket_channel_cache == set()

    # add/discard are single mutation entry points
    qs.add_channel(42)
    assert qs.is_ticket_channel(42) is True
    qs.discard_channel(42)
    assert qs.is_ticket_channel(42) is False

    # sync replaces, clear works
    qs.sync_channel_cache({10, 20})
    assert qs._ticket_channel_cache == {10, 20}
    qs.sync_channel_cache()
    assert qs._ticket_channel_cache == set()
    # sync must copy, not alias
    src = {1, 2, 3}
    qs.sync_channel_cache(src)
    src.add(99)
    assert 99 not in qs._ticket_channel_cache


@pytest.mark.asyncio
async def test_query_service_get_stale_tickets_delegates_to_db(mock_db: AsyncMock) -> None:
    """get_stale_tickets MUST call db and return Ticket models."""
    from bot.services.ticket_query_service import TicketQueryService

    row = {
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "ticketNumber": 7,
        "guildId": "g1",
        "authorId": "u1",
        "channelId": "c1",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
    }
    mock_db.get_stale_tickets.return_value = [row]
    qs = TicketQueryService(mock_db)

    tickets = await qs.get_stale_tickets("g1", hours=72)

    mock_db.get_stale_tickets.assert_awaited_once_with("g1", hours=72)
    assert len(tickets) == 1
    assert isinstance(tickets[0], Ticket)
    assert tickets[0].guild_id == "g1"


@pytest.mark.asyncio
async def test_query_service_get_stale_tickets_empty(mock_db: AsyncMock) -> None:
    """Empty stale result MUST return empty list."""
    from bot.services.ticket_query_service import TicketQueryService

    mock_db.get_stale_tickets.return_value = []
    qs = TicketQueryService(mock_db)
    assert await qs.get_stale_tickets("g1") == []


@pytest.mark.asyncio
async def test_facade_delegates_get_stale_tickets_once(mock_db: AsyncMock) -> None:
    """TicketService facade MUST delegate get_stale_tickets exactly once to query service."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)

    # Replace the owned query service with a mock to count delegations
    mock_qs = MagicMock()
    mock_qs.get_stale_tickets = AsyncMock(return_value=[])
    # keep real cache set for other assertions
    mock_qs._ticket_channel_cache = set()
    svc._query = mock_qs

    await svc.get_stale_tickets("g1", hours=48)

    mock_qs.get_stale_tickets.assert_awaited_once_with("g1", hours=48)
    # facade must not touch db directly for this path
    mock_db.get_stale_tickets.assert_not_awaited()


def test_facade_delegates_is_ticket_channel_once(mock_db: AsyncMock) -> None:
    """is_ticket_channel MUST delegate once; facade MUST NOT duplicate set."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_qs = MagicMock()
    mock_qs.is_ticket_channel = MagicMock(return_value=True)
    mock_qs._ticket_channel_cache = {42}
    svc._query = mock_qs

    assert svc.is_ticket_channel(42) is True
    mock_qs.is_ticket_channel.assert_called_once_with(42)


def test_facade_delegates_sync_channel_cache_once(mock_db: AsyncMock) -> None:
    """sync_channel_cache MUST delegate once; single owner."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_qs = MagicMock()
    mock_qs.sync_channel_cache = MagicMock()
    mock_qs._ticket_channel_cache = set()
    svc._query = mock_qs

    svc.sync_channel_cache({10, 20})
    mock_qs.sync_channel_cache.assert_called_once_with({10, 20})
    svc.sync_channel_cache()
    assert mock_qs.sync_channel_cache.call_count == 2
    assert mock_qs.sync_channel_cache.call_args_list[1].args == (None,)
    # explicit None also allowed
    svc.sync_channel_cache(None)
    assert mock_qs.sync_channel_cache.call_count == 3


def test_facade_cache_property_is_alias_to_query_owner(mock_db: AsyncMock) -> None:
    """Facade's _ticket_channel_cache MUST be alias to query's set (no duplicate)."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)

    # facade exposes alias to single owner
    assert svc._ticket_channel_cache is svc._query._ticket_channel_cache

    svc._query.add_channel(99)
    assert 99 in svc._ticket_channel_cache
    assert svc.is_ticket_channel(99) is True

    # facade setter aliases too
    svc._ticket_channel_cache = {1, 2}
    assert svc._query._ticket_channel_cache == {1, 2}


@pytest.mark.asyncio
async def test_facade_create_close_use_single_owner_not_direct_set(mock_db: AsyncMock) -> None:
    """create_ticket/close_ticket MUST mutate via query owner, not direct set."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)

    # Spy on the single owner via wrap
    orig_add = svc._query.add_channel
    orig_discard = svc._query.discard_channel

    calls_add: list[int] = []
    calls_discard: list[int] = []

    def spy_add(cid: int) -> None:
        calls_add.append(cid)
        orig_add(cid)

    def spy_discard(cid: int) -> None:
        calls_discard.append(cid)
        orig_discard(cid)

    svc._query.add_channel = spy_add  # type: ignore[attr-defined,method-assign]
    svc._query.discard_channel = spy_discard  # type: ignore[attr-defined,method-assign]
    try:
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)
        mock_db.count_user_open_tickets_in_category = AsyncMock(return_value=0)
        mock_db.insert_ticket = AsyncMock(
            return_value={
                "id": "t1",
                "ticketNumber": 1,
                "guildId": "g1",
                "authorId": "u1",
                "channelId": "123",
                "categoryId": None,
                "status": "open",
                "claimedBy": None,
                "transcriptUrl": None,
                "createdAt": "2026-01-15T10:00:00+00:00",
                "closedAt": None,
                "lastActivity": "2026-01-15T10:00:00+00:00",
            }
        )
        await svc.create_ticket(guild_id="g1", author_id="u1", category_id=None, channel_id="123")
        assert len(calls_add) >= 1

        mock_db.get_ticket = AsyncMock(return_value={"guildId": "g1", "channelId": "123"})
        mock_db.transition_ticket_to_closed = AsyncMock(
            return_value={
                "id": "t1",
                "ticketNumber": 1,
                "guildId": "g1",
                "authorId": "u1",
                "channelId": "123",
                "categoryId": None,
                "status": "closed",
                "claimedBy": None,
                "transcriptUrl": None,
                "createdAt": "2026-01-15T10:00:00+00:00",
                "closedAt": "2026-06-16T18:00:00+00:00",
                "lastActivity": "2026-06-16T18:00:00+00:00",
            }
        )
        mock_db.insert_audit_row = AsyncMock(return_value={})
        await svc.close_ticket("t1", closed_by="u1")
        assert len(calls_discard) >= 1
    finally:
        svc._query.add_channel = orig_add  # type: ignore[attr-defined,method-assign]
        svc._query.discard_channel = orig_discard  # type: ignore[attr-defined,method-assign]
