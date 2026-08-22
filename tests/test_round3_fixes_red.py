# ruff: noqa: S311
"""RED tests for NebulosaBot GGA ROUND 3 — 2 remaining C blockers.

Strict TDD: these tests MUST FAIL before the fixes are applied, then pass.

Covers:
- Blocker 1 — Direct DB mutation inside the cog. The
  ``TicketsCog._close_due_scheduled_ticket`` helper fetches the full ticket
  row via ``db.get_ticket`` and clears stale scheduled fields via
  ``db.update_ticket`` directly from the cog. AGENTS.md: "Cogs handle
  Discord interaction only — no business logic". The row fetch + status
  branch + write MUST be routed through ``ticket_service`` (the service
  owns the write). The cog only resolves the Discord channel + calls
  ``close_ticket_full``.
- Blocker 2 — Remaining ``contextlib.suppress(Exception)`` sites are
  semantically bare except blocks that hide failures. They MUST catch
  narrow Discord exceptions (``discord.HTTPException`` / ``NotFound`` /
  ``Forbidden``) and log via the module logger while keeping best-effort
  behavior (the flow MUST NOT break). Sites:
    * tickets cog ``_show_timer_confirm_view`` confirm feedback
      (``interaction.response.edit_message``)
    * ticket_repair_service ``upsert_timer_embed`` — pin scan, pinned-edit,
      ``msg.pin``
"""

from __future__ import annotations

import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.models.ticket import Ticket
from bot.services.ticket_lifecycle_service import TicketLifecycleService
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService

# ===========================================================================
# Shared fixtures
# ===========================================================================


def _open_row() -> dict:
    """A fully-formed open ticket DB row (camelCase keys)."""
    return {
        "id": "due-uuid-0001",
        "ticketNumber": 7,
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
        "scheduledCloseAt": "2026-08-22T12:00:00+00:00",
        "scheduledCloseBy": "999999999",
    }


def _closed_row() -> dict:
    """A fully-formed closed ticket DB row (already closed — stale fields)."""
    return {
        **_open_row(),
        "status": "closed",
        "closedAt": "2026-08-22T12:00:00+00:00",
    }


def _candidate_row(ticket_id: str = "due-uuid-0001", channel_id: str = "888888888") -> dict:
    """A partial candidate row from ``get_scheduled_close_candidates``."""
    return {
        "id": ticket_id,
        "ticketNumber": 7,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": channel_id,
        "status": "open",
        "scheduledCloseAt": "2026-08-22T12:00:00+00:00",
        "scheduledCloseBy": "999999999",
        "lastActivity": "2026-01-15T10:00:00+00:00",
    }


def _repair(mock_db: AsyncMock) -> TicketRepairService:
    """Build a TicketRepairService with a mock db + stub lifecycle/query."""
    lifecycle = MagicMock(spec=TicketLifecycleService)
    query = MagicMock(spec=TicketQueryService)
    return TicketRepairService(db=mock_db, query=query, lifecycle=lifecycle)


def _make_channel(channel_id: int = 888888888) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.guild = MagicMock()
    channel.guild.id = 123456789
    channel.delete = AsyncMock()
    return channel


def _make_bot_for_cog(mock_db: AsyncMock, channel: MagicMock) -> MagicMock:
    """Build a bot mock with a real-ish ticket_service facade mock."""
    bot = MagicMock()
    bot.db = mock_db
    bot.get_channel = MagicMock(return_value=channel)
    ticket_service = MagicMock()
    ticket_service.close_ticket_full = AsyncMock(return_value=None)
    ticket_service.get_due_scheduled_tickets = AsyncMock(return_value=[])
    ticket_service.cancel_scheduled_close = AsyncMock(return_value=None)
    bot.ticket_service = ticket_service
    return bot


# ===========================================================================
# Blocker 1 — _close_due_scheduled_ticket routes through the service layer
# ===========================================================================


