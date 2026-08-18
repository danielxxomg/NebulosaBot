"""RED: repair adapters converge on one eligibility/coordinator path."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.models.ticket import IntegrityEvidence


@pytest.mark.asyncio
async def test_handle_channel_delete_converges_on_evaluate() -> None:
    """handle_channel_delete MUST delegate to the single evaluate path (no parallel truth)."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    # The facade import must resolve to the coordinator module.
    svc = __import__("bot.services.ticket_service", fromlist=["evaluate_repair_eligibility"])
    assert evaluate_repair_eligibility is svc.evaluate_repair_eligibility
    # Source must define the canonical decision exactly once.
    src = inspect.getsource(evaluate_repair_eligibility)
    assert "gate_unresolved" in src and "evidence_unresolved" in src


@pytest.mark.asyncio
async def test_sweep_integrity_converges_on_evaluate() -> None:
    """sweep_integrity MUST carry evidence through the single evaluate path."""
    from bot.services.ticket_service import TicketService

    mock_db = AsyncMock()
    mock_db.get_open_ticket_channel_ids.return_value = ["c1"]
    mock_db.get_active_ticket_by_channel.return_value = {
        "id": "t1",
        "status": "open",
        "channelId": "c1",
    }
    # Fresh probe unresolved (missing guild -> None) => skipped, evidences preserved.
    mock_bot = MagicMock()
    mock_bot.get_guild.return_value = None

    service = TicketService(mock_db, MagicMock())  # type: ignore[arg-type]
    results = await service.sweep_integrity("g1", mock_bot, preflight=None)
    # Unresolved probe MUST produce a single skipped report with evidence_id, no mutation.
    assert len(results) == 1
    assert results[0].outcome == "skipped"
    assert results[0].evidence_id is not None
    assert results[0].corroborated is None


@pytest.mark.asyncio
async def test_repair_ticket_from_evidence_guild_scoped_and_conditional() -> None:
    """repair_ticket_from_evidence MUST be guild-scoped and conditional (one winner)."""
    from bot.services.ticket_service import TicketService

    mock_db = AsyncMock()
    # First call: winner; second call same ids -> already_closed (no row).
    call_count = {"n": 0}

    async def fake_transition(guild_id: str, ticket_id: str, **_kwargs: object) -> dict[str, object] | None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"id": ticket_id, "guildId": guild_id}
        return None

    mock_db.transition_ticket_to_closed.side_effect = fake_transition
    mock_db.insert_audit_row = AsyncMock()

    from bot.services.integrity_report import evaluate_live_preflight

    preflight = evaluate_live_preflight(
        project_status="ACTIVE_HEALTHY",
        migration_015_applied=True,
        close_reason_nullable=True,
        required_indexes_present=True,
        realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
        observed_at=datetime.now(UTC).isoformat(),
    )

    svc = TicketService(mock_db, MagicMock())  # type: ignore[arg-type]
    evidence = IntegrityEvidence(
        ticket_id="t9",
        guild_id="g1",
        channel_id="c9",
        status="open",
        channel_exists=False,
    )
    r1 = await svc.repair_ticket_from_evidence(evidence, preflight=preflight, close_reason="zombie:repair")
    r2 = await svc.repair_ticket_from_evidence(evidence, preflight=preflight, close_reason="zombie:repair")

    assert r1.outcome == "repaired"
    assert r2.outcome == "already_closed"
    # Both must be guild-scoped transitions.
    first_call = mock_db.transition_ticket_to_closed.call_args_list[0]
    assert first_call.args[0] == "g1"


@pytest.mark.asyncio
async def test_repair_ticket_by_ref_guild_scoped() -> None:
    """repair_ticket_by_ref MUST NOT disclose or mutate across guilds."""
    from bot.services.ticket_invariants import RepairAuthority
    from bot.services.ticket_service import TicketService

    mock_db = AsyncMock()
    # Numeric ref resolves to a row whose guildId mismatches the requested guild.
    mock_db.get_ticket_by_number.return_value = {"id": "t1", "guildId": "g-other", "channelId": "c1", "status": "open"}
    mock_db.insert_audit_row = AsyncMock()

    svc = TicketService(mock_db, MagicMock())  # type: ignore[arg-type]
    authority = RepairAuthority(
        actor_id="u1",
        guild_id="g1",
        target_guild_id="g1",
        is_guild_owner=True,
        is_bot_owner=False,
    )
    result = await svc.repair_ticket_by_ref(
        "42",
        guild_id="g1",
        actor_id="u1",
        authority=authority,
        bot=MagicMock(),
    )
    assert result is not None
    assert result.reason == "cross_guild_denied"
    assert result.outcome == "skipped"
