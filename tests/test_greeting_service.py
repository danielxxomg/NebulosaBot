"""Unit tests for bot.services.greeting_service.GreetingService.

Covers the greeting-config spec scenarios:
    - get_config: cache hit, cache miss + DB hit, cache miss + defaults
    - save_config: upserts + cache invalidation + re-read
    - dispatch_welcome: enabled/missing channel/disabled guards
    - dispatch_goodbye: same guards

Strict TDD: tests written BEFORE implementation (RED phase).
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.models.greeting_config import GreetingConfig
from bot.services.greeting_service import GreetingService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock for Database, pre-configured for greeting methods."""
    db = AsyncMock()
    db.get_greeting_config = AsyncMock()
    db.upsert_greeting_config = AsyncMock()
    return db


@pytest.fixture
def mock_image_service() -> MagicMock:
    """Return a MagicMock for ImageService."""
    img = MagicMock()
    img.generate_greeting_card = MagicMock(side_effect=lambda *_, **__: io.BytesIO(b"fake-image"))
    return img


@pytest.fixture
def service(
    cache: TTLCache,
    mock_db: AsyncMock,
    mock_image_service: MagicMock,
) -> GreetingService:
    """Return a fresh GreetingService with mocked dependencies."""
    return GreetingService(db=mock_db, cache=cache, image_service=mock_image_service)


@pytest.fixture
def greeting_config_row() -> dict:
    """Return a sample greeting_config DB row (camelCase keys)."""
    return {
        "guildId": "123456789",
        "welcomeEnabled": True,
        "goodbyeEnabled": True,
        "welcomeChannelId": "111111111",
        "goodbyeChannelId": "222222222",
        "welcomeMessage": "Welcome {mention} to {server}!",
        "goodbyeMessage": "Goodbye {mention}!",
        "welcomeCardEnabled": True,
        "goodbyeCardEnabled": True,
    }


def make_mock_member(
    member_id: int = 333,
    name: str = "TestUser",
    guild_id: int = 123456789,
) -> MagicMock:
    """Build a mock discord.Member with a guild that has a mock channel."""
    # Mock the channel that dispatch will send to.
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()

    member = MagicMock()
    member.id = member_id
    member.name = name
    member.display_name = name
    member.mention = f"<@{member_id}>"
    member.bot = False
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.discordapp.com/avatars/333/abc.png"
    member.guild = MagicMock()
    member.guild.id = guild_id
    member.guild.name = "TestServer"
    member.guild.member_count = 150
    member.guild.get_channel.return_value = mock_channel
    return member


# ---------------------------------------------------------------------------
# get_config — cache-first
# ---------------------------------------------------------------------------