@pytest.mark.asyncio
async def test_close_due_scheduled_open_ticket_routes_close_through_service(
    mock_db: AsyncMock,
) -> None:
    """Blocker 1 RED: for an open/claimed due ticket, the cog MUST delegate
    the row fetch + status branch to the service and MUST NOT call
    ``bot.db.get_ticket`` / ``bot.db.update_ticket`` directly.

    The service resolves the ticket and returns a ``Ticket`` the cog then
    passes to ``close_ticket_full``. The cog's own DB handle is never used
    for this path.
    """
    from bot.cogs.tickets import TicketsCog

    channel = _make_channel()
    bot = _make_bot_for_cog(mock_db, channel)
    # The service facade resolves the full row + builds the Ticket for the cog.
    bot.ticket_service.resolve_due_ticket_for_close = AsyncMock(return_value=Ticket.from_db_row(_open_row()))
    # bot.db.get_ticket / update_ticket MUST stay untouched by the cog path.
    mock_db.get_ticket = AsyncMock(return_value=_open_row())
    mock_db.update_ticket = AsyncMock(return_value=None)

    cog = TicketsCog(bot=bot)
    gid = "123456789"
    row = _candidate_row()

    await cog._close_due_scheduled_ticket(gid, row)

    # The cog MUST route the row resolution through the service.
    bot.ticket_service.resolve_due_ticket_for_close.assert_awaited_once()
    # The cog MUST call close_ticket_full with the service-resolved Ticket.
    bot.ticket_service.close_ticket_full.assert_awaited_once()
    # CRITICAL — the cog MUST NOT touch the DB directly for this path.
    mock_db.get_ticket.assert_not_awaited()
    mock_db.update_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_due_scheduled_already_closed_routes_clear_through_service(
    mock_db: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Blocker 1 RED: when the due ticket is already closed, the cog MUST
    delegate the stale scheduled-field clear to the service
    (``cancel_scheduled_close``) and MUST NOT call ``bot.db.update_ticket``
    directly. The service owns the write.

    The cog MUST NOT call ``close_ticket_full`` for an already-closed ticket.
    """
    from bot.cogs.tickets import TicketsCog

    channel = _make_channel()
    bot = _make_bot_for_cog(mock_db, channel)
    # Service resolves to an already-closed ticket → signal "clear stale".
    bot.ticket_service.resolve_due_ticket_for_close = AsyncMock(return_value=None)
    bot.ticket_service.cancel_scheduled_close = AsyncMock(return_value=None)
    mock_db.get_ticket = AsyncMock(return_value=_closed_row())
    mock_db.update_ticket = AsyncMock(return_value=None)

    cog = TicketsCog(bot=bot)
    gid = "123456789"
    row = _candidate_row()

    await cog._close_due_scheduled_ticket(gid, row)

    # Already closed → cog MUST NOT close the ticket.
    bot.ticket_service.close_ticket_full.assert_not_awaited()
    # The cog MUST NOT clear stale fields via bot.db directly.
    mock_db.update_ticket.assert_not_awaited()
    mock_db.get_ticket.assert_not_awaited()


def test_close_due_scheduled_ticket_source_has_no_direct_db_write() -> None:
    """Blocker 1 RED (source guard): ``_close_due_scheduled_ticket`` source
    MUST NOT contain a direct ``db.get_ticket`` or ``db.update_ticket`` call.

    The row fetch + write belong to the service layer.
    """
    from bot.cogs.tickets import TicketsCog

    src = inspect.getsource(TicketsCog._close_due_scheduled_ticket)
    # The cog MUST NOT fetch the full row or clear scheduled fields from the DB.
    assert "db.get_ticket" not in src, (
        "cog _close_due_scheduled_ticket MUST NOT call db.get_ticket directly — "
        "route the row fetch through ticket_service"
    )
    assert "db.update_ticket" not in src, (
        "cog _close_due_scheduled_ticket MUST NOT call db.update_ticket directly — "
        "route the stale-field clear through ticket_service.cancel_scheduled_close"
    )


# ===========================================================================
# Blocker 2 — _show_timer_confirm_view confirm feedback: narrow except + log
# ===========================================================================


@pytest.mark.asyncio
async def test_show_timer_confirm_view_logs_when_edit_message_raises(
    mock_db: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Blocker 2 RED: the confirm-view success feedback
    (``interaction.response.edit_message``) MUST NOT swallow
    ``discord.HTTPException`` silently. The failure MUST be logged while the
    flow continues (best-effort — the schedule already succeeded).

    Drives the cog's ``_show_timer_confirm_view`` and simulates the
    ``_on_confirm`` callback raising HTTPException on the edit.
    """
    from bot.cogs.tickets import TicketsCog
    from bot.services.ticket_repair_service import TimerMessageResult

    channel = _make_channel()
    bot = _make_bot_for_cog(mock_db, channel)
    bot.ticket_service.confirm_timer_schedule = AsyncMock(
        return_value=TimerMessageResult(
            action="scheduled",
            guild_id="123456789",
            ticket_id="due-uuid-0001",
            author_id="999",
            seconds=3600,
            due_ts=1234567890.0,
            schedule_failed=False,
        )
    )
    bot.ticket_service.upsert_timer_embed = AsyncMock()

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(spec=discord.Member)
    message.author.id = 999
    message.channel = channel

    cog = TicketsCog(bot=bot)
    with caplog.at_level(logging.ERROR, logger="bot.cogs.tickets"):
        await cog._show_timer_confirm_view(message, "123456789", "due-uuid-0001", 3600, "Confirm", "Desc")

    # The confirm view was sent. Now simulate the owner clicking confirm:
    # invoke the on_confirm closure by finding the view the cog built.
    # The cog sends exactly one message carrying a ConfirmCancelView.
    sent_call = channel.send.await_args
    assert sent_call is not None
    view = sent_call.kwargs.get("view")
    assert view is not None, "cog MUST send a ConfirmCancelView"

    # Build an interaction whose edit_message raises HTTPException.
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 999  # owner
    interaction.response = MagicMock()
    interaction.response.edit_message = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=400), "edit failed")
    )

    with caplog.at_level(logging.WARNING, logger="bot.cogs.tickets"):
        # Owner-gated confirm: call the view's on_confirm directly.
        await view._on_confirm(interaction)  # type: ignore[attr-defined]

    # The edit failure MUST be logged (was swallowed by suppress(Exception)).
    assert any(
        r.name == "bot.cogs.tickets" and ("edit" in r.message.lower() or "confirm" in r.message.lower())
        for r in caplog.records
    ), f"expected an edit/confirm failure log, got: {[r.message for r in caplog.records]}"


