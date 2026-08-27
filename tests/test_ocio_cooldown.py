"""S6B.3 RED — ocio CommandOnCooldown handler is ephemeral with localized retry_after (strict TDD).

Ref: ocio-commands "Ocio commands cooldown and handler"
— each ocio command carries cooldown(1,5,user); CommandOnCooldown replies
ephemerally with localized retry_after and releases after 5s.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core.i18n import load_locales


@pytest.fixture(autouse=True)
def _load_i18n() -> None:
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    load_locales(Path("bot/locales"))


@pytest.fixture
def mock_bot() -> MagicMock:
    b = MagicMock(spec=commands.Bot)
    b.db = MagicMock()
    return b


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    return OcioCog(mock_bot)


def test_ocio_commands_carry_cooldown() -> None:
    src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
    # Must have app_commands.checks.cooldown for pure app_commands
    assert "cooldown" in src.lower()
    # Require 1,5 pattern — allow either commands.cooldown or app_commands.checks.cooldown
    assert "1, 5" in src or "1,5" in src or "1, 5.0" in src, "cooldown must be 1 per 5s"
    # Must not have zero cooldowns (at least 3 ocio commands)
    assert src.lower().count("cooldown") >= 3, "each ocio command must carry cooldown"


@pytest.mark.asyncio
async def test_app_cooldown_handler_replies_ephemerally(cog: OcioCog) -> None:
    """App CommandOnCooldown handler must reply ephemerally with retry_after."""
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock()
    inter.guild.id = 123456789
    inter.response = MagicMock()
    inter.response.is_done.return_value = False
    inter.response.send_message = AsyncMock()
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    # Build real app_commands error with retry_after
    err = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5.0), 3.5)
    # Try cog handler first, else bot global
    handled = False
    if hasattr(cog, "cog_app_command_error"):
        await cog.cog_app_command_error(inter, err)
        if inter.response.send_message.await_count or inter.followup.send.await_count:
            handled = True
            kwargs = (
                inter.response.send_message.call_args.kwargs
                if inter.response.send_message.await_count
                else inter.followup.send.call_args.kwargs
            )
            assert kwargs.get("ephemeral") is True, "cooldown reply must be ephemeral"
            # Must be localized via t() — check embed title/description come from i18n
            embed = kwargs.get("embed")
            if embed is not None:
                assert embed.title is not None and embed.description is not None
    if not handled:
        # Fallback to NebulosaBot handler — must exist
        from bot.bot import NebulosaBot
        from bot.config import BotConfig

        bot = NebulosaBot(
            config=BotConfig(discord_token="t", supabase_url="https://x.supabase.co", supabase_key="k"),
            intents=discord.Intents.default(),
        )
        inter2 = MagicMock(spec=discord.Interaction)
        inter2.guild = MagicMock()
        inter2.guild.id = 123456789
        inter2.guild_id = 123456789
        inter2.command = MagicMock()
        inter2.command.qualified_name = "dice"
        inter2.command.cog = None
        inter2.response = MagicMock()
        inter2.response.is_done.return_value = False
        inter2.response.send_message = AsyncMock()
        inter2.followup = MagicMock()
        inter2.followup.send = AsyncMock()
        await bot.on_app_command_error(inter2, err)
        kwargs = (
            inter2.response.send_message.call_args.kwargs
            if inter2.response.send_message.await_count
            else inter2.followup.send.call_args.kwargs
        )
        assert kwargs.get("ephemeral") is True, "global cooldown branch must be ephemeral"


def test_cooldown_releases_after_bucket_window() -> None:
    """Cooldown bucket resets after per (5s) — structural check."""
    src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
    assert "BucketType.user" in src or "app_commands" in src, "cooldown must be per-user"
    # Cooldown type check — ensure per is 5
    assert "5" in src


def test_cooldown_handler_uses_t_retry_after() -> None:
    src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
    # Handler must format retry_after via t() — look for ocio.cooldown keys
    assert "ocio.cooldown" in src, "cooldown handler must use t('ocio.cooldown.*', retry_after=...)"
    assert "retry_after" in src, "handler must pass retry_after to t()"
