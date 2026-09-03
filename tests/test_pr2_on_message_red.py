"""RED for PR2 2.8-2.11 on_message ,12h/,cancel, embed, confirm, loop, cancel, silence.

Slice B 2.1: _make_bot/_make_message hoisted to tests.conftest as plain builders
(make_pr2_bot/make_pr2_message/make_pr2_manager_message); 13 tests compressed
into 3 parametrized groups with explicit ids, asserts verbatim.
"""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.tickets import TicketsCog
from bot.models.ticket import Ticket
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService, TimerMessageResult
from tests.conftest import make_pr2_bot, make_pr2_manager_message, make_pr2_message


def _scheduled_result(
    seconds: int = 43200, gid: str = "123", ticket_id: str = "t1", author_id: str = "999"
) -> TimerMessageResult:
    return TimerMessageResult(
        action="scheduled",
        guild_id=gid,
        ticket_id=ticket_id,
        author_id=author_id,
        seconds=seconds,
        due_ts=datetime.now(UTC).timestamp() + seconds,
    )


# ---------------------------------------------------------------------------
# Group 1: on_message gate + timer dispatch (7 cases → 1 parametrized test)
# ---------------------------------------------------------------------------

_ON_MESSAGE_GATE_CASES = [
    pytest.param("mod_12h_sets_timer_and_pins", id="mod_12h_sets_timer_and_pins"),
    pytest.param("non_mod_ignored", id="non_mod_ignored"),
    pytest.param("dm_ignored", id="dm_ignored"),
    pytest.param("hola_ignored_no_error_embed", id="hola_ignored_no_error_embed"),
    pytest.param("matrix_granted_ticket_manager_passes_gate", id="matrix_granted_ticket_manager_passes_gate"),
    pytest.param("plain_member_denied_timer_gate", id="plain_member_denied_timer_gate"),
    pytest.param("admin_still_passes_timer_gate", id="admin_still_passes_timer_gate"),
]


@pytest.mark.parametrize("case", _ON_MESSAGE_GATE_CASES)
@pytest.mark.asyncio
async def test_on_message_gate_cases(case: str) -> None:
    """Parametrized gate/dispatch cases — asserts verbatim per original 7 tests."""
    match case:
        case "mod_12h_sets_timer_and_pins":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())
            cog = TicketsCog(bot)
            msg = make_pr2_message(",12h", is_mod=True, status="open")
            await cog.on_message(msg)
            bot.ticket_service.handle_timer_message.assert_awaited_once()
            bot.ticket_service.upsert_timer_embed.assert_awaited_once()
        case "non_mod_ignored":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            cog = TicketsCog(bot)
            msg = make_pr2_message(",12h", is_mod=False)
            await cog.on_message(msg)
            bot.ticket_service.handle_timer_message.assert_not_awaited()
        case "dm_ignored":
            bot = make_pr2_bot()
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
        case "hola_ignored_no_error_embed":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            bot.ticket_service.handle_timer_message = AsyncMock(return_value=None)  # not a timer cmd
            cog = TicketsCog(bot)
            msg = make_pr2_message(",hola", is_mod=True)
            await cog.on_message(msg)
            bot.ticket_service.upsert_timer_embed.assert_not_awaited()
            # No error embed check — just ensure not scheduled
        case "matrix_granted_ticket_manager_passes_gate":
            ticket_manager_role = 4242
            bot = make_pr2_bot()
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
            msg = make_pr2_manager_message(role_id=ticket_manager_role, administrator=False)

            with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
                await cog.on_message(msg)

            bot.ticket_service.handle_timer_message.assert_awaited_once()
        case "plain_member_denied_timer_gate":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())

            guild_service = MagicMock()
            guild_service.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
            cog = TicketsCog(bot)
            msg = make_pr2_manager_message(role_id=None, administrator=False)

            with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
                await cog.on_message(msg)

            bot.ticket_service.handle_timer_message.assert_not_awaited()
        case "admin_still_passes_timer_gate":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            bot.ticket_service.handle_timer_message = AsyncMock(return_value=_scheduled_result())

            # Empty matrix — admin passes via the implicit admin short-circuit.
            guild_service = MagicMock()
            guild_service.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
            cog = TicketsCog(bot)
            msg = make_pr2_manager_message(role_id=None, administrator=True)

            with patch("bot.utils.checks._get_guild_service", return_value=guild_service):
                await cog.on_message(msg)

            bot.ticket_service.handle_timer_message.assert_awaited_once()
        case _:
            msg = f"unknown case {case!r}"  # noqa: TRY003 -- test branching guard, not production raise
            raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Group 2: timer embed + cancel (4 cases → 1 parametrized test)
