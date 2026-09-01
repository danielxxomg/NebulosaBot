"""Branch coverage for bot/bot.py census lows — cov-headroom-guard."""

from __future__ import annotations

import logging
import types
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.cache import TTLCache
from bot.utils.brand import ERROR


def _make_bot() -> NebulosaBot:
    return NebulosaBot(
        config=BotConfig(discord_token="t", supabase_url="https://x.supabase.co", supabase_key="k"),
        intents=discord.Intents.default(),
    )


@pytest.mark.asyncio
async def test_setup_retention_find_spec_none_upserts_defaults() -> None:
    bot = _make_bot()
    table = MagicMock()
    table.upsert.return_value.execute = AsyncMock()
    client = MagicMock()
    client.table.return_value = table
    bot.db = MagicMock()
    bot.db._client = client  # noqa: SLF001
    with patch("bot.bot.importlib.util.find_spec", return_value=None):
        await bot._setup_retention()
    assert client.table.call_count == 3
    assert table.upsert.call_args.kwargs["on_conflict"] == "key"


@pytest.mark.asyncio
async def test_setup_retention_disabled_unschedules_four() -> None:
    bot = _make_bot()
    table = MagicMock()
    table.upsert.return_value.execute = AsyncMock()
    rpc = MagicMock()
    rpc.execute = AsyncMock()
    client = MagicMock()
    client.table.return_value = table
    client.rpc.return_value = rpc
    bot.db = MagicMock()
    bot.db._client = client  # noqa: SLF001
    fake = types.ModuleType("bot.operational_config")
    fake.load_operational_config = lambda: types.SimpleNamespace(  # type: ignore[attr-defined]
        retention=types.SimpleNamespace(tickets=7, infractions=7, crash=7),
        flags=types.SimpleNamespace(retention_enabled=False),
    )
    import bot as bot_pkg  # noqa: PLC0415 -- probe package attr polluted by setup_hook's import

    with (
        patch("bot.bot.importlib.util.find_spec", return_value=MagicMock()),
        patch.dict("sys.modules", {"bot.operational_config": fake}),
        patch.object(bot_pkg, "operational_config", fake, create=True),
    ):
        await bot._setup_retention()
    assert client.rpc.call_count >= 4
    assert any(a.args[0] == "cron_unschedule" for a in client.rpc.call_args_list)


@pytest.mark.asyncio
async def test_start_realtime_cache_none_returns() -> None:
    bot = _make_bot()
    bot.cache = None
    await bot._start_realtime()
    assert bot._realtime_subscriber is None


