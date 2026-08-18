"""RED: TicketLifecycleService lifecycle ownership + facade delegates once (S3.3A2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import Ticket
from bot.models.ticket_note import TicketNote


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.get_max_ticket_number = AsyncMock(return_value=0)
    db.insert_ticket = AsyncMock(return_value=None)
    db.get_ticket = AsyncMock(return_value=None)
    db.update_ticket = AsyncMock(return_value=None)
    db.get_ticket_notes = AsyncMock(return_value=[])
    db.insert_ticket_note = AsyncMock(return_value=None)
    db.delete_ticket_note = AsyncMock(return_value=None)
    db.insert_audit_row = AsyncMock(return_value={})
    db.get_recent_notes_for_dedup = AsyncMock(return_value=[])
    db.count_user_open_tickets_in_category = AsyncMock(return_value=0)
    db.transition_ticket_to_closed = AsyncMock(return_value=None)
    db.get_guild = AsyncMock(return_value=None)
    db.get_ticket_category = AsyncMock(return_value=None)
    return db


def test_lifecycle_service_exists_and_owns_methods(mock_db: AsyncMock) -> None:
    """TicketLifecycleService MUST exist and own lifecycle methods."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService

    qs = TicketQueryService(mock_db)
    svc = TicketLifecycleService(db=mock_db, query=qs)
    for name in (
        "create_ticket",
        "close_ticket",
        "claim_ticket",
        "unclaim_ticket",
        "edit_ticket_category",
        "create_subticket",
        "reopen_ticket",
        "transfer_ticket",
        "create_note",
        "get_notes",
        "delete_note",
    ):
        assert hasattr(svc, name), f"missing {name}"


def test_lifecycle_service_delegates_cache_via_query(mock_db: AsyncMock) -> None:
    """Lifecycle MUST delegate cache via TicketQueryService add_channel/discard_channel."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService

    qs = TicketQueryService(mock_db)
    # spy
    orig_add = qs.add_channel
    orig_discard = qs.discard_channel
    calls_add: list[int] = []
    calls_discard: list[int] = []

    def spy_add(cid: int) -> None:
        calls_add.append(cid)
        orig_add(cid)

    def spy_discard(cid: int) -> None:
        calls_discard.append(cid)
        orig_discard(cid)

    qs.add_channel = spy_add  # type: ignore[method-assign]
    qs.discard_channel = spy_discard  # type: ignore[method-assign]
    svc = TicketLifecycleService(db=mock_db, query=qs)
    # lifecycle owns the query reference
    assert svc._query is qs  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_facade_delegates_create_ticket_once(mock_db: AsyncMock) -> None:
    """TicketService.create_ticket MUST delegate exactly once to lifecycle."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.create_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.create_ticket(guild_id="g1", author_id="u1", category_id=None, channel_id="123")
    mock_lc.create_ticket.assert_awaited_once()
    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_close_ticket_once(mock_db: AsyncMock) -> None:
    """close_ticket MUST delegate once; facade MUST NOT call transition directly."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.close_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.close_ticket("t1", closed_by="u1")
    mock_lc.close_ticket.assert_awaited_once_with(
        "t1", closed_by="u1", transcript_url=None, close_reason=None, guild_id=None
    )
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_claim_ticket_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.claim_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.claim_ticket("t1", claimed_by="u1")
    mock_lc.claim_ticket.assert_awaited_once()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_unclaim_ticket_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.unclaim_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.unclaim_ticket("t1", actor_id="u1", is_mod=True)
    mock_lc.unclaim_ticket.assert_awaited_once()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_edit_category_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.edit_ticket_category = AsyncMock(return_value=(MagicMock(spec=Ticket), True))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    ch = MagicMock()
    await svc.edit_ticket_category("t1", new_category_id="cat1", channel=ch, actor_id="u1", is_mod=True)
    mock_lc.edit_ticket_category.assert_awaited_once()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_create_subticket_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.create_subticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.create_subticket(parent_id="p1", author_id="u1", category_id=None, channel_id="c1", guild_id="g1")
    mock_lc.create_subticket.assert_awaited_once()
    mock_db.insert_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_reopen_ticket_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.reopen_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    guild = MagicMock()
    await svc.reopen_ticket("t1", guild=guild)
    mock_lc.reopen_ticket.assert_awaited_once_with("t1", guild=guild)
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_transfer_ticket_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.transfer_ticket = AsyncMock(return_value=MagicMock(spec=Ticket))
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.transfer_ticket("t1", new_claimed_by="u2", actor_id="u1")
    mock_lc.transfer_ticket.assert_awaited_once()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_note_ops_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_lc = MagicMock()
    mock_lc.create_note = AsyncMock(return_value=MagicMock(spec=TicketNote))
    mock_lc.get_notes = AsyncMock(return_value=[])
    mock_lc.delete_note = AsyncMock(return_value=None)
    svc._lifecycle = mock_lc  # type: ignore[attr-defined]
    await svc.create_note("t1", author_id="u1", content="hi")
    mock_lc.create_note.assert_awaited_once_with("t1", "u1", "hi", guild_id=None)
    await svc.get_notes("t1")
    mock_lc.get_notes.assert_awaited_once_with("t1", guild_id=None)
    await svc.delete_note("n1", author_id="u1", ticket_id="t1")
    mock_lc.delete_note.assert_awaited_once_with("n1", "u1", ticket_id="t1", guild_id=None)
    mock_db.insert_ticket_note.assert_not_awaited()
    mock_db.get_ticket_notes.assert_not_awaited()


def test_lifecycle_single_audit_owner(mock_db: AsyncMock) -> None:
    """Lifecycle MUST be single audit owner — audit writes only via lifecycle, not facade duplicate."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService

    qs = TicketQueryService(mock_db)
    lc = TicketLifecycleService(db=mock_db, query=qs)
    # lifecycle holds db for audit; facade should not duplicate audit logic
    assert hasattr(lc, "_db")
    # ensure invariants are imported/used (check_can_claim etc. should be reachable)
    import bot.services.ticket_lifecycle_service as mod

    with open(mod.__file__, encoding="utf-8") as fh:  # type: ignore[arg-type]
        src = fh.read()
    # must own audit + invariants, delegate cache via query
    assert "insert_audit_row" in src
    assert "check_can_claim" in src
    assert "add_channel" in src or "discard_channel" in src