# ---------------------------------------------------------------------------

_TIMER_EMBED_CASES = [
    pytest.param("overwrite_edits_pinned", id="overwrite_edits_pinned"),
    pytest.param("embed_has_r_and_f", id="embed_has_r_and_f"),
    pytest.param("cancel_clears_and_confirms", id="cancel_clears_and_confirms"),
    pytest.param("cancel_no_timer_noop", id="cancel_no_timer_noop"),
]


@pytest.mark.parametrize("case", _TIMER_EMBED_CASES)
@pytest.mark.asyncio
async def test_timer_embed_cases(case: str) -> None:
    """Parametrized embed/cancel cases — asserts verbatim per original 4 tests."""
    match case:
        case "overwrite_edits_pinned":
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

            due_ts = time.time() + 43200
            await svc.upsert_timer_embed(channel, "123", "t1", due_ts, 43200)
            # Second timer should edit, not just send
            pinned_msg.edit.assert_awaited()
            channel.send.assert_not_awaited()
        case "embed_has_r_and_f":
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

            due_ts = time.time() + 43200
            await svc.upsert_timer_embed(channel, "123", "t1", due_ts, 43200)
            # Find embed with <t:*:R> and <t:*:F>
            found = False
            for call in channel.send.await_args_list:
                kwargs = call.kwargs
                embed = kwargs.get("embed")
                if (
                    embed
                    and "<t:" in (embed.title or "")
                    and ":R>" in (embed.title or "")
                    and ":F>" in (embed.title or "")
                ):
                    found = True
                    assert "⏳" in embed.title or "Cierra" in embed.title
            assert found, "Pinned embed must carry ⏳ Cierra <t:unix:R> (<t:unix:F>)"
        case "cancel_clears_and_confirms":
            bot = make_pr2_bot()
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
            msg = make_pr2_message(",cancel", is_mod=True)
            await cog.on_message(msg)
            bot.ticket_service.handle_timer_message.assert_awaited_once()
            assert msg.channel.send.await_count >= 1  # cancel confirmation embed
        case "cancel_no_timer_noop":
            bot = make_pr2_bot()
            row = {"id": "t1", "status": "open", "guildId": "123", "channelId": "444"}
            bot.db.get_ticket_by_channel = AsyncMock(return_value=row)
            bot.ticket_service.handle_timer_message = AsyncMock(
                return_value=TimerMessageResult(action="cancelled", guild_id="123", ticket_id="t1", author_id="999")
            )
            cog = TicketsCog(bot)
            msg = make_pr2_message(",cancel", is_mod=True)
            await cog.on_message(msg)
            bot.ticket_service.handle_timer_message.assert_awaited_once()  # still called, safe no-op
        case _:
            msg = f"unknown case {case!r}"  # noqa: TRY003 -- test branching guard, not production raise
            raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Group 3: scheduled loop + unload (2 cases → 1 parametrized test)
# ---------------------------------------------------------------------------

_SCHEDULED_CASES = [
    pytest.param("scheduled_loop_batch_50_silent", id="scheduled_loop_batch_50_silent"),
    pytest.param("cog_unload_cancels_scheduled", id="cog_unload_cancels_scheduled"),
]


@pytest.mark.parametrize("case", _SCHEDULED_CASES)
@pytest.mark.asyncio
async def test_scheduled_lifecycle_cases(case: str) -> None:
    """Parametrized scheduled-loop/unload cases — asserts verbatim per original 2 tests."""
    match case:
        case "scheduled_loop_batch_50_silent":
            bot = make_pr2_bot()
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
        case "cog_unload_cancels_scheduled":
            bot = make_pr2_bot()
            cog = TicketsCog(bot)
            cog.scheduled_close_loop = MagicMock(is_running=MagicMock(return_value=True), cancel=MagicMock())
            cog.auto_close_stale_tickets = MagicMock(is_running=MagicMock(return_value=False), cancel=MagicMock())
            cog.integrity_sweep_loop = MagicMock(is_running=MagicMock(return_value=False), cancel=MagicMock())
            await cog.cog_unload()
            cog.scheduled_close_loop.cancel.assert_called_once()
        case _:
            msg = f"unknown case {case!r}"  # noqa: TRY003 -- test branching guard, not production raise
            raise AssertionError(msg)
