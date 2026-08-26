"""Cache eviction on guild remove (cache-layer delta — S0.9/S0.10).

When the bot leaves guild G, EVERY ``{G}:*`` key MUST be evicted in one
pass, other guilds' entries MUST survive, and a post-eviction read for G
MUST miss. The guild-scoped mod-role RAM map and greeting raid semaphores
are evicted in the same pass (proposal S0 quick wins).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import discord
import pytest

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.cache import TTLCache, cache_key
from bot.services.greeting_service import GreetingService


def _make_bot_with_cache() -> tuple[NebulosaBot, TTLCache]:
    config = BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )
    bot = NebulosaBot(config=config, intents=discord.Intents.default())
    cache = TTLCache()
    bot.cache = cache
    return bot, cache


def _make_guild(guild_id: int) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    return guild


# ===========================================================================
# TTLCache.invalidate_guild — hit/miss/other-guild semantics
# ===========================================================================


class TestInvalidateGuildSemantics:
    def test_evicts_every_guild_key_in_one_pass(self) -> None:
        cache = TTLCache()
        for entity in ("config", "greeting_config", "ticket_panel"):
            cache.set(cache_key("42", entity), {"entity": entity})
        cache.set(cache_key("43", "config"), {"other": "guild"})

        cache.invalidate_guild("42")

        assert cache.get(cache_key("42", "config")) is None
        assert cache.get(cache_key("42", "greeting_config")) is None
        assert cache.get(cache_key("42", "ticket_panel")) is None

    def test_other_guilds_unaffected(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("42", "config"), {"g": 42})
        cache.set(cache_key("43", "config"), {"g": 43})

        cache.invalidate_guild("42")

        assert cache.get(cache_key("43", "config")) == {"g": 43}, "guild B entries must remain valid"

    def test_post_eviction_read_misses(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("42", "config"), {"stale": True})

        cache.invalidate_guild("42")

        assert cache.get(cache_key("42", "config")) is None, "no stale value may be served after eviction"


# ===========================================================================
# Wiring — NebulosaBot.on_guild_remove evicts everything guild-scoped
# ===========================================================================


class TestOnGuildRemoveWiring:
    @pytest.mark.asyncio
    async def test_on_guild_remove_evicts_cache_and_mod_role_map(self) -> None:
        bot, cache = _make_bot_with_cache()
        cache.set(cache_key("42", "config"), {"x": 1})
        cache.set(cache_key("43", "config"), {"y": 2})
        bot._guild_mod_role_cache[42] = "role-1"

        await bot.on_guild_remove(_make_guild(42))

        assert cache.get(cache_key("42", "config")) is None
        assert cache.get(cache_key("43", "config")) == {"y": 2}
        assert 42 not in bot._guild_mod_role_cache

    @pytest.mark.asyncio
    async def test_on_guild_remove_evicts_greeting_raid_semaphores(self) -> None:
        bot, _cache = _make_bot_with_cache()
        greeting_service = MagicMock()
        greeting_service.evict_guild_sync = MagicMock()
        bot.greeting_service = greeting_service

        await bot.on_guild_remove(_make_guild(77))

        greeting_service.evict_guild_sync.assert_called_once_with("77")


# ===========================================================================
# GreetingService.evict_guild — semaphore map cleanup helper
# ===========================================================================


class TestGreetingSemaphoreEviction:
    def test_evict_guild_drops_only_that_guilds_semaphore(self) -> None:
        service = GreetingService.__new__(GreetingService)  # skip heavy __init__
        service._raid_semaphores = {
            "42": asyncio.Semaphore(2),
            "43": asyncio.Semaphore(2),
        }

        service.evict_guild_sync("42")

        assert "42" not in service._raid_semaphores
        assert "43" in service._raid_semaphores

    def test_evict_unknown_guild_is_noop(self) -> None:
        service = GreetingService.__new__(GreetingService)
        service._raid_semaphores = {}

        service.evict_guild_sync("999")  # must not raise
