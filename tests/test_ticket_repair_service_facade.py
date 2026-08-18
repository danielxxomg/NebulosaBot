"""RED: TicketRepairService repair/channel/transcript ownership + facade delegates once (S3.3B)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import IntegrityEvidence, Ticket


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
    db.get_active_ticket_by_channel = AsyncMock(return_value=None)
    db.get_open_ticket_channel_ids = AsyncMock(return_value=[])
    db.get_ticket_by_number = AsyncMock(return_value=None)
    return db


def test_repair_service_exists_and_owns_methods(mock_db: AsyncMock) -> None:
    """TicketRepairService MUST exist and own repair + orchestration methods."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService
    from bot.services.ticket_repair_service import TicketRepairService

    qs = TicketQueryService(mock_db)
    lc = TicketLifecycleService(db=mock_db, query=qs)
    svc = TicketRepairService(db=mock_db, query=qs, lifecycle=lc)
    for name in (
        "repair_ticket_from_evidence",
        "handle_channel_delete",
        "sweep_integrity",
        "repair_ticket_by_ref",
        "repair_ticket_manual",
        "create_ticket_channel",
        "close_ticket_full",
    ):
        assert hasattr(svc, name), f"missing {name}"


def test_repair_service_single_eligibility_owner(mock_db: AsyncMock) -> None:
    """Repair MUST delegate to single evaluate_repair_eligibility, not duplicate gate."""
    import pathlib

    import bot.services.ticket_repair_service as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    assert "evaluate_repair_eligibility" in src
    # facade or repair service must not re-implement gate logic inline
    # (the coordinator is the single source; ensure import from ticket_repair)
    assert "from bot.services.ticket_repair import" in src


@pytest.mark.asyncio
async def test_facade_delegates_repair_ticket_from_evidence_once(mock_db: AsyncMock) -> None:
    """TicketService.repair_ticket_from_evidence MUST delegate exactly once to repair service."""
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.repair_ticket_from_evidence = AsyncMock(return_value=MagicMock())
    svc._repair = mock_repair  # type: ignore[attr-defined]
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
    )
    await svc.repair_ticket_from_evidence(evidence, preflight=None)
    mock_repair.repair_ticket_from_evidence.assert_awaited_once()
    mock_db.transition_ticket_to_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_handle_channel_delete_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.handle_channel_delete = AsyncMock(return_value=None)
    svc._repair = mock_repair  # type: ignore[attr-defined]
    await svc.handle_channel_delete(guild_id="g1", channel_id="c1", preflight=None)
    mock_repair.handle_channel_delete.assert_awaited_once_with(guild_id="g1", channel_id="c1", preflight=None)
    mock_db.get_active_ticket_by_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_sweep_integrity_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.sweep_integrity = AsyncMock(return_value=[])
    svc._repair = mock_repair  # type: ignore[attr-defined]
    bot = MagicMock()
    await svc.sweep_integrity(guild_id="g1", bot=bot, preflight=None)
    mock_repair.sweep_integrity.assert_awaited_once()
    mock_db.get_open_ticket_channel_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_repair_by_ref_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_invariants import RepairAuthority
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.repair_ticket_by_ref = AsyncMock(return_value=None)
    svc._repair = mock_repair  # type: ignore[attr-defined]
    authority = RepairAuthority(actor_id="u1", guild_id="g1", target_guild_id="g1", has_mod_role=True)
    bot = MagicMock()
    await svc.repair_ticket_by_ref(
        "42", guild_id="g1", actor_id="u1", authority=authority, bot=bot, preflight=None
    )
    mock_repair.repair_ticket_by_ref.assert_awaited_once()
    mock_db.get_ticket.assert_not_awaited()
    mock_db.get_ticket_by_number.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_repair_manual_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_invariants import RepairAuthority
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.repair_ticket_manual = AsyncMock(return_value=MagicMock())
    svc._repair = mock_repair  # type: ignore[attr-defined]
    authority = RepairAuthority(actor_id="u1", guild_id="g1", target_guild_id="g1", has_mod_role=True)
    bot = MagicMock()
    await svc.repair_ticket_manual(
        ticket_id="t1", guild_id="g1", actor_id="u1", authority=authority, bot=bot, preflight=None
    )
    mock_repair.repair_ticket_manual.assert_awaited_once()
    mock_db.get_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_create_ticket_channel_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.create_ticket_channel = AsyncMock(return_value=(MagicMock(), MagicMock(spec=Ticket)))
    svc._repair = mock_repair  # type: ignore[attr-defined]
    guild = MagicMock()
    category = MagicMock()
    author = MagicMock()
    author.id = 123
    author.display_name = "Test"
    await svc.create_ticket_channel(
        guild=guild,
        category=category,
        author=author,
        guild_id="g1",
        category_name="Support",
        category_id=None,
    )
    mock_repair.create_ticket_channel.assert_awaited_once()
    # facade must not directly create discord channels or call db
    mock_db.get_max_ticket_number.assert_not_awaited()


@pytest.mark.asyncio
async def test_facade_delegates_close_ticket_full_once(mock_db: AsyncMock) -> None:
    from bot.services.ticket_service import TicketService

    cache = TTLCache()
    svc = TicketService(db=mock_db, cache=cache)
    mock_repair = MagicMock()
    mock_repair.close_ticket_full = AsyncMock(return_value=None)
    svc._repair = mock_repair  # type: ignore[attr-defined]
    channel = MagicMock()
    ticket = MagicMock(spec=Ticket)
    ticket.id = "t1"
    bot = MagicMock()
    bot.transcript_service = None
    bot.guild_service = None
    await svc.close_ticket_full(channel=channel, ticket=ticket, closed_by="u1", bot=bot, manual=True)
    mock_repair.close_ticket_full.assert_awaited_once()
    mock_db.transition_ticket_to_closed.assert_not_awaited()


def test_orchestration_not_owned_by_lifecycle(mock_db: AsyncMock) -> None:
    """Lifecycle MUST NOT own orchestration — owned by repair service."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService

    qs = TicketQueryService(mock_db)
    lc = TicketLifecycleService(db=mock_db, query=qs)
    assert not hasattr(lc, "create_ticket_channel")
    assert not hasattr(lc, "close_ticket_full")
    assert not hasattr(lc, "handle_channel_delete")
    assert not hasattr(lc, "sweep_integrity")


def test_facade_preserves_transcript_countdown_contract(mock_db: AsyncMock) -> None:
    """Facade countdown contract must remain via repair service (timeout handling)."""
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService
    from bot.services.ticket_repair_service import TicketRepairService

    qs = TicketQueryService(mock_db)
    lc = TicketLifecycleService(db=mock_db, query=qs)
    rs = TicketRepairService(db=mock_db, query=qs, lifecycle=lc)
    # repair service must expose countdown helper (static or private)
    assert hasattr(rs, "_countdown_and_delete") or hasattr(TicketRepairService, "_countdown_and_delete")
