"""Missing runtime scenarios for 8-findings remediation (finding 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.cache import TTLCache
from bot.services.integrity_report import evaluate_live_preflight
from bot.services.ticket_invariants import RepairAuthority
from bot.services.ticket_service import TicketService


def _resolved():
    return evaluate_live_preflight(
        project_status="ACTIVE_HEALTHY",
        migration_015_applied=True,
        close_reason_nullable=True,
        required_indexes_present=True,
        realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
        observed_at=datetime.now(UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_manual_rerun_is_idempotent() -> None:
    db = AsyncMock()
    g1 = "123"
    row = {"id": "t1", "guildId": g1, "channelId": "888888888", "status": "open"}
    db.get_ticket = AsyncMock(return_value=row)
    db.transition_ticket_to_closed = AsyncMock(side_effect=[{**row, "status": "closed"}, None])
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    auth = RepairAuthority(actor_id="mod1", guild_id=g1, target_guild_id=g1, has_mod_role=True)
    r1 = await svc.repair_ticket_manual(
        "t1", guild_id=g1, actor_id="mod1", authority=auth, bot=bot, preflight=_resolved()
    )
    r2 = await svc.repair_ticket_manual(
        "t1", guild_id=g1, actor_id="mod1", authority=auth, bot=bot, preflight=_resolved()
    )
    assert r1.outcome == "repaired"
    assert r2.outcome == "already_closed"


@pytest.mark.asyncio
async def test_sweep_429_ratelimited_continues_with_backoff() -> None:
    db = AsyncMock()
    db.get_open_ticket_channel_ids = AsyncMock(return_value=["111111111", "222222222"])
    rows = {
        "111111111": {"id": "t1", "guildId": "123456789", "channelId": "111111111", "status": "open"},
        "222222222": {"id": "t2", "guildId": "123456789", "channelId": "222222222", "status": "open"},
    }
    db.get_active_ticket_by_channel = AsyncMock(side_effect=lambda _g, ch: rows.get(ch))
    db.transition_ticket_to_closed = AsyncMock(return_value={**rows["222222222"], "status": "closed"})
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789

    async def fetch_ch(cid: int):
        if cid == 111111111:
            raise discord.RateLimited(0.5)
        raise discord.NotFound(MagicMock(), "gone")

    guild.fetch_channel = AsyncMock(side_effect=fetch_ch)
    bot.get_guild = MagicMock(return_value=guild)
    with patch("bot.services.ticket_service.asyncio.sleep", new_callable=AsyncMock) as sleep:
        results = await svc.sweep_integrity("123456789", bot, preflight=_resolved())
    assert results[0].outcome == "skipped" and results[0].reason == "probe_unresolved"
    assert results[1].outcome == "repaired"
    assert sleep.await_count >= 1


@pytest.mark.asyncio
async def test_exact_close_reasons_and_audit_actions() -> None:
    db = AsyncMock()
    db.get_active_ticket_by_channel = AsyncMock(
        return_value={"id": "t1", "guildId": "123", "channelId": "555", "status": "open"}
    )
    db.transition_ticket_to_closed = AsyncMock(
        return_value={"id": "t1", "guildId": "123", "channelId": "555", "status": "closed"}
    )
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    await svc.handle_channel_delete("123", "555", preflight=_resolved())
    assert db.transition_ticket_to_closed.call_args.kwargs["close_reason"] == "zombie:channel_deleted"
    db2 = AsyncMock()
    db2.get_open_ticket_channel_ids = AsyncMock(return_value=["777777777"])
    db2.get_active_ticket_by_channel = AsyncMock(
        return_value={"id": "t1", "guildId": "123", "channelId": "777777777", "status": "open"}
    )
    db2.transition_ticket_to_closed = AsyncMock(
        return_value={"id": "t1", "guildId": "123", "channelId": "777777777", "status": "closed"}
    )
    db2.insert_audit_row = AsyncMock(return_value={})
    svc2 = TicketService(db=db2, cache=TTLCache())
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    bot.get_guild = MagicMock(return_value=guild)
    await svc2.sweep_integrity("123", bot, preflight=_resolved())
    assert db2.transition_ticket_to_closed.call_args.kwargs["close_reason"] == "zombie:sweep"
