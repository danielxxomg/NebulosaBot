"""RED for PR2 2.11 ConfirmCancelView <2h/>5d."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.views.confirmation import ConfirmCancelView


@pytest.mark.asyncio
async def test_confirm_view_threshold_triggers_confirm():
    # ,1h should show ConfirmCancelView (owner-only 30s), not immediate schedule
    from bot.cogs.tickets import TicketsCog

    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.update_ticket_last_activity = AsyncMock()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service = MagicMock(
        is_ticket_channel=MagicMock(return_value=True), schedule_close=AsyncMock(), cancel_scheduled_close=AsyncMock()
    )
    bot.db.get_scheduled_close_candidates = AsyncMock(return_value=[])
    bot._guild_mod_role_cache = {}
    cog = TicketsCog(bot)
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(spec=discord.Member)
    msg.author.bot = False
    msg.author.id = 999
    msg.author.guild_permissions.administrator = True
    msg.author.roles = []
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = 123
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = 444
    msg.channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock(), edit=AsyncMock()))
    msg.channel.pins = AsyncMock(return_value=[])
    msg.content = ",1h"
    await cog.on_message(msg)
    # Should have sent a view (confirm), not scheduled immediately
    bot.ticket_service.schedule_close.assert_not_awaited()
    # Check that a view was sent
    assert any("view" in (c.kwargs or {}) for c in msg.channel.send.await_args_list)


@pytest.mark.asyncio
async def test_12h_immediate_no_confirm():
    from bot.cogs.tickets import TicketsCog

    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.update_ticket_last_activity = AsyncMock()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service = MagicMock(
        is_ticket_channel=MagicMock(return_value=True), schedule_close=AsyncMock(), cancel_scheduled_close=AsyncMock()
    )
    bot.db.get_scheduled_close_candidates = AsyncMock(return_value=[])
    bot._guild_mod_role_cache = {}
    cog = TicketsCog(bot)
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(spec=discord.Member)
    msg.author.bot = False
    msg.author.id = 999
    msg.author.guild_permissions.administrator = True
    msg.author.roles = []
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = 123
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = 444
    msg.channel.send = AsyncMock(return_value=MagicMock(pin=AsyncMock(), edit=AsyncMock()))
    msg.channel.pins = AsyncMock(return_value=[])
    msg.content = ",12h"
    await cog.on_message(msg)
    bot.ticket_service.schedule_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_cancel_view_owner_only_and_timeout():
    # ConfirmCancelView is owner-only 30s; modB denied; Cancel/timeout no-op
    guild_id = "123"
    owner_id = 999
    mod_b_id = 888
    called = []

    async def on_confirm(interaction):
        called.append("confirmed")

    view = ConfirmCancelView(guild_id=guild_id, owner_id=owner_id, on_confirm=on_confirm, timeout=30)
    assert view.timeout == 30
    # Non-owner denied
    inter = MagicMock(spec=discord.Interaction)
    inter.user = MagicMock()
    inter.user.id = mod_b_id
    inter.response = MagicMock(send_message=AsyncMock())
    # Find confirm button
    # Access via view.children
    assert len(view.children) == 2
    # Simulate _check_owner for modB
    ok = await view._check_owner(inter)
    assert ok is False
    inter.response.send_message.assert_awaited()
    assert called == []
    # Owner confirm
    inter2 = MagicMock(spec=discord.Interaction)
    inter2.user = MagicMock()
    inter2.user.id = owner_id
    inter2.response = MagicMock(send_message=AsyncMock(), edit_message=AsyncMock())
    # Directly call confirm via view callback simulation: we test _check_owner + on_confirm
    ok2 = await view._check_owner(inter2)
    assert ok2 is True
    await view._on_confirm(inter2)
    assert called == ["confirmed"]
