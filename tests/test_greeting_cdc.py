"""RED tests for greeting_config CDC invalidation covering theme_id (PR1 5.2).

The existing Realtime subscription to ``greeting_config`` already calls
``invalidate_guild(guild_id)``, which drops the entire ``{guild_id}:*`` prefix —
so ``{guild_id}:greeting_config`` and ``{guild_id}:greeting_avatar`` are
invalidated for free when a ``themeId`` change arrives via CDC.  No new
invalidation wiring is needed.

These tests guard that contract behaviorally: a greeting_config CDC event
invalidates both the config and avatar cache entries.
"""

from __future__ import annotations

import pytest

from bot.core.cache import TTLCache, cache_key
from bot.core.realtime import RealtimeCacheSubscriber


def _make_subscriber(cache: TTLCache) -> RealtimeCacheSubscriber:
    from unittest.mock import AsyncMock, MagicMock

    return RealtimeCacheSubscriber(
        supabase_url="https://x.supabase.co",
        supabase_key="k",
        cache=cache,
        client_factory=AsyncMock(return_value=MagicMock()),
    )


class TestGreetingConfigCdcInvalidatesThemeId:
    """5.2 — greeting_config CDC drops config + avatar caches (themeId change)."""

    @pytest.mark.asyncio
    async def test_greeting_config_cdc_drops_config_and_avatar(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("G1", "greeting_config"), "cfg", ttl=300)
        cache.set(cache_key("G1", "greeting_avatar"), "url", ttl=60)

        sub = _make_subscriber(cache)
        payload = {
            "data": {
                "type": "UPDATE",
                "table": "greeting_config",
                "schema": "public",
                "record": {"guildId": "G1", "themeId": "gaming_neon"},
                "old_record": {},
            },
            "ids": [1],
        }
        await sub._handle_cdc(payload)

        assert cache.get(cache_key("G1", "greeting_config")) is None
        assert cache.get(cache_key("G1", "greeting_avatar")) is None

    @pytest.mark.asyncio
    async def test_greeting_config_cdc_does_not_touch_other_guild(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("G1", "greeting_config"), "cfg", ttl=300)
        cache.set(cache_key("G1", "greeting_avatar"), "url", ttl=60)
        cache.set(cache_key("G2", "greeting_config"), "cfg2", ttl=300)
        cache.set(cache_key("G2", "greeting_avatar"), "url2", ttl=60)

        sub = _make_subscriber(cache)
        payload = {
            "data": {
                "type": "UPDATE",
                "table": "greeting_config",
                "schema": "public",
                "record": {"guildId": "G1", "themeId": "gaming_neon"},
                "old_record": {},
            },
            "ids": [1],
        }
        await sub._handle_cdc(payload)

        # G1 dropped, G2 untouched.
        assert cache.get(cache_key("G1", "greeting_config")) is None
        assert cache.get(cache_key("G1", "greeting_avatar")) is None
        assert cache.get(cache_key("G2", "greeting_config")) == "cfg2"
        assert cache.get(cache_key("G2", "greeting_avatar")) == "url2"

    @pytest.mark.asyncio
    async def test_greeting_config_cdc_null_theme_id_also_invalidates(self) -> None:
        """Clearing themeId back to null must also invalidate caches."""
        cache = TTLCache()
        cache.set(cache_key("G1", "greeting_config"), "cfg", ttl=300)
        cache.set(cache_key("G1", "greeting_avatar"), "url", ttl=60)

        sub = _make_subscriber(cache)
        payload = {
            "data": {
                "type": "UPDATE",
                "table": "greeting_config",
                "schema": "public",
                "record": {"guildId": "G1", "themeId": None},
                "old_record": {},
            },
            "ids": [1],
        }
        await sub._handle_cdc(payload)

        assert cache.get(cache_key("G1", "greeting_config")) is None
        assert cache.get(cache_key("G1", "greeting_avatar")) is None
