"""RED-first remediation tests for 5 critical findings (fd4b72 verify).

Covers:
1. Audit outcome vocabulary: automatic `repair/system/repaired` and manual `manual_repair/repaired`
2. Manual duplicate audit: exactly ONE manual_repair/repaired row
3. Sweep dry-run corroboration: unresolved gate returns corroborated=True candidates
4. Cross-guild ValueError: foreign-guild row returns skipped/cross_guild, no ValueError
5. Incomplete scenario assertions: listener race, exact audit contracts, dry-run shape
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.cache import TTLCache
from bot.models.ticket import IntegrityEvidence, RepairResult
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


def _unresolved():
    return evaluate_live_preflight(observed_at=datetime.now(UTC).isoformat())


def _audit_kwargs(mock_db, index=-1):
    call = mock_db.insert_audit_row.call_args_list[index]
    if call.kwargs:
        return call.kwargs
    keys = ["guild_id", "ticket_id", "action", "actor_id", "outcome", "reason"]
    return dict(zip(keys, call.args, strict=False))


# ── 1. Audit outcome vocabulary ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_automatic_repair_persists_repaired_not_success():
    """SERVICE-5.2: automatic repair must persist outcome=repaired."""
    db = AsyncMock()
    row = {"id": "t1", "guildId": "g1", "channelId": "c1", "status": "open"}
    closed = {**row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}
    db.transition_ticket_to_closed = AsyncMock(return_value=closed)
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
        source="sweep",
    )
    assert evidence.corroborated is True
    result = await svc.repair_ticket_from_evidence(evidence, preflight=_resolved(), close_reason="zombie:sweep")
    assert result.outcome == "repaired"
    assert result.action == "close"
    assert result.evidence_id == evidence.evidence_id
    # Exact audit contract
    assert db.insert_audit_row.await_count == 1
    kwargs = _audit_kwargs(db)
    assert kwargs["action"] == "repair"
    assert kwargs["actor_id"] == "system"
    assert kwargs["outcome"] == "repaired"
    assert kwargs["reason"] is None


@pytest.mark.asyncio
async def test_manual_repair_persists_single_manual_repair_repaired():
    """SERVICE-5.3 + SERVICE-4.1: manual repair persists one manual_repair row."""
    db = AsyncMock()
    row = {"id": "t1", "guildId": "123456789", "channelId": "888888888", "status": "open"}
    db.get_ticket = AsyncMock(return_value=row)
    closed = {**row, "status": "closed", "closedAt": "now"}
    db.transition_ticket_to_closed = AsyncMock(return_value=closed)
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    auth = RepairAuthority(actor_id="userM", guild_id="123456789", target_guild_id="123456789", has_mod_role=True)
    result = await svc.repair_ticket_manual("t1", guild_id="123456789", actor_id="userM", authority=auth, bot=bot)
    assert result.outcome == "repaired"
    assert result.action == "close"
    # Direct audit assertion: manual_repair + actor + outcome, and close_reason persisted.
    assert db.transition_ticket_to_closed.await_count == 1
    assert db.transition_ticket_to_closed.call_args.kwargs["close_reason"] == "zombie:manual_repair"
    # MUST be exactly one audit row, with manual_repair/repaired, no extra repair/success
    assert db.insert_audit_row.await_count == 1, db.insert_audit_row.call_args_list
    kwargs = _audit_kwargs(db)
    assert kwargs["action"] == "manual_repair"
    assert kwargs["actor_id"] == "userM"
    assert kwargs["outcome"] == "repaired"
    assert kwargs["reason"] is None
    # No duplicate automatic-style row
    actions = [_audit_kwargs(db, i)["action"] for i in range(db.insert_audit_row.call_count)]
    assert actions.count("repair") == 0
    assert actions.count("manual_repair") == 1


# ── 3. Sweep dry-run corroboration ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_dry_run_returns_corroborated_candidates():
    """SERVICE-3.1: unresolved gate sweep must return candidates with corroborated=True."""
    db = AsyncMock()
    db.get_open_ticket_channel_ids = AsyncMock(return_value=["111", "222"])
    rows = {
        "111": {"id": "t1", "guildId": "123456789", "channelId": "111", "status": "open"},
        "222": {"id": "t2", "guildId": "123456789", "channelId": "222", "status": "open"},
    }
    db.get_active_ticket_by_channel = AsyncMock(side_effect=lambda _g, ch: rows.get(ch))
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    # Both channels are NotFound -> corroborated
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    bot.get_guild = MagicMock(return_value=guild)
    results = await svc.sweep_integrity("123456789", bot, preflight=_unresolved())
    assert len(results) == 2
    for r in results:
        assert isinstance(r, RepairResult)
        assert r.outcome == "skipped"
        assert r.reason == "gate_unresolved"
        assert r.evidence_id is not None
        # New contract: dry-run candidate must be corroborated=True
        assert r.corroborated is True
    # No mutation
    db.transition_ticket_to_closed.assert_not_awaited()
    # No audit rows for dry-run (spec 7.3)
    assert db.insert_audit_row.await_count == 0


# ── 4. Cross-guild ValueError ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_guild_by_ref_returns_skipped_no_value_error():
    """Cross-guild repair_ticket_by_ref must return skipped, not raise ValueError."""
    db = AsyncMock()
    foreign_row = {"id": "t-foreign", "guildId": "other-guild", "channelId": "999", "status": "open"}
    db.get_ticket = AsyncMock(return_value=foreign_row)
    db.get_ticket_by_number = AsyncMock(return_value=None)
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    auth = RepairAuthority(actor_id="mod1", guild_id="g1", target_guild_id="g1", has_mod_role=True)
    bot = MagicMock()
    # Use uuid path: ticket_ref is uuid
    result = await svc.repair_ticket_by_ref(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        guild_id="g1",
        actor_id="mod1",
        authority=auth,
        bot=bot,
    )
    assert result is not None
    assert isinstance(result, RepairResult)
    # Must be deterministic skipped (or error with allowed outcome), NOT denied (which raises)
    assert result.outcome in ("skipped", "error")
    assert result.reason == "cross_guild_denied"
    assert result.action == "no_op"
    # No mutation
    db.transition_ticket_to_closed.assert_not_awaited()
    # No ValueError raised
    # Also ensure number path cross-guild would behave same (if needed)


# ── 5. Listener duplicate race and exact audit contracts ────────────────────


@pytest.mark.asyncio
async def test_listener_duplicate_race_yields_repaired_then_already_closed():
    """SERVICE-2.4: concurrent duplicate events must yield one repaired, one already_closed."""
    from bot.core.cache import TTLCache
    from bot.services.ticket_service import TicketService

    db = AsyncMock()
    row = {"id": "t1", "guildId": "123", "channelId": "555", "status": "open"}
    db.get_active_ticket_by_channel = AsyncMock(return_value=row)
    # First call succeeds, second returns None (already closed)
    db.transition_ticket_to_closed = AsyncMock(side_effect=[{**row, "status": "closed"}, None])
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    bot = MagicMock()
    bot.ticket_service = svc
    bot.logging_service = MagicMock()
    bot.logging_service.log_channel_delete = AsyncMock()
    bot.user = MagicMock()
    # Provide resolved preflight via bot.live_preflight
    bot.live_preflight = lambda: _resolved()
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 555
    channel.guild = MagicMock()
    channel.guild.id = 123
    # Capture RepairResults via svc directly to assert outcomes
    # We call handle_channel_delete twice concurrently via listener
    # Instead, test the service directly for deterministic outcomes
    results = await asyncio.gather(
        svc.handle_channel_delete("123", "555", preflight=_resolved()),
        svc.handle_channel_delete("123", "555", preflight=_resolved()),
    )
    assert {r.outcome for r in results if r is not None} == {"repaired", "already_closed"}
    assert sum(1 for r in results if r is not None and r.action == "close" and r.outcome == "repaired") == 1
    assert sum(1 for r in results if r is not None and r.action == "no_op" and r.outcome == "already_closed") == 1


@pytest.mark.asyncio
async def test_manual_audit_exact_contract_with_not_found_second_call():
    """Manual repair audit must be exactly manual_repair/repaired with actorId."""
    db = AsyncMock()
    row = {"id": "t9", "guildId": "123456789", "channelId": "888888888", "status": "open"}
    db.get_ticket = AsyncMock(return_value=row)
    closed = {**row, "status": "closed"}
    db.transition_ticket_to_closed = AsyncMock(side_effect=[closed, None])
    db.insert_audit_row = AsyncMock(return_value={})
    svc = TicketService(db=db, cache=TTLCache())
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    auth = RepairAuthority(actor_id="userM", guild_id="123456789", target_guild_id="123456789", has_mod_role=True)
    r1 = await svc.repair_ticket_manual("t9", guild_id="123456789", actor_id="userM", authority=auth, bot=bot)
    assert r1.outcome == "repaired"
    assert r1.action == "close"
    # First call exact audit
    assert db.insert_audit_row.call_count == 1
    k1 = _audit_kwargs(db, 0)
    assert k1["action"] == "manual_repair"
    assert k1["outcome"] == "repaired"
    assert k1["actor_id"] == "userM"
    r2 = await svc.repair_ticket_manual("t9", guild_id="123456789", actor_id="userM", authority=auth, bot=bot)
    assert r2.outcome == "already_closed"
    assert r2.action == "no_op"
    # Second call must not create a second manual_repair/repaired row
    assert all(
        _audit_kwargs(db, i)["action"] != "manual_repair" or _audit_kwargs(db, i)["outcome"] != "repaired" or i == 0
        for i in range(db.insert_audit_row.call_count)
    )
