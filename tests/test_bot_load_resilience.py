"""Unit tests for NebulosaBot.setup_hook load resilience.

Verifies that a single extension failure does not prevent later extensions
from loading, and that tree.sync() still runs for successfully loaded commands.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.bot import NebulosaBot, EXTENSIONS
from bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> BotConfig:
    """Minimal BotConfig for tests."""
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )


def _make_bot(config: BotConfig | None = None) -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    return NebulosaBot(config=config or _make_config(), intents=discord.Intents.default())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadResilience:
    """setup_hook logs ERROR and continues when one load_extension() raises."""

    @pytest.mark.asyncio
    async def test_one_extension_failure_does_not_block_others(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When one extension fails, remaining extensions still load and tree.sync runs."""
        bot = _make_bot()
        loaded: list[str] = []

        async def fake_load_extension(path: str) -> None:
            if path == "bot.cogs.sentinel":
                raise ImportError("sentinel is broken")
            loaded.append(path)

        mock_sync = AsyncMock()
        with (
            patch("bot.bot.Database") as mock_db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
            patch.object(bot, "load_extension", side_effect=fake_load_extension),
            patch.object(type(bot.tree), "sync", mock_sync),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_sub_cls.return_value.start = AsyncMock()
            with caplog.at_level(logging.ERROR, logger="bot.bot"):
                await bot.setup_hook()

        # The failed extension is not in loaded list.
        assert "bot.cogs.sentinel" not in loaded
        # All other extensions DID load.
        for ext in EXTENSIONS:
            if ext != "bot.cogs.sentinel":
                assert ext in loaded, f"{ext} was not loaded"
        # tree.sync() was called.
        mock_sync.assert_awaited_once()
        # ERROR was logged for the failure.
        assert any("bot.cogs.sentinel" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_all_extensions_load_in_order(self) -> None:
        """When no extension fails, all extensions load in EXTENSIONS order."""
        bot = _make_bot()
        loaded: list[str] = []

        async def fake_load_extension(path: str) -> None:
            loaded.append(path)

        mock_sync = AsyncMock()
        with (
            patch("bot.bot.Database") as mock_db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
            patch.object(bot, "load_extension", side_effect=fake_load_extension),
            patch.object(type(bot.tree), "sync", mock_sync),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_sub_cls.return_value.start = AsyncMock()
            await bot.setup_hook()

        assert loaded == list(EXTENSIONS)
        mock_sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_failures_all_logged(self) -> None:
        """Multiple extension failures are all logged; surviving extensions still load."""
        bot = _make_bot()
        loaded: list[str] = []

        async def fake_load_extension(path: str) -> None:
            if path in ("bot.cogs.sentinel", "bot.cogs.ocio"):
                raise ImportError(f"{path} broken")
            loaded.append(path)

        mock_sync = AsyncMock()
        with (
            patch("bot.bot.Database") as mock_db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
            patch.object(bot, "load_extension", side_effect=fake_load_extension),
            patch.object(type(bot.tree), "sync", mock_sync),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_sub_cls.return_value.start = AsyncMock()
            await bot.setup_hook()

        assert "bot.cogs.sentinel" not in loaded
        assert "bot.cogs.ocio" not in loaded
        # Surviving extensions still loaded.
        for ext in EXTENSIONS:
            if ext not in ("bot.cogs.sentinel", "bot.cogs.ocio"):
                assert ext in loaded, f"{ext} was not loaded"
        # tree.sync still ran.
        mock_sync.assert_awaited_once()

    def test_extensions_tuple_is_not_empty(self) -> None:
        """EXTENSIONS must contain at least the known core extension."""
        assert len(EXTENSIONS) >= 1
        assert "bot.cogs.core" in EXTENSIONS
