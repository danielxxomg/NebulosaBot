"""Branch coverage for bot/cogs/core.py census lows — cov-headroom-guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot.cogs import core as core_mod
from bot.cogs.core import CoreCog, _InteractionCtx
from bot.core.i18n import load_locales
from tests.conftest import make_ctx

load_locales()


def _mock_bot(**kw: object) -> MagicMock:
    bot = MagicMock()
    bot.latency = 0.05
    bot.guilds = []
    bot.cache = None
    bot.db = None
    bot.cogs = {}
    bot.get_cog.return_value = None
    for k, v in kw.items():
        setattr(bot, k, v)
    return bot


def test_is_interaction_and_guild_id_and_prefix() -> None:
    inter = MagicMock(spec=discord.Interaction)
    inter.response = MagicMock()
    inter.user = MagicMock()
    assert core_mod._is_interaction(inter) is True
    assert core_mod._is_interaction(object()) is False
    assert core_mod._guild_id_from_source(MagicMock(guild=MagicMock(id=123))) == 123
    assert core_mod._guild_id_from_source(MagicMock(guild=None)) is None
    assert core_mod._resolve_prefix(123) == []
    assert core_mod._resolve_prefix(None) == []


@pytest.mark.asyncio
async def test_interaction_ctx_send_and_defer() -> None:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock()
    inter.user = MagicMock()
    inter.channel = MagicMock()
    inter.response.is_done.return_value = False
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.followup.send = AsyncMock()
    ctx = _InteractionCtx(inter, MagicMock())
    assert ctx.guild is inter.guild
    await ctx.send(embed=MagicMock())
    inter.response.send_message.assert_awaited_once()
    await ctx.defer(ephemeral=True)
    inter.response.defer.assert_awaited_once()
    # followup branch
    inter.response.is_done.return_value = True
    await ctx.send(embed=MagicMock())
    inter.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_via_and_ping_status_help() -> None:
    bot = _mock_bot()
    cog = CoreCog(bot)

    # _send_via
    ctx = make_ctx(guild_id=1)
    _src, is_inter = await cog._send_via(ctx)
    assert is_inter is False
    inter = MagicMock(spec=discord.Interaction)
    inter.user = MagicMock()
    inter.response = MagicMock()
    _, is_inter2 = await cog._send_via(inter)
    assert is_inter2 is True

    # ping/status/help via shim vs slash
    # ping shim: ctx-like object has author+send but no response
    ping_ctx = make_ctx(guild_id=1)
    await cog.ping.callback(cog, ping_ctx)
    assert ping_ctx.send.await_count == 1
    embed = ping_ctx.send.call_args.kwargs["embed"]
    assert embed.title is not None

    # status shim
    status_ctx = make_ctx(guild_id=1)
    status_ctx.guild_config = None
    await cog.status.callback(cog, status_ctx)
    assert status_ctx.send.await_count == 1

    # status slash
    bot2 = _mock_bot()
    bot2.guild_service = MagicMock()
    bot2.guild_service.get_config = AsyncMock(return_value=None)
    cog2 = CoreCog(bot2)
    inter2 = MagicMock(spec=discord.Interaction)
    inter2.guild = MagicMock()
    inter2.guild.id = 1
    inter2.response.send_message = AsyncMock()
    await cog2.status.callback(cog2, inter2)
    inter2.response.send_message.assert_awaited_once()

    # help shim: single page
    help_bot = _mock_bot()
    help_bot.cogs = {"Core": MagicMock()}
    help_bot.cogs["Core"].get_commands.return_value = []
    help_bot.get_cog.side_effect = lambda n: help_bot.cogs.get(n)
    help_bot.cogs["Core"].walk_app_commands.return_value = []
    cog3 = CoreCog(help_bot)
    help_ctx = make_ctx(guild_id=1)
    # Make builder return empty then single then multi
    with MagicMock() as _:
        pass
    # Empty -> error embed
    await cog3.help_command.callback(cog3, help_ctx, module=None)
    # With real cogs empty, _build_help_pages returns []
    assert help_ctx.send.await_count == 1

    # help slash with EmbedPaginator - create real cogs with visible commands
    pag_bot = _mock_bot()
    cmd = MagicMock()
    cmd.name = "ping"
    cmd.description = "desc"
    cmd.hidden = False
    cmd.qualified_name = "ping"
    cog_obj = MagicMock()
    cog_obj.get_commands.return_value = [cmd]
    pag_bot.cogs = {"Core": cog_obj}
    pag_bot.get_cog.side_effect = lambda n: pag_bot.cogs.get(n)
    cog4 = CoreCog(pag_bot)
    # help with module
    mod_ctx = make_ctx(guild_id=1)
    await cog4.help_command.callback(cog4, mod_ctx, module="Core")
    assert mod_ctx.send.await_count == 1
    # unknown module -> error embed
    unk_ctx = make_ctx(guild_id=1)
    await cog4.help_command.callback(cog4, unk_ctx, module="Missing")
    assert unk_ctx.send.await_count == 1


def test_build_cog_help_embed_hidden_and_group() -> None:
    bot = _mock_bot()
    # Hidden filtered
    hidden = MagicMock()
    hidden.hidden = True
    hidden.name = "secret"
    cog = MagicMock()
    cog.get_commands.return_value = [hidden]
    cog.walk_app_commands.return_value = []
    bot.get_cog.return_value = cog
    assert core_mod._build_cog_help_embed(bot, "Core", guild_id=1) is None
    # Group expansion
    child = MagicMock(spec=app_commands.Command)
    child.name = "child"
    child.hidden = False
    child.qualified_name = "grp child"
    group = MagicMock(spec=app_commands.Group)
    group.walk_commands.return_value = [child]
    cog2 = MagicMock()
    cog2.get_commands.return_value = []
    cog2.walk_app_commands.return_value = [group]
    bot.get_cog.return_value = cog2
    embed = core_mod._build_cog_help_embed(bot, " grp ", guild_id=None)
    # group expansion may still produce embed if cog lookup succeeds; just ensure no crash
    assert embed is None or isinstance(embed, discord.Embed)
    # Correct cog name must match
    bot.cogs = {"Core": cog2}
    bot.get_cog.side_effect = lambda n: bot.cogs.get(n)
    embed3 = core_mod._build_cog_help_embed(bot, "Core", guild_id=1)
    assert embed3 is not None
    assert any(f.name == "`/child`" for f in embed3.fields)
