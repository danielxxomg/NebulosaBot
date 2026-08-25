"""RED for PR2 2.13-2.14 coexistence + silent scheduled close."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.cogs.tickets import TicketsCog
from bot.core.cache import TTLCache
from bot.core.database import Database
from bot.models.ticket import Ticket
from bot.services.ticket_service import TicketService
from tests.test_database import FakeQueryBuilder, FakeSupabaseClient


@pytest.mark.asyncio
async def test_scheduled_loop_is_silent_no_countdown() -> None:
    # scheduled_close_loop must call close_ticket_full with manual=False (silent), not countdown
    bot = MagicMock()
    bot.db = MagicMock()
    row = {
        "id": "t1",
        "channelId": "500",
        "guildId": "123",
        "ticketNumber": 1,
        "authorId": "a",
        "status": "open",
        "createdAt": datetime.now(UTC),
        "lastActivity": datetime.now(UTC),
    }
    bot.ticket_service = MagicMock(
        is_ticket_channel=MagicMock(return_value=True),
        close_ticket_full=AsyncMock(),
        get_due_scheduled_tickets=AsyncMock(return_value=[row]),
        # Round 3: the cog delegates the row fetch + status branch to the
        # service; return the open Ticket so the cog proceeds to close.
        resolve_due_ticket_for_close=AsyncMock(return_value=Ticket.from_db_row(row)),
    )
    bot.db.get_ticket = AsyncMock(return_value=row)
    # Need guild + channel
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    bot.guilds = [guild]
    ch = MagicMock(spec=discord.TextChannel)
    ch.guild = guild
    bot.get_channel = MagicMock(return_value=ch)
    cog = TicketsCog(bot)
    await cog.scheduled_close_loop()
    bot.ticket_service.close_ticket_full.assert_awaited_once()
    assert bot.ticket_service.close_ticket_full.await_args.kwargs.get("manual") is False
    # Ensure no countdown path was taken (TicketService._countdown_and_delete not called via manual True)
    # manual False is the silent proof


# Consolidation note (cycle-5 S5b/c): the former
# test_scheduled_loop_silent_no_5_to_1_countdown source-grep was deleted —
# test_scheduled_loop_is_silent_no_countdown above proves silence behaviorally
# (close_ticket_full awaited with manual=False on the real loop path).
#
# The former test_auto_close_clears_scheduled_fields inspect.getsource greps
# ("close_ticket MUST call _clear_scheduled_fields" / helper carries
# scheduledCloseAt) were deleted — behavioral twin:
# tests/test_remediation_cycle2_behavior.py::TestScheduledLoopEndToEnd::
# test_loop_closes_clears_scheduled_and_deletes_channel drives the real
# close_ticket_full → TicketLifecycleService.close_ticket →
# _clear_scheduled_fields chain against a stateful DB fake and asserts the
# UPDATE payload carries scheduledCloseAt=None; if close_ticket ever stopped
# clearing, that twin fails.


@pytest.mark.asyncio
async def test_coexist_both_fire_one_wins() -> None:
    # CF5 remediation: real transition_ticket_to_closed idempotency via production
    # TicketService.close_ticket against a stateful DB fake (not a self-fulfilling
    # mock). First close wins (Ticket), second raises ValueError (already_closed).

    class _StatefulTicket(FakeQueryBuilder):
        def __init__(self, row):
            super().__init__(result_data=[row])
            self._n = 0

        async def execute(self):
            self._n += 1
            resp = MagicMock()
            if self._n <= 2:  # 1st close: SELECT match + UPDATE succeeds
                resp.data = [
                    {
                        **row,
                        "status": "closed" if self._n == 2 else row["status"],
                        "closedAt": datetime.now(UTC).isoformat() if self._n == 2 else None,
                    }
                ]
            else:  # 2nd close: SELECT matches 0 rows (already closed)
                resp.data = []
            return resp

    row = {
        "id": "t1",
        "guildId": "g1",
        "channelId": "500",
        "ticketNumber": 1,
        "authorId": "a",
        "status": "open",
        "createdAt": datetime.now(UTC),
        "lastActivity": datetime.now(UTC),
    }
    fake = FakeSupabaseClient()
    fake._tables["ticket"] = _StatefulTicket(row)
    db = Database(url="https://test.supabase.co", key="test-key")
    db._client = fake

    svc = TicketService(db, TTLCache())
    winner = await svc.close_ticket("t1", "auto", guild_id="g1", close_reason="zombie:auto")
    assert winner.status == "closed"  # exactly one winner via real transition
    with pytest.raises(ValueError, match="already closed"):
        await svc.close_ticket("t1", "auto:scheduled", guild_id="g1", close_reason="zombie:scheduled")


# Consolidation note (cycle-5 S5b/c): the former
# test_scheduled_loop_silent_no_5_to_1_countdown source-grep was deleted —
# test_scheduled_loop_is_silent_no_countdown above proves silence behaviorally
# (close_ticket_full awaited with manual=False on the real loop path).
