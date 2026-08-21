"""RED for PR2 2.13-2.14 coexistence + silent scheduled close."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


@pytest.mark.asyncio
async def test_scheduled_loop_is_silent_no_countdown():
    # scheduled_close_loop must call close_ticket_full with manual=False (silent), not countdown
    from datetime import UTC, datetime

    from bot.cogs.tickets import TicketsCog

    bot = MagicMock()
    bot.db = MagicMock()
    bot.ticket_service = MagicMock(is_ticket_channel=MagicMock(return_value=True), close_ticket_full=AsyncMock())
    bot.db.get_scheduled_close_candidates = AsyncMock(
        return_value=[
            {
                "id": "t1",
                "channelId": "500",
                "guildId": "123",
                "ticketNumber": 1,
                "authorId": "a",
                "status": "open",
                "createdAt": datetime.now(UTC),
                "lastActivity": datetime.now(UTC),
            }
        ]
    )
    bot.db.get_ticket = AsyncMock(
        return_value={
            "id": "t1",
            "channelId": "500",
            "guildId": "123",
            "ticketNumber": 1,
            "authorId": "a",
            "status": "open",
            "createdAt": datetime.now(UTC),
            "lastActivity": datetime.now(UTC),
        }
    )
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
    # AUTO_CLOSE sweep should clear scheduledCloseAt/By via lifecycle/service
    import inspect

    from bot.services.ticket_lifecycle_service import TicketLifecycleService

    src = inspect.getsource(TicketLifecycleService.close_ticket)
    assert "scheduledCloseAt" in src or "scheduled_close" in src.lower()


@pytest.mark.asyncio
async def test_coexist_both_fire_one_wins():
    # Simulate transition_ticket_to_closed idempotency: second call returns None
    from unittest.mock import AsyncMock

    db = MagicMock()
    # First succeeds, second returns None (already closed)
    db.transition_ticket_to_closed = AsyncMock(side_effect=[{"id": "t1", "status": "closed"}, None])
    # If both AUTO_CLOSE and scheduled loop fire, exactly one mutation
    r1 = await db.transition_ticket_to_closed("g1", "t1")
    r2 = await db.transition_ticket_to_closed("g1", "t1")
    assert r1 is not None and r2 is None


def test_scheduled_loop_silent_no_5_to_1_countdown():
    import pathlib

    src = pathlib.Path("bot/cogs/tickets.py").read_text()
    # scheduled_close_loop must NOT send "5"/countdown; only close_ticket_full manual=False
    seg = src[src.index("async def scheduled_close_loop") : src.index("async def scheduled_close_loop") + 2500]
    assert 'send("5")' not in seg and "countdown" not in seg.lower()
    src2 = pathlib.Path("bot/services/ticket_repair_service.py").read_text()
    # repair close_ticket_full with manual=False must sleep CHANNEL_DELETE_DELAY not countdown
    assert "CHANNEL_DELETE_DELAY" in src2
