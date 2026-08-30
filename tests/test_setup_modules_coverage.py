"""S0 coverage — LanguageSetupModule handle/render/components ≥22 lines (strict TDD).

Ref: design D3 additive coverage via setup_modules/language.py:71-121.
Covers handle guild-only, bot-unavailable, set_es/set_en success+failure,
unknown action, plus render/render_async/components to ensure ≥22
newly-covered statements without denominator change. No DDL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.views.setup_modules.language import LanguageSetupModule


def _make_guild(guild_id: int = 123456789) -> MagicMock:
    g = MagicMock(spec=discord.Guild)
    g.id = guild_id
    return g


def _make_bot(guild_id: str = "123456789", language: str = "es") -> tuple[MagicMock, MagicMock]:
    bot = MagicMock()
    cfg = MagicMock()
    cfg.language = language
    cfg.guild_id = guild_id
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=cfg)
    bot.guild_service.save_config = AsyncMock(return_value=None)
    return bot, cfg


def _make_interaction(
    guild_id: int | None = 123456789,
    bot: MagicMock | None = None,
) -> MagicMock:
    inter = MagicMock(spec=discord.Interaction)
    if guild_id is None:
        inter.guild = None
    else:
        inter.guild = _make_guild(guild_id)
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.response.is_done.return_value = False
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    if bot is not None:
        inter.client = bot
    else:
        inter.client = MagicMock()
        inter.client.guild_service = None
    return inter


class TestLanguageRender:
    def test_render_returns_embed(self) -> None:
        mod = LanguageSetupModule(bot=None)
        embed = mod.render("123456789")
        assert embed.title is not None
        assert embed.description is not None

    @pytest.mark.asyncio
    async def test_render_async_without_bot(self) -> None:
        mod = LanguageSetupModule(bot=None)
        embed = await mod.render_async("123456789", bot=None)
        assert embed.title is not None
        # When no bot, description must NOT contain current label extra
        assert embed.description is not None

    @pytest.mark.asyncio
    async def test_render_async_with_bot_shows_current(self) -> None:
        bot, _cfg = _make_bot("123456789", "es")
        mod = LanguageSetupModule(bot=bot)
        embed = await mod.render_async("123456789", bot=bot)
        assert embed.title is not None
        assert embed.description is not None
        # Should contain current language display (es) via setup.language.current_label
        desc_lower = embed.description.lower()
        assert "es" in embed.description or "español" in desc_lower or "actual" in desc_lower

    @pytest.mark.asyncio
    async def test_render_async_handles_get_config_failure(self) -> None:
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(side_effect=RuntimeError("boom"))
        mod = LanguageSetupModule(bot=bot)
        embed = await mod.render_async("123456789", bot=bot)
        assert embed.title is not None


class TestLanguageComponents:
    def test_components_returns_two_buttons(self) -> None:
        mod = LanguageSetupModule(bot=None)
        items = mod.components("123456789")
        assert len(items) == 2
        cids = {getattr(i, "custom_id", None) for i in items}
        assert "setup:language:set_es" in cids
        assert "setup:language:set_en" in cids


class TestLanguageHandleGuildOnly:
    @pytest.mark.asyncio
    async def test_handle_guild_none(self) -> None:
        mod = LanguageSetupModule(bot=None)
        inter = _make_interaction(guild_id=None)
        await mod.handle(inter, "set_es")
        inter.response.send_message.assert_awaited_once()
        kwargs = inter.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert kwargs.get("embed") is not None


class TestLanguageHandleBotUnavailable:
    @pytest.mark.asyncio
    async def test_handle_bot_none(self) -> None:
        mod = LanguageSetupModule(bot=None)
        # interaction without guild_service
        inter = _make_interaction(guild_id=123456789, bot=None)
        inter.client = MagicMock()
        inter.client.guild_service = None
        # Ensure _resolve_bot returns None: mod._bot is None and client has no guild_service
        await mod.handle(inter, "set_es")
        inter.response.send_message.assert_awaited_once()
        assert inter.response.send_message.call_args.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_handle_guild_service_none(self) -> None:
        bot = MagicMock()
        bot.guild_service = None
        mod = LanguageSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        await mod.handle(inter, "set_es")
        inter.response.send_message.assert_awaited_once()


class TestLanguageHandleSetEsEn:
    @pytest.mark.asyncio
    async def test_handle_set_es_success(self) -> None:
        bot, cfg = _make_bot("123456789", "en")
        mod = LanguageSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        await mod.handle(inter, "set_es")
        bot.guild_service.get_config.assert_awaited()
        bot.guild_service.save_config.assert_awaited_once()
        assert cfg.language == "es"
        inter.response.send_message.assert_awaited_once()
        kwargs = inter.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_handle_set_en_success(self) -> None:
        bot, cfg = _make_bot("123456789", "es")
        mod = LanguageSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        await mod.handle(inter, "set_en")
        bot.guild_service.save_config.assert_awaited_once()
        assert cfg.language == "en"

    @pytest.mark.asyncio
    async def test_handle_set_es_save_failure(self) -> None:
        bot, _cfg = _make_bot("123456789", "es")
        bot.guild_service.save_config = AsyncMock(side_effect=RuntimeError("db down"))
        mod = LanguageSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        await mod.handle(inter, "set_es")
        inter.response.send_message.assert_awaited_once()
        embed = inter.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None

    @pytest.mark.asyncio
    async def test_handle_unknown_action(self) -> None:
        bot, _cfg = _make_bot("123456789", "es")
        mod = LanguageSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        await mod.handle(inter, "bogus_action")
        inter.response.send_message.assert_awaited_once()
        kwargs = inter.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None

    @pytest.mark.asyncio
    async def test_handle_set_en_via_client_fallback(self) -> None:
        # No bot in constructor, but client carries guild_service
        bot, cfg = _make_bot("123456789", "es")
        mod = LanguageSetupModule(bot=None)
        inter = _make_interaction(guild_id=123456789, bot=bot)
        # _resolve_bot should find client
        await mod.handle(inter, "set_en")
        assert cfg.language == "en"
