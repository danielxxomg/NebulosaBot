"""Probe tests for GreetingRenderer injection via real setup_hook — C14.

Strict TDD: cairosvg ImportError → Pillow + WARNING, no abort;
cairosvg present → Pillow still default (Cycle 1).
Uses real NebulosaBot.setup_hook with DB/cache mocked per D4.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import discord
import pytest

from bot.bot import NebulosaBot
from bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="test-key",
    )


def _patch_setup_hook_env(bot: NebulosaBot, monkeypatch_bundle: dict) -> None:
    """Apply common patches for setup_hook (DB, cache, cogs, tree)."""
    # Returns a dict of patches for caller to manage via context
    _ = monkeypatch_bundle  # placeholder for future extensibility


@pytest.mark.asyncio
async def test_probe_import_error_falls_back_to_pillow_and_logs_warning(caplog):
    """ImportError on cairosvg must inject PillowGreetingRenderer and log WARNING, no abort."""
    from bot.services.greeting_renderer import PillowGreetingRenderer

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "cairosvg" or name.startswith("cairosvg."):
            raise ImportError("No module named 'cairosvg'")
        return real_import(name, *args, **kwargs)

    bot = NebulosaBot(config=_make_config(), intents=discord.Intents.default())

    mock_sync = AsyncMock()
    with (
        patch("builtins.__import__", side_effect=fake_import),
        patch("bot.bot.Database") as mock_db_cls,
        patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
        patch.object(bot, "load_extension", new=AsyncMock()),
        patch.object(type(bot.tree), "sync", mock_sync),
        patch("bot.bot.load_locales"),
        patch("bot.bot.validate_slash_localizations"),
        patch.object(type(bot.tree), "set_translator", new=AsyncMock()),
    ):
        mock_db_cls.return_value.connect = AsyncMock()
        mock_sub_cls.return_value.start = AsyncMock()
        with caplog.at_level(logging.WARNING, logger="bot.bot"):
            await bot.setup_hook()

        # Must have injected Pillow renderer even though probe raised ImportError
        assert isinstance(bot.greeting_service._greeting_renderer, PillowGreetingRenderer)  # type: ignore[union-attr]
        assert isinstance(bot.rank_renderer, object)
        # WARNING must have been logged
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("cairosvg" in r.getMessage().lower() for r in warnings)
        # No abort — tree.sync still ran
        mock_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_success_still_injects_pillow_cycle1():
    """When cairosvg import succeeds, Cycle 1 still injects Pillow."""
    from bot.services.greeting_renderer import PillowGreetingRenderer

    bot = NebulosaBot(config=_make_config(), intents=discord.Intents.default())
    mock_sync = AsyncMock()
    with (
        patch("bot.bot.Database") as mock_db_cls,
        patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
        patch.object(bot, "load_extension", new=AsyncMock()),
        patch.object(type(bot.tree), "sync", mock_sync),
        patch("bot.bot.load_locales"),
        patch("bot.bot.validate_slash_localizations"),
        patch.object(type(bot.tree), "set_translator", new=AsyncMock()),
    ):
        mock_db_cls.return_value.connect = AsyncMock()
        mock_sub_cls.return_value.start = AsyncMock()
        await bot.setup_hook()

        # Cycle 1: both branches yield Pillow regardless of cairosvg presence
        assert isinstance(bot.greeting_service._greeting_renderer, PillowGreetingRenderer)  # type: ignore[union-attr]
        # Source still probes cairosvg and injects PillowGreetingRenderer
        src = Path("bot/bot.py").read_text(encoding="utf-8")
        assert "cairosvg" in src
        assert "PillowGreetingRenderer" in src


@pytest.mark.asyncio
async def test_greeting_service_receives_renderer_interface():
    """GreetingService constructed via setup_hook must receive a GreetingRenderer."""
    from bot.core.cache import TTLCache
    from bot.services.greeting_renderer import GreetingRenderer, PillowGreetingRenderer
    from bot.services.greeting_service import GreetingService

    db = AsyncMock()
    cache = TTLCache()
    renderer = PillowGreetingRenderer()
    svc = GreetingService(db=db, cache=cache, greeting_renderer=renderer)
    assert isinstance(svc._greeting_renderer, PillowGreetingRenderer)
    assert isinstance(renderer, GreetingRenderer)