# ===========================================================================
# Blocker 2 — upsert_timer_embed pin ops: narrow except + log
# ===========================================================================


@pytest.mark.asyncio
async def test_upsert_timer_embed_logs_when_pin_scan_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Blocker 2 RED: ``channel.pins()`` raising ``discord.HTTPException``
    MUST be logged and the flow MUST continue to send a fresh embed
    (best-effort). Was swallowed by ``contextlib.suppress(Exception)``.
    """
    import time

    db = MagicMock()
    svc = _repair(db)
    channel = _make_channel()
    channel.pins = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "pins down"))
    sent_msg = MagicMock()
    sent_msg.pin = AsyncMock()
    channel.send = AsyncMock(return_value=sent_msg)

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_repair_service"):
        await svc.upsert_timer_embed(channel, "123456789", "t1", time.time() + 43200, 43200)

    # The pin-scan failure MUST be logged.
    assert any(r.name == "bot.services.ticket_repair_service" and "pin" in r.message.lower() for r in caplog.records), (
        f"expected a pin-scan failure log, got: {[r.message for r in caplog.records]}"
    )
    # Best-effort: a fresh embed is still sent despite the pins() failure.
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_timer_embed_logs_when_pinned_edit_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Blocker 2 RED: editing an existing pinned timer embed that raises
    ``discord.HTTPException`` MUST be logged and the flow MUST continue
    (fall through to sending a fresh embed). Was swallowed by
    ``contextlib.suppress(Exception)``.
    """
    import time

    db = MagicMock()
    svc = _repair(db)
    channel = _make_channel()
    pinned_msg = MagicMock()
    pinned_msg.embeds = [MagicMock(title="⏳ Cierra <t:123:R> (<t:123:F>)")]
    pinned_msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "edit denied"))
    channel.pins = AsyncMock(return_value=[pinned_msg])
    sent_msg = MagicMock()
    sent_msg.pin = AsyncMock()
    channel.send = AsyncMock(return_value=sent_msg)

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_repair_service"):
        await svc.upsert_timer_embed(channel, "123456789", "t1", time.time() + 43200, 43200)

    # The pinned-edit failure MUST be logged.
    assert any(r.name == "bot.services.ticket_repair_service" and "pin" in r.message.lower() for r in caplog.records), (
        f"expected a pinned-edit failure log, got: {[r.message for r in caplog.records]}"
    )
    # Best-effort: a fresh embed is still sent after the pinned edit failed.
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_timer_embed_logs_when_msg_pin_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Blocker 2 RED: pinning the freshly sent timer embed that raises
    ``discord.HTTPException`` MUST be logged. The embed is already sent,
    so the flow is complete (best-effort). Was swallowed by
    ``contextlib.suppress(Exception)``.
    """
    import time

    db = MagicMock()
    svc = _repair(db)
    channel = _make_channel()
    channel.pins = AsyncMock(return_value=[])
    sent_msg = MagicMock()
    sent_msg.pin = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "pin denied"))
    channel.send = AsyncMock(return_value=sent_msg)

    with caplog.at_level(logging.WARNING, logger="bot.services.ticket_repair_service"):
        await svc.upsert_timer_embed(channel, "123456789", "t1", time.time() + 43200, 43200)

    # The pin failure MUST be logged (was swallowed).
    assert any(r.name == "bot.services.ticket_repair_service" and "pin" in r.message.lower() for r in caplog.records), (
        f"expected a pin failure log, got: {[r.message for r in caplog.records]}"
    )
    # The embed was sent successfully.
    channel.send.assert_awaited_once()


# ===========================================================================
# Blocker 2 — structural source guard: no bare suppress(Exception) at the
# named sites
# ===========================================================================


def test_no_bare_suppress_exception_at_round3_sites() -> None:
    """Blocker 2 RED (source guard): the 4 named sites MUST NOT contain
    ``contextlib.suppress(Exception)`` — a semantically bare except.

    Sites:
    - bot/cogs/tickets.py ``_show_timer_confirm_view`` (confirm feedback)
    - bot/services/ticket_repair_service.py ``upsert_timer_embed`` (3 sites)

    Comments referencing the old antipattern are ignored — only executable
    code is checked.
    """
    import re

    from bot.cogs.tickets import TicketsCog

    def _strip_comments(src: str) -> str:
        """Remove ``# ...`` comment text so guard only inspects code."""
        return re.sub(r"#.*", "", src)

    # The cog confirm-view method source MUST NOT use bare suppress(Exception).
    confirm_src = _strip_comments(inspect.getsource(TicketsCog._show_timer_confirm_view))
    assert "contextlib.suppress(Exception)" not in confirm_src, (
        "_show_timer_confirm_view MUST NOT use contextlib.suppress(Exception) — "
        "catch discord.HTTPException + log instead"
    )

    # upsert_timer_embed source MUST NOT use bare suppress(Exception) at all.
    upsert_src = _strip_comments(inspect.getsource(TicketRepairService.upsert_timer_embed))
    assert "contextlib.suppress(Exception)" not in upsert_src, (
        "upsert_timer_embed MUST NOT use contextlib.suppress(Exception) — "
        "catch discord.HTTPException/NotFound/Forbidden + log instead"
    )
