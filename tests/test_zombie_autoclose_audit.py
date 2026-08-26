"""Zombie auto-close audit (ticket-service delta — D6).

When ANY automatic path closes a zombie ticket, a best-effort
``ticket_audit`` row MUST be written:

- ``action="zombie_autoclose"``
- ``actorId="system"``
- applied close reason verbatim (e.g. ``zombie:sweep``)
- outcome

The insert is BEST-EFFORT: failure MUST NOT abort or roll back the close;
the failure is logged at WARNING and the close stands. Manual repairs keep
the strict audit-persistence contract unchanged.

Ref: clean-1.0 S0.3/S0.4 — "Zombie auto-close writes an audit entry".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.models.ticket import IntegrityEvidence
from bot.services.integrity_report import evaluate_live_preflight
from bot.services.ticket_lifecycle_service import TicketLifecycleService
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService


def _preflight() -> object:
    return evaluate_live_preflight(
        project_status="ACTIVE_HEALTHY",
        migration_015_applied=True,
        close_reason_nullable=True,
        required_indexes_present=True,
        realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
        observed_at=datetime.now(UTC).isoformat(),
    )


def _zombie_evidence(ticket_id: str = "t1", guild_id: str = "g1") -> IntegrityEvidence:
    return IntegrityEvidence(
        ticket_id=ticket_id,
        guild_id=guild_id,
        channel_id="c1",
        status="open",
        channel_exists=False,
        source="sweep",
    )


_CLOSED_ROW = {
    "id": "t1",
    "ticketNumber": 1,
    "guildId": "g1",
    "authorId": "u1",
    "channelId": "12345",
    "status": "closed",
    "createdAt": "2026-08-01T00:00:00+00:00",
    "lastActivity": "2026-08-01T00:00:00+00:00",
}


def _make_db(closed_row: dict | None = None) -> AsyncMock:
    db = AsyncMock()
    db.transition_ticket_to_closed.return_value = closed_row or dict(_CLOSED_ROW)
    db.insert_audit_row = AsyncMock()
    return db


def _audit_calls(db: AsyncMock) -> list[tuple]:
    """Return (action, actor_id, outcome, reason) tuples of audit inserts."""
    calls = []
    for call in db.insert_audit_row.call_args_list:
        args = call.args
        # Signature: (guild_id, ticket_id, action, actor_id, outcome, reason)
        calls.append((args[2], args[3], args[4], args[5]))
    return calls


# ===========================================================================
# Repair seam — sweep path (single seam per D6)
# ===========================================================================


class TestSweepClosedZombieAudit:
    """The integrity-sweep closure writes one zombie_autoclose audit row."""

    @pytest.mark.asyncio
    async def test_sweep_closure_writes_zombie_autoclose_row(self) -> None:
        """GIVEN a corroborated zombie closed by the sweep THEN the audit row exists."""
        db = _make_db()
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)
        repair = TicketRepairService(db, query, lifecycle)

        result = await repair.repair_ticket_from_evidence(
            _zombie_evidence(),
            preflight=_preflight(),
            close_reason="zombie:sweep",
            actor_id="system",
        )

        assert result.outcome == "repaired"
        actions = [(action, actor) for action, actor, _outcome, _reason in _audit_calls(db)]
        assert ("zombie_autoclose", "system") in actions, (
            f"expected zombie_autoclose audit by system, got: {actions}"
        )
        rows = [row for row in _audit_calls(db) if row[0] == "zombie_autoclose"]
        assert rows[0][3] == "zombie:sweep", "applied close reason MUST be stored verbatim"
        # The generic repair row is REPLACED for automated zombies, not duplicated.
        assert all(action != "repair" for action, _actor, _o, _r in _audit_calls(db))

    @pytest.mark.asyncio
    async def test_full_sweep_path_writes_audit(self) -> None:
        """End-to-end sweep_integrity → closure carries the same audit row."""
        db = _make_db()
        db.get_open_ticket_channel_ids.return_value = ["c1"]
        db.get_active_ticket_by_channel.return_value = {
            "id": "t1",
            "status": "open",
            "channelId": "c1",
        }
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)
        repair = TicketRepairService(db, query, lifecycle)
        bot = MagicMock()

        with patch("bot.services.ticket_repair_service.probe_channel_absence", new=AsyncMock(return_value=False)):
            results = await repair.sweep_integrity("g1", bot, preflight=_preflight())

        assert len(results) == 1 and results[0].outcome == "repaired"
        rows = [row for row in _audit_calls(db) if row[0] == "zombie_autoclose"]
        assert rows, f"sweep closure must write zombie_autoclose audit; got {_audit_calls(db)}"
        assert rows[0] == ("zombie_autoclose", "system", "repaired", "zombie:sweep")


class TestChannelDeletePathAudit:
    """The authoritative channel-delete repair writes the same audit row."""

    @pytest.mark.asyncio
    async def test_channel_delete_closure_writes_zombie_autoclose_row(self) -> None:
        db = _make_db()
        db.get_active_ticket_by_channel.return_value = {
            "id": "t1",
            "status": "claimed",
            "channelId": "c1",
        }
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)
        repair = TicketRepairService(db, query, lifecycle)

        result = await repair.handle_channel_delete("g1", "c1", preflight=_preflight())

        assert result is not None and result.outcome == "repaired"
        rows = [row for row in _audit_calls(db) if row[0] == "zombie_autoclose"]
        assert rows == [("zombie_autoclose", "system", "repaired", "zombie:channel_deleted")], (
            f"channel-delete path must write the shared zombie_autoclose row; got {_audit_calls(db)}"
        )


# ===========================================================================
# Lifecycle seam — scheduled-close loop closes with reason zombie:*
# ===========================================================================


class TestLifecycleSeamZombieClose:
    """close_ticket with a zombie:* reason writes zombie_autoclose, not 'close'."""

    @pytest.mark.asyncio
    async def test_zombie_close_writes_zombie_autoclose_row(self) -> None:
        db = _make_db()
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)

        await lifecycle.close_ticket("t1", closed_by="auto:scheduled", close_reason="zombie:channel_missing", guild_id="g1")

        rows = _audit_calls(db)
        assert ("zombie_autoclose", "system", "success", "zombie:channel_missing") in rows, (
            f"is_zombie close MUST write zombie_autoclose with verbatim reason; got {rows}"
        )
        assert all(action != "close" for action, *_rest in rows), (
            f"generic close row must be replaced for zombie closes; got {rows}"
        )

    @pytest.mark.asyncio
    async def test_non_zombie_close_keeps_generic_close_row(self) -> None:
        """Guard: manual/scheduled non-zombie closes are unchanged."""
        db = _make_db()
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)

        await lifecycle.close_ticket("t1", closed_by="mod-9", close_reason=None, guild_id="g1")

        rows = _audit_calls(db)
        assert ("close", "mod-9", "success", None) in rows
        assert all(action != "zombie_autoclose" for action, *_rest in rows)


# ===========================================================================
# Best-effort guarantee — audit failure never blocks the close
# ===========================================================================


class TestAuditFailureBestEffort:
    """Automated zombie case relaxes strict persistence; manual keeps it."""

    @pytest.mark.asyncio
    async def test_repair_seam_audit_failure_keeps_close_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        db = _make_db()
        db.insert_audit_row.side_effect = RuntimeError("db down")
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)
        repair = TicketRepairService(db, query, lifecycle)

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_repair_service"):
            result = await repair.repair_ticket_from_evidence(
                _zombie_evidence(),
                preflight=_preflight(),
                close_reason="zombie:sweep",
                actor_id="system",
            )

        # Close stands: no exception propagated, outcome stays repaired.
        assert result.outcome == "repaired"
        assert any(rec.levelno == logging.WARNING for rec in caplog.records), (
            "audit-insert failure MUST be logged at WARNING"
        )

    @pytest.mark.asyncio
    async def test_lifecycle_seam_audit_failure_keeps_close(self, caplog: pytest.LogCaptureFixture) -> None:
        db = _make_db()
        db.insert_audit_row.side_effect = RuntimeError("db down")
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)

        with caplog.at_level(logging.WARNING, logger="bot.services.ticket_lifecycle_service"):
            ticket = await lifecycle.close_ticket(
                "t1", closed_by="auto:scheduled", close_reason="zombie:sweep", guild_id="g1"
            )

        assert ticket.id == "t1", "closure MUST stand when the best-effort audit insert fails"

    @pytest.mark.asyncio
    async def test_manual_repair_keeps_strict_contract(self) -> None:
        """Manual repairs still hard-fail on audit-persistence failure."""
        db = _make_db()
        db.insert_audit_row.side_effect = RuntimeError("db down")
        query = MagicMock(spec=TicketQueryService)
        lifecycle = TicketLifecycleService(db, query)
        repair = TicketRepairService(db, query, lifecycle)

        result = await repair.repair_ticket_from_evidence(
            _zombie_evidence(),
            preflight=_preflight(),
            close_reason="zombie:manual_repair",
            actor_id="mod-123",
        )

        assert result.outcome == "error"
        assert result.reason == "audit_persistence_failed"


# ===========================================================================
# Helper contract — single audit method on the lifecycle service
# ===========================================================================


class TestAuditHelperContract:
    """_audit_zombie_autoclose lives on TicketLifecycleService (D6 single site)."""

    def test_helper_exists_on_lifecycle_service(self) -> None:
        assert hasattr(TicketLifecycleService, "_audit_zombie_autoclose"), (
            "D6 requires ONE audit method on TicketLifecycleService used by both seams"
        )

    @pytest.mark.asyncio
    async def test_helper_never_raises(self) -> None:
        db = _make_db()
        db.insert_audit_row.side_effect = RuntimeError("boom")
        lifecycle = TicketLifecycleService(db, MagicMock(spec=TicketQueryService))

        # Must not raise despite the DB failure.
        await lifecycle._audit_zombie_autoclose("g1", "t1", "success", "zombie:sweep")