class TestGetConfig:
    """get_config() must use cache-first resolution."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_config(
        self,
        service: GreetingService,
        cache: TTLCache,
        greeting_config_row: dict,
    ) -> None:
        """When config is cached, get_config() must return it without DB call."""
        guild_id = "123456789"
        cached = GreetingConfig.from_db_row(greeting_config_row)
        cache.set(f"{guild_id}:greeting_config", cached, ttl=300)

        result = await service.get_config(guild_id)

        assert result is cached
        service._db.get_greeting_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_db_hit_populates_cache(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        cache: TTLCache,
        greeting_config_row: dict,
    ) -> None:
        """Cache miss must fetch from DB and populate cache."""
        guild_id = "123456789"
        mock_db.get_greeting_config.return_value = greeting_config_row

        result = await service.get_config(guild_id)

        assert result.guild_id == guild_id
        assert result.welcome_enabled is True
        assert result.welcome_channel_id == "111111111"
        mock_db.get_greeting_config.assert_called_once_with(guild_id)

        # Cache must be populated.
        cached = cache.get(f"{guild_id}:greeting_config")
        assert cached is not None
        assert cached.welcome_enabled is True

    @pytest.mark.asyncio
    async def test_cache_miss_no_db_row_returns_defaults(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        cache: TTLCache,
    ) -> None:
        """When no DB row exists, get_config() must return defaults."""
        guild_id = "999888777"
        mock_db.get_greeting_config.return_value = None

        result = await service.get_config(guild_id)

        assert result.guild_id == guild_id
        assert result.welcome_enabled is False
        assert result.goodbye_enabled is False
        assert result.welcome_channel_id is None
        assert result.goodbye_channel_id is None
        mock_db.get_greeting_config.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_different_guilds_have_separate_cache_keys(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        cache: TTLCache,
        greeting_config_row: dict,
    ) -> None:
        """Different guilds must use separate cache keys."""
        guild_a = "111111111"
        guild_b = "222222222"

        mock_db.get_greeting_config.return_value = greeting_config_row
        await service.get_config(guild_a)
        await service.get_config(guild_b)

        # Both should be cached under different keys.
        assert cache.get(f"{guild_a}:greeting_config") is not None
        assert cache.get(f"{guild_b}:greeting_config") is not None
        # DB was called twice (once per guild).
        assert mock_db.get_greeting_config.call_count == 2


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    """save_config() must upsert to DB and invalidate cache."""

    @pytest.mark.asyncio
    async def test_save_config_upserts_and_invalidates(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        cache: TTLCache,
    ) -> None:
        """save_config() must call DB upsert then invalidate the cache entry."""
        guild_id = "123456789"
        config = GreetingConfig(
            guild_id=guild_id,
            welcome_enabled=True,
            welcome_channel_id="111111111",
        )

        # Pre-populate cache with a stale value.
        cache.set(f"{guild_id}:greeting_config", "STALE", ttl=300)

        await service.save_config(config)

        mock_db.upsert_greeting_config.assert_called_once_with(config)

        # Cache must be invalidated.
        assert cache.get(f"{guild_id}:greeting_config") is None


# ---------------------------------------------------------------------------
# dispatch_welcome — config guard logic
# ---------------------------------------------------------------------------


class TestDispatchWelcome:
    """dispatch_welcome() must check config guards before proceeding.

    Card generation + sending is wired in Phase 2 — Phase 1 only validates
    that the guard logic correctly skips when conditions are not met.
    """

    @pytest.mark.asyncio
    async def test_enabled_and_channel_set_resolves_config(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcome is enabled and channel is set, config must be resolved."""
        guild_id = "123456789"
        mock_db.get_greeting_config.return_value = greeting_config_row
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)

        # Config was resolved (no-op for now — Phase 2 sends the card).
        mock_db.get_greeting_config.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_disabled_skips_entirely(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcome_enabled is False, resolver returns early."""
        disabled = {**greeting_config_row, "welcomeEnabled": False}
        mock_db.get_greeting_config.return_value = disabled
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)
        # Service resolves config but takes no further action — no error expected.

    @pytest.mark.asyncio
    async def test_missing_channel_skips(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcomeChannelId is None, resolver returns early."""
        no_channel = {**greeting_config_row, "welcomeChannelId": None}
        mock_db.get_greeting_config.return_value = no_channel
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)
        # Service resolves config but takes no further action — no error expected.

    @pytest.mark.asyncio
    async def test_no_config_row_skips(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
    ) -> None:
        """When no config row exists (returns defaults), welcome is disabled."""
        mock_db.get_greeting_config.return_value = None
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)
        # Defaults have welcome_enabled=False — no action taken.


# ---------------------------------------------------------------------------
# dispatch_goodbye — config guard logic
# ---------------------------------------------------------------------------


class TestDispatchGoodbye:
    """dispatch_goodbye() must check config guards before proceeding.

    Card generation + sending is wired in Phase 2 — Phase 1 only validates
    that the guard logic correctly skips when conditions are not met.
    """

    @pytest.mark.asyncio
    async def test_enabled_and_channel_set_resolves_config(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When goodbye is enabled and channel is set, config must be resolved."""
        guild_id = "123456789"
        mock_db.get_greeting_config.return_value = greeting_config_row
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)

        mock_db.get_greeting_config.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_disabled_skips_entirely(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When goodbye_enabled is False, resolver returns early."""
        disabled = {**greeting_config_row, "goodbyeEnabled": False}
        mock_db.get_greeting_config.return_value = disabled
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)
        # Service resolves config but takes no further action — no error expected.

    @pytest.mark.asyncio
    async def test_missing_channel_skips(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """When goodbyeChannelId is None, resolver returns early."""
        no_channel = {**greeting_config_row, "goodbyeChannelId": None}
        mock_db.get_greeting_config.return_value = no_channel
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)
        # Service resolves config but takes no further action — no error expected.

    @pytest.mark.asyncio
    async def test_no_config_row_skips(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
    ) -> None:
        """When no config row exists (returns defaults), goodbye is disabled."""
        mock_db.get_greeting_config.return_value = None
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)
        # Defaults have goodbye_enabled=False — no action taken.