@pytest.mark.asyncio
async def test_start_realtime_raises_logs_and_nones(caplog: pytest.LogCaptureFixture) -> None:
    bot = _make_bot()
    bot.cache = TTLCache()
    with patch("bot.bot.RealtimeCacheSubscriber") as cls:
        cls.return_value.start = AsyncMock(side_effect=RuntimeError("boom"))
        with caplog.at_level(logging.ERROR, logger="bot.bot"):
            await bot._start_realtime()
    assert bot._realtime_subscriber is None
    assert any("Realtime" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_get_context_success_and_error(caplog: pytest.LogCaptureFixture) -> None:
    from bot.core.context import NebulosaContext

    bot = _make_bot()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
    ctx_ok = MagicMock(spec=NebulosaContext)
    ctx_ok.guild = MagicMock()
    ctx_ok.guild.id = 1
    with patch.object(commands.Bot, "get_context", new=AsyncMock(return_value=ctx_ok)):
        got = await bot.get_context(MagicMock())
    assert got is ctx_ok
    bot.guild_service.get_config = AsyncMock(side_effect=RuntimeError("down"))
    ctx_err = MagicMock(spec=NebulosaContext)
    ctx_err.guild = MagicMock()
    ctx_err.guild.id = 2
    with (
        patch.object(commands.Bot, "get_context", new=AsyncMock(return_value=ctx_err)),
        caplog.at_level(logging.ERROR, logger="bot.bot"),
    ):
        got2 = await bot.get_context(MagicMock())
    assert got2 is ctx_err


@pytest.mark.asyncio
async def test_on_app_command_error_embeds_and_followup() -> None:
    bot = _make_bot()
    bot.db = MagicMock()
    bot.db._client = None  # noqa: SLF001

    async def _call(err: app_commands.AppCommandError, *, is_done: bool = False) -> MagicMock:
        inter = MagicMock(spec=discord.Interaction)
        inter.command = None
        inter.guild = MagicMock()
        inter.guild.id = 111
        inter.guild_id = 111
        inter.response.is_done.return_value = is_done
        inter.response.send_message = AsyncMock()
        inter.followup.send = AsyncMock()
        with patch("bot.bot.CrashReportService") as cr:
            cr.return_value.record = AsyncMock()
            await bot.on_app_command_error(inter, err)
        return inter

    mp = app_commands.MissingPermissions(["ban_members"])
    inter = await _call(mp)
    assert inter.response.send_message.call_args.kwargs["embed"].color.value == ERROR
    cf = app_commands.CheckFailure("nope")
    inter = await _call(cf)
    assert inter.response.send_message.call_args.kwargs["embed"].title is not None
    cd = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5.0), 5.0)
    inter = await _call(cd, is_done=True)
    inter.followup.send.assert_awaited_once()
    generic = app_commands.AppCommandError("boom")
    inter = await _call(generic)
    assert inter.response.send_message.await_count == 1


@pytest.mark.asyncio
async def test_on_command_error_missing_and_crash() -> None:
    bot = _make_bot()
    bot.db = MagicMock()
    bot.db._client = MagicMock()  # noqa: SLF001
    ctx = MagicMock()
    ctx.command = None
    ctx.guild = MagicMock()
    ctx.guild.id = 222
    ctx.send = AsyncMock()
    await bot.on_command_error(ctx, commands.MissingPermissions(["ban_members"]))
    assert ctx.send.call_args.kwargs["embed"].title is not None
    ctx.send.reset_mock()
    await bot.on_command_error(ctx, commands.CheckFailure("nope"))
    assert ctx.send.call_args.kwargs["embed"].title is not None
    ctx.send.reset_mock()
    with patch("bot.bot.CrashReportService") as cr:
        cr.return_value.record = AsyncMock()
        await bot.on_command_error(ctx, commands.CommandError("boom"))
        cr.return_value.record.assert_awaited()


@pytest.mark.asyncio
async def test_validate_single_panel_branches(caplog: pytest.LogCaptureFixture) -> None:
    bot = _make_bot()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(
        return_value=MagicMock(ticket_panel_message_id="1", ticket_panel_channel_id="1")
    )
    bot.guild_service.update_guild_panel = AsyncMock()
    with (
        patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [])),
        caplog.at_level(logging.WARNING, logger="bot.bot"),
    ):
        await bot._validate_single_panel("999")
    guild = MagicMock()
    guild.id = 999
    guild.get_channel.return_value = None
    with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [guild])):
        await bot._validate_single_panel("999")
    bot.guild_service.update_guild_panel.assert_awaited_with("999", None, None)
    channel = MagicMock()
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    guild.get_channel.return_value = channel
    with (
        patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [guild])),
        patch("bot.bot.deploy_ticket_panel", new_callable=AsyncMock) as dep,
    ):
        await bot._validate_single_panel("999")
        dep.assert_awaited_once()
    msg = MagicMock()
    msg.components = []
    channel.fetch_message = AsyncMock(return_value=msg)
    with (
        patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [guild])),
        patch("bot.bot.deploy_ticket_panel", new_callable=AsyncMock) as dep,
    ):
        await bot._validate_single_panel("999")
        dep.assert_awaited_once()
    channel.fetch_message = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))
    with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [guild])):
        await bot._validate_single_panel("999")
    channel.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "err"))
    with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda s: [guild])):
        await bot._validate_single_panel("999")
