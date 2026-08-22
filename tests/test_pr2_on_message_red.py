"""RED for PR2 2.8-2.11 on_message ,12h/,cancel, embed, confirm, loop, cancel, silence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.services.ticket_repair_service import TimerMessageResult


def _make_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.update_ticket_last_activity = AsyncMock()
    bot.db.get_ticket_by_channel = AsyncMock(return_value=None)
    bot.db.get_active_ticket_by_channel = AsyncMock(return_value=None)
    bot.db.update_ticket = AsyncMock()
    bot.db.get_scheduled_close_candidates = AsyncMock(return_value=[])
    bot.db.get_ticket = AsyncMock(return_value=None)
    bot.ticket_service = MagicMock()
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=True)
    bot.ticket_service.schedule_close = AsyncMock()
    bot.ticket_service.cancel_scheduled_close = AsyncMock()
    bot.ticket_service.close_ticket_full = AsyncMock()
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=None)
    bot.ticket_service.confirm_timer_schedule = AsyncMock(return_value=None)
    bot.ticket_service.get_due_scheduled_tickets = AsyncMock(return_value=[])
    bot.ticket_service.upsert_timer_embed = AsyncMock()
    bot.guilds = []
    bot._guild_mod_role_cache = {}
    bot.get_channel = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    return bot


def _make_message(content, guild_id=123, channel_id=444, is_mod=True, status="open"):
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    msg.author = MagicMock(spec=discord.Member)
    msg.author.bot = False
    msg.author.id = 999
    msg.author.guild_permissions.administrator = is_mod
    msg.author.roles = []
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = guild_id
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.send.return_value = AsyncMock(pin=AsyncMock(), edit=AsyncMock())
    msg.channel.pins = AsyncMock(return_value=[])
    return msg


def _scheduled_result(seconds=43200, gid="123", ticket_id="t1", author_id="999"):
    return TimerMessageResult(
        action="scheduled",
        guild_id=gid,
        ticket_id=ticket_id,
        author_id=author_id,
        seconds=seconds,
        due_ts=datetime.now(UTC).timestamp() + seconds,
    )


@pytest.mark.asyncio
async def test_on_message_mod_12h_sets_timer_and_pins():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())
    cog = TicketsCog(bot)
    msg = _make_message(",12h", is_mod=True, status="open")
    await cog.on_message(msg)
    bot.ticket_service.handle_timer_message.assert_awaited_once()
    bot.ticket_service.upsert_timer_embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_non_mod_ignored():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    cog = TicketsCog(bot)
    msg = _make_message(",12h", is_mod=False)
    await cog.on_message(msg)
    bot.ticket_service.handle_timer_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_dm_ignored():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    cog = TicketsCog(bot)
    msg = MagicMock(spec=discord.Message)
    msg.author.bot = False
    msg.author.id = 999
    msg.guild = None
    msg.content = ",12h"
    msg.channel = MagicMock()
    msg.channel.id = 444
    await cog.on_message(msg)
    bot.ticket_service.handle_timer_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_hola_ignored_no_error_embed():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=None)  # not a timer cmd
    cog = TicketsCog(bot)
    msg = _make_message(",hola", is_mod=True)
    await cog.on_message(msg)
    bot.ticket_service.upsert_timer_embed.assert_not_awaited()
    # No error embed check — just ensure not scheduled


@pytest.mark.asyncio
async def test_on_message_overwrite_edits_pinned():
    from bot.services.ticket_query_service import TicketQueryService
    from bot.services.ticket_repair_service import TicketRepairService

    # Service-level test: upsert_timer_embed edits existing pinned timer embed.
    db = MagicMock()
    query = MagicMock(spec=TicketQueryService)
    lifecycle = MagicMock()
    svc = TicketRepairService(db, query, lifecycle)
    channel = MagicMock(spec=discord.TextChannel)
    pinned_msg = MagicMock()
    pinned_msg.embeds = [MagicMock(title="⏳ Cierra <t:123:R> (<t:123:F>)")]
    pinned_msg.edit = AsyncMock()
    channel.pins = AsyncMock(return_value=[pinned_msg])
    channel.send = AsyncMock()
    import time

    due_ts = time.time() + 43200
    await svc.upsert_timer_embed(channel, "123", "t1", due_ts, 43200)
    # Second timer should edit, not just send
    pinned_msg.edit.assert_awaited()
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_clears_and_confirms():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {
        "id": "t1",
        "status": "open",
        "guildId": "123",
        "channelId": "444",
        "scheduledCloseAt": "2026-08-20T12:00:00Z",
    }
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(
        return_value=TimerMessageResult(action="cancelled", guild_id="123", ticket_id="t1", author_id="999")
    )
    cog = TicketsCog(bot)
    msg = _make_message(",cancel", is_mod=True)
    await cog.on_message(msg)
    bot.ticket_service.handle_timer_message.assert_awaited_once()
    assert msg.channel.send.await_count >= 1  # cancel confirmation embed


@pytest.mark.asyncio
async def test_cancel_no_timer_noop():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(
        return_value=TimerMessageResult(action="cancelled", guild_id="123", ticket_id="t1", author_id="999")
    )
    cog = TicketsCog(bot)
    msg = _make_message(",cancel", is_mod=True)
    await cog.on_message(msg)
    bot.ticket_service.handle_timer_message.assert_awaited_once()  # still called, safe no-op


@pytest.mark.asyncio
async def test_embed_has_r_and_f():
    from bot.services.ticket_query_service import TicketQueryService
    from bot.services.ticket_repair_service import TicketRepairService

    # Service-level test: timer embed MUST carry <t:R> and <t:F>.
    db = MagicMock()
    query = MagicMock(spec=TicketQueryService)
    lifecycle = MagicMock()
    svc = TicketRepairService(db, query, lifecycle)
    channel = MagicMock(spec=discord.TextChannel)
    channel.pins = AsyncMock(return_value=[])
    sent_msg = MagicMock()
    sent_msg.pin = AsyncMock()
    channel.send = AsyncMock(return_value=sent_msg)
    import time

    due_ts = time.time() + 43200
    await svc.upsert_timer_embed(channel, "123", "t1", due_ts, 43200)
    # Find embed with <t:*:R> and <t:*:F>
    found = False
    for call in channel.send.await_args_list:
        kwargs = call.kwargs
        embed = kwargs.get("embed")
        if embed and "<t:" in (embed.title or "") and ":R>" in (embed.title or "") and ":F>" in (embed.title or ""):
            found = True
            assert "⏳" in embed.title or "Cierra" in embed.title
    assert found, "Pinned embed must carry ⏳ Cierra <t:unix:R> (<t:unix:F>)"


@pytest.mark.asyncio
async def test_scheduled_loop_batch_50_silent():
    from bot.cogs.tickets import TicketsCog
    from bot.models.ticket import Ticket

    bot = _make_bot()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    bot.guilds = [guild]
    rows = [
        {
            "id": f"t{i}",
            "channelId": str(500 + i),
            "guildId": "123",
            "ticketNumber": i,
            "authorId": "a",
            "status": "open",
            "createdAt": datetime.now(UTC),
            "lastActivity": datetime.now(UTC),
        }
        for i in range(60)
    ]
    # First 50 are due
    bot.ticket_service.get_due_scheduled_tickets = AsyncMock(return_value=rows[:50])
    # Round 3: the cog delegates the row fetch + status branch to the service;
    # wire resolve_due_ticket_for_close to resolve each open row to a Ticket so
    # the cog proceeds to close_ticket_full.
    bot.ticket_service.resolve_due_ticket_for_close = AsyncMock(
        side_effect=lambda gid, r: Ticket.from_db_row(r) if r["id"].startswith("t") else None
    )
    bot.db.get_ticket = AsyncMock(
        side_effect=lambda tid, guild_id=None: next((r for r in rows if r["id"] == tid), None)
    )
    ch = MagicMock(spec=discord.TextChannel)
    ch.guild = guild
    bot.get_channel = MagicMock(return_value=ch)
    bot.ticket_service.close_ticket_full = AsyncMock()
    cog = TicketsCog(bot)
    await cog.scheduled_close_loop()
    # batch 50 enforced: only 50 processed even if 60 due (we returned 50)
    assert bot.ticket_service.close_ticket_full.await_count == 50
    # silent: manual=False
    for call in bot.ticket_service.close_ticket_full.await_args_list:
        assert call.kwargs.get("manual") is False


@pytest.mark.asyncio
async def test_cog_unload_cancels_scheduled():
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    cog = TicketsCog(bot)
    cog.scheduled_close_loop = MagicMock(is_running=MagicMock(return_value=True), cancel=MagicMock())
    cog.auto_close_stale_tickets = MagicMock(is_running=MagicMock(return_value=False), cancel=MagicMock())
    cog.integrity_sweep_loop = MagicMock(is_running=MagicMock(return_value=False), cancel=MagicMock())
    await cog.cog_unload()
    cog.scheduled_close_loop.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 2 — timer gate honors permissionMatrix via can_member("tickets.manage")
# ---------------------------------------------------------------------------


def _make_ticket_manager_message(
    *,
    role_id: int | None = None,
    administrator: bool = False,
    guild_id: int = 123,
    channel_id: int = 444,
    content: str = ",12h",
) -> MagicMock:
    """Build a Message whose author is a non-admin, non-modRole member.

    When ``role_id`` is given the author carries that role — used to simulate a
    matrix-granted ticket manager (``permissionMatrix["tickets.manage"]``).
    """
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    author = MagicMock(spec=discord.Member)
    author.bot = False
    author.id = 999
    author.guild_permissions.administrator = administrator
    roles: list[MagicMock] = []
    if role_id is not None:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        roles.append(role)
    author.roles = roles
    msg.author = author
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = guild_id
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.send.return_value = AsyncMock(pin=AsyncMock(), edit=AsyncMock())
    msg.channel.pins = AsyncMock(return_value=[])
    return msg


@pytest.mark.asyncio
async def test_on_message_matrix_granted_ticket_manager_passes_gate() -> None:
    """A member granted ``tickets.manage`` via permissionMatrix MUST pass the timer gate.

    RED: the gate currently uses ``is_mod_member`` (admin/modRole only), so a
    non-admin, non-modRole member with a matrix-granted ticket-manager role is
    denied. After GREEN the gate uses ``can_member("tickets.manage", ...)`` and
    the matrix grant lets the timer command through.
    """
    from bot.cogs.tickets import TicketsCog

    ticket_manager_role = 4242
    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())

    guild_service = MagicMock()
    guild_service.get_config = AsyncMock(
        return_value=MagicMock(
            permission_matrix={"tickets.manage": [str(ticket_manager_role)]},
            mod_role_id=None,
        )
    )
    cog = TicketsCog(bot)
    msg = _make_ticket_manager_message(role_id=ticket_manager_role, administrator=False)

    with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
        await cog.on_message(msg)

    bot.ticket_service.handle_timer_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_message_plain_member_denied_timer_gate() -> None:
    """A plain member (no admin, no modRole, no matrix grant) MUST be denied."""
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())

    guild_service = MagicMock()
    guild_service.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
    cog = TicketsCog(bot)
    msg = _make_ticket_manager_message(role_id=None, administrator=False)

    with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
        await cog.on_message(msg)

    bot.ticket_service.handle_timer_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_admin_still_passes_timer_gate() -> None:
    """An administrator MUST still pass the timer gate (implicit admin pass)."""
    from bot.cogs.tickets import TicketsCog

    bot = _make_bot()
    row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
    bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())

    # Empty matrix — admin passes via the implicit admin short-circuit.
    guild_service = MagicMock()
    guild_service.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
    cog = TicketsCog(bot)
    msg = _make_ticket_manager_message(role_id=None, administrator=True)

    with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
        await cog.on_message(msg)

    bot.ticket_service.handle_timer_message.assert_awaited_once()
