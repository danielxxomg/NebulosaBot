"""RED for PR2 2.13-2.14 coexistence + silent scheduled close."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


@pytest.mark.asyncio
async def test_scheduled_loop_is_silent_no_countdown():
    # scheduled_close_loop must call close_ticket_full with manual=False (silent), not countdown
    from datetime import UTC, datetime

    from bot.cogs.tickets import TicketsCog
    from bot.models.ticket import Ticket

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


@pytest.mark.asyncio
async def test_auto_close_clears_scheduled_fields():
    # AUTO_CLOSE sweep should clear scheduledCloseAt/By via lifecycle/service.
    # Round 2: the clear was extracted into _clear_scheduled_fields (DRY across
    # both close_ticket branches); assert close_ticket still triggers it, and
    # the helper itself carries the scheduledCloseAt field clear.
    import inspect

    from bot.services.ticket_lifecycle_service import TicketLifecycleService

    close_src = inspect.getsource(TicketLifecycleService.close_ticket)
    helper_src = inspect.getsource(TicketLifecycleService._clear_scheduled_fields)
    assert "_clear_scheduled_fields" in close_src, "close_ticket MUST call _clear_scheduled_fields"
    assert "scheduledCloseAt" in helper_src or "scheduled_close" in helper_src.lower()


@pytest.mark.asyncio
async def test_coexist_both_fire_one_wins():
    # CF5 remediation: real transition_ticket_to_closed idempotency via production
    # TicketService.close_ticket against a stateful DB fake (not a self-fulfilling
    # mock). First close wins (Ticket), second raises ValueError (already_closed).
    from datetime import UTC, datetime

    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.ticket_service import TicketService
    from tests.test_database import FakeQueryBuilder, FakeSupabaseClient

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


def test_scheduled_loop_silent_no_5_to_1_countdown():
    import pathlib

    src = pathlib.Path("bot/cogs/tickets.py").read_text()
    # scheduled_close_loop must NOT send "5"/countdown; only close_ticket_full manual=False
    seg = src[src.index("async def scheduled_close_loop") : src.index("async def scheduled_close_loop") + 2500]
    assert 'send("5")' not in seg and "countdown" not in seg.lower()
    src2 = pathlib.Path("bot/services/ticket_repair_service.py").read_text()
    # repair close_ticket_full with manual=False must sleep CHANNEL_DELETE_DELAY not countdown
    assert "CHANNEL_DELETE_DELAY" in src2
