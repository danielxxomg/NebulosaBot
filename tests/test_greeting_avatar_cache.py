"""RED tests for guild-scoped greeting avatar cache (PR1 task 4.1).

Asserts:
- The avatar cache key is built via ``cache_key(guild_id, "greeting_avatar")``
  (i.e. ``"{guild_id}:greeting_avatar"``), not a bare key.
- TTL is 60 seconds.
- No cross-guild leak: guild A entries do not appear under guild B's key.
- ``invalidate_guild`` drops the avatar entry for free (prefix drop).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.cache import TTLCache, cache_key
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.greeting_service import AVATAR_CACHE_TTL, GreetingService


def _make_member(guild_id: int = 100, member_id: int = 333) -> MagicMock:
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_channel.send = AsyncMock(return_value=None)
    guild = MagicMock()
    guild.id = guild_id
    guild.name = "G"
    guild.member_count = 7
    guild.get_channel.return_value = mock_channel
    guild.icon = None
    avatar = MagicMock()
    avatar.url = f"https://cdn/{member_id}.png"
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.name = "U"
    member.display_name = "U"
    member.display_avatar = avatar
    member.guild = guild
    member.mention = f"<@{member_id}>"
    return member


def _make_service(cache: TTLCache) -> GreetingService:
    db = AsyncMock()
    db.get_greeting_config.return_value = {
        "guildId": "100",
        "welcomeEnabled": True,
        "welcomeChannelId": "111",
        "welcomeCardEnabled": True,
        "goodbyeEnabled": False,
    }
    return GreetingService(db=db, cache=cache, greeting_renderer=PillowGreetingRenderer())


class TestAvatarCacheKey:
    """4.1 — the avatar cache uses cache_key(gid, 'greeting_avatar')."""

    def test_key_template_is_guild_scoped(self) -> None:
        assert cache_key("100", "greeting_avatar") == "100:greeting_avatar"

    def test_avatar_cache_ttl_is_60s(self) -> None:
        assert AVATAR_CACHE_TTL == 60

    @pytest.mark.asyncio
    async def test_dispatch_populates_guild_scoped_avatar_key(self) -> None:
        cache = TTLCache()
        service = _make_service(cache)
        member = _make_member(guild_id=100)

        with patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None):
            await service.dispatch_welcome(member)

        # The avatar cache entry must be under the guild-scoped key.
        assert cache.get(cache_key("100", "greeting_avatar")) is not None, (
            "dispatch did not populate {guild_id}:greeting_avatar"
        )

    @pytest.mark.asyncio
    async def test_no_bare_avatar_key(self) -> None:
        cache = TTLCache()
        service = _make_service(cache)
        member = _make_member(guild_id=100)

        with patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None):
            await service.dispatch_welcome(member)

        # A bare "greeting_avatar" key (no guild prefix) must NOT leak.
        assert cache.get("greeting_avatar") is None

    @pytest.mark.asyncio
    async def test_no_cross_guild_leak(self) -> None:
        """Guild A's avatar cache entry must not appear under guild B's key."""
        cache = TTLCache()
        service = _make_service(cache)
        member_a = _make_member(guild_id=100, member_id=1)
        member_b = _make_member(guild_id=200, member_id=2)

        with patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None):
            await service.dispatch_welcome(member_a)

        # Guild B has no avatar entry yet.
        assert cache.get(cache_key("200", "greeting_avatar")) is None
        assert cache.get(cache_key("100", "greeting_avatar")) is not None

        with patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None):
            await service.dispatch_welcome(member_b)

        # Both guilds have their own entries; keys are distinct.
        assert cache.get(cache_key("100", "greeting_avatar")) is not None
        assert cache.get(cache_key("200", "greeting_avatar")) is not None


class TestAvatarCacheInvalidation:
    """4.1 / 5.2 — invalidate_guild drops the avatar entry (prefix drop)."""

    def test_invalidate_guild_drops_avatar_key(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("100", "greeting_avatar"), "url", ttl=60)
        cache.set(cache_key("100", "greeting_config"), "cfg", ttl=300)

        cache.invalidate_guild("100")

        assert cache.get(cache_key("100", "greeting_avatar")) is None
        assert cache.get(cache_key("100", "greeting_config")) is None

    def test_invalidate_guild_only_touches_own_guild(self) -> None:
        cache = TTLCache()
        cache.set(cache_key("100", "greeting_avatar"), "a", ttl=60)
        cache.set(cache_key("200", "greeting_avatar"), "b", ttl=60)

        cache.invalidate_guild("100")

        assert cache.get(cache_key("100", "greeting_avatar")) is None
        assert cache.get(cache_key("200", "greeting_avatar")) == "b"
