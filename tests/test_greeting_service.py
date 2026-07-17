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
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.cache import TTLCache
from bot.core.i18n import set_guild_language
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
    mock_channel = MagicMock(spec=discord.TextChannel)
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
    async def test_cache_hit_preserves_onboarding_channel(
        self,
        service: GreetingService,
        cache: TTLCache,
    ) -> None:
        """Cache-first reads return the configured onboarding channel without DB access."""
        config = GreetingConfig(guild_id="123456789", onboarding_channel_id="999999999")
        cache.set("123456789:greeting_config", config, ttl=300)

        result = await service.get_config("123456789")

        assert result.onboarding_channel_id == "999999999"
        service._db.get_greeting_config.assert_not_called()

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

        mock_db.upsert_greeting_config.assert_called_once_with(guild_id, config)

        # Cache must be invalidated.
        assert cache.get(f"{guild_id}:greeting_config") is None

    @pytest.mark.asyncio
    async def test_save_config_persists_onboarding_channel(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
    ) -> None:
        """GreetingService owns persistence of the optional onboarding channel."""
        config = GreetingConfig(
            guild_id="123456789",
            onboarding_channel_id="999999999",
        )

        await service.save_config(config)

        mock_db.upsert_greeting_config.assert_awaited_once_with("123456789", config)


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

    @pytest.mark.asyncio
    async def test_card_enabled_sends_welcome_card(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcome_card_enabled is True, a card is generated and sent with a file."""
        mock_db.get_greeting_config.return_value = greeting_config_row
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_called_once()
        channel.send.assert_called_once()
        assert "file" in channel.send.call_args.kwargs

    @pytest.mark.asyncio
    async def test_renderer_compatibility_fallback_and_error_propagation(
        self, service: GreetingService, mock_db: AsyncMock, greeting_config_row: dict
    ) -> None:
        received: dict[str, object] = {}

        def old_renderer(username, avatar_url, guild_name, member_count, card_type):
            received.update(locals())
            return io.BytesIO()

        service._image_service.generate_greeting_card = old_renderer
        mock_db.get_greeting_config.return_value = greeting_config_row

        await service.dispatch_welcome(make_mock_member())

        assert received["card_type"] == "welcome"
        assert "greeting_title" not in received
        assert "member_count_text" not in received

        def broken_renderer(**_: object) -> io.BytesIO:
            raise TypeError("renderer failed while drawing")

        service._image_service.generate_greeting_card = broken_renderer
        mock_db.get_greeting_config.return_value = greeting_config_row

        with pytest.raises(TypeError, match="renderer failed while drawing"):
            await service.dispatch_welcome(make_mock_member())

    @pytest.mark.asyncio
    async def test_resolvable_onboarding_channel_appends_localized_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """A resolvable onboarding channel is included in welcome content and renderer inputs."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member(member_id=333, name="NewUser")
        set_guild_language(str(member.guild.id), "en")

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        content = channel.send.call_args.kwargs["content"]
        assert "Start here: <#999999999>" in content
        assert "greeting_title" in mock_image_service.generate_greeting_card.call_args.kwargs
        assert "member_count_text" in mock_image_service.generate_greeting_card.call_args.kwargs
        assert mock_image_service.generate_greeting_card.call_args.kwargs["greeting_title"] == "Welcome to the server!"

    @pytest.mark.asyncio
    async def test_spanish_live_welcome_dispatch_passes_localized_copy_and_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """A Spanish join resolves localized card copy and onboarding CTA together."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "onboardingChannelId": "999999999",
            "welcomeMessage": None,
        }
        member = make_mock_member(member_id=333, name="NewUser")
        set_guild_language(str(member.guild.id), "es")

        await service.dispatch_welcome(member)

        renderer_kwargs = mock_image_service.generate_greeting_card.call_args.kwargs
        assert renderer_kwargs["greeting_title"] == "¡Bienvenido al servidor!"
        assert renderer_kwargs["member_count_text"] == "Eres el miembro número 150"
        assert member.guild.get_channel.return_value.send.call_args.kwargs["content"] == (
            "Empieza por aquí: <#999999999>"
        )

    @pytest.mark.asyncio
    async def test_empty_welcome_message_with_resolvable_onboarding_channel_is_cta_only(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """An empty welcome template must still deliver only the localized CTA."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "onboardingChannelId": "999999999",
            "welcomeMessage": "",
        }
        member = make_mock_member(member_id=333, name="NewUser")
        set_guild_language(str(member.guild.id), "en")

        await service.dispatch_welcome(member)

        content = member.guild.get_channel.return_value.send.call_args.kwargs["content"]
        assert content == "Start here: <#999999999>"

    @pytest.mark.asyncio
    async def test_custom_welcome_message_preserves_onboarding_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Custom welcome text and the onboarding CTA are sent together."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "onboardingChannelId": "999999999",
            "welcomeMessage": "Welcome {mention} to {server}!",
        }
        member = make_mock_member(member_id=333, name="NewUser")
        set_guild_language(str(member.guild.id), "en")

        await service.dispatch_welcome(member)

        content = member.guild.get_channel.return_value.send.call_args.kwargs["content"]
        assert "Welcome <@333> to TestServer!" in content
        assert "Start here: <#999999999>" in content

    @pytest.mark.asyncio
    @pytest.mark.parametrize("onboarding_channel_id", [None, "888888888"])
    async def test_missing_or_unresolvable_onboarding_channel_omits_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
        onboarding_channel_id: str | None,
    ) -> None:
        """Missing or inaccessible onboarding targets do not break welcome delivery."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "onboardingChannelId": onboarding_channel_id,
        }
        member = make_mock_member(member_id=333, name="NewUser")
        if onboarding_channel_id is not None:
            welcome_channel = member.guild.get_channel.return_value
            member.guild.get_channel.side_effect = lambda channel_id: (
                welcome_channel if channel_id == int(greeting_config_row["welcomeChannelId"]) else None
            )

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        content = channel.send.call_args.kwargs["content"]
        assert "welcome_onboarding" not in content
        assert "<#" not in content
        channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_card_disabled_with_message_sends_text_only(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcome_card_enabled is False and a message is set, send text only (no file)."""
        disabled_card = {**greeting_config_row, "welcomeCardEnabled": False}
        mock_db.get_greeting_config.return_value = disabled_card
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_called_once()
        assert "file" not in channel.send.call_args.kwargs
        content = channel.send.call_args.kwargs.get("content", "")
        assert "<@333>" in content  # {mention} substituted, not literal
        assert "TestServer" in content  # {server} substituted, not literal

    @pytest.mark.asyncio
    async def test_card_disabled_without_message_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """When welcome_card_enabled is False and no message is set, send nothing."""
        disabled_card = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": None,
        }
        mock_db.get_greeting_config.return_value = disabled_card
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_skips_before_card_toggle(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """Top-level welcome_enabled guard MUST short-circuit before the card toggle.

        Regression guard: even with welcome_card_enabled=True, when
        welcome_enabled is False nothing is sent and no card is generated.
        """
        disabled = {**greeting_config_row, "welcomeEnabled": False}
        mock_db.get_greeting_config.return_value = disabled
        member = make_mock_member(member_id=333, name="NewUser")

        await service.dispatch_welcome(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_global_disabled_ignores_card_toggle_and_message(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """A globally disabled welcome must send neither card nor text."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeEnabled": False,
            "welcomeMessage": "Welcome {mention}!",
            "welcomeCardEnabled": True,
        }
        member = make_mock_member()

        await service.dispatch_welcome(member)

        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_global_disabled_ignores_resolvable_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """A globally disabled welcome must not resolve onboarding CTA data."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeEnabled": False,
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_none_message_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """A disabled card with no message must not fall back to a CTA-only send."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": None,
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_empty_string_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """An empty disabled-card template must not produce a CTA-only send."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_whitespace_only_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Whitespace-only disabled-card content is empty after formatting."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "   \n\t ",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_template_substitutes_to_whitespace_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Formatted content that becomes whitespace must be treated as empty."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": " {mention} ",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()
        member.mention = ""

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_non_empty_sends_text_only_no_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """A non-empty disabled-card welcome sends formatted text without CTA."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "Welcome {mention}!",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_awaited_once_with(
            content="Welcome <@333>!"
        )

    @pytest.mark.asyncio
    async def test_disabled_card_invalid_cta_does_not_block_text(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """An invalid onboarding channel must not block disabled-card text."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "Welcome {mention}!",
            "onboardingChannelId": "not-a-channel-id",
        }
        member = make_mock_member()

        with patch(
            "bot.services.greeting_service._resolve_welcome_cta",
            side_effect=AssertionError("disabled-card text must skip CTA resolution"),
        ) as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_awaited_once_with(
            content="Welcome <@333>!"
        )

    @pytest.mark.asyncio
    async def test_disabled_card_missing_cta_sends_text(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """A missing onboarding channel must not affect disabled-card text."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "Welcome {mention}!",
            "onboardingChannelId": None,
        }
        member = make_mock_member()

        with patch(
            "bot.services.greeting_service._resolve_welcome_cta",
            side_effect=AssertionError("disabled-card text must skip CTA resolution"),
        ) as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_awaited_once_with(
            content="Welcome <@333>!"
        )

    @pytest.mark.asyncio
    async def test_disabled_card_empty_despite_resolvable_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """An empty disabled-card message remains silent with a valid CTA target."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_empty_despite_invalid_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """An empty disabled-card message remains silent with an invalid CTA target."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "",
            "onboardingChannelId": "not-a-channel-id",
        }
        member = make_mock_member()

        with patch(
            "bot.services.greeting_service._resolve_welcome_cta",
            side_effect=AssertionError("disabled-card text must skip CTA resolution"),
        ) as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_card_preserves_localization(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Disabled-card text preserves locale-independent template substitution."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": "Hola {mention} en {server}!",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()
        set_guild_language(str(member.guild.id), "es")

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_awaited_once_with(
            content="Hola <@333> en TestServer!"
        )

    @pytest.mark.asyncio
    async def test_card_enabled_empty_msg_resolvable_cta_sends_cta_only(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Card-enabled empty welcomes retain their CTA-only behavior."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": True,
            "welcomeMessage": "",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()
        set_guild_language(str(member.guild.id), "en")

        await service.dispatch_welcome(member)

        assert member.guild.get_channel.return_value.send.call_args.kwargs["content"] == (
            "Start here: <#999999999>"
        )

    @pytest.mark.asyncio
    async def test_card_enabled_with_msg_appends_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Card-enabled welcomes retain formatted text plus their localized CTA."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": True,
            "welcomeMessage": "Welcome {mention}!",
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()
        set_guild_language(str(member.guild.id), "en")

        await service.dispatch_welcome(member)

        content = member.guild.get_channel.return_value.send.call_args.kwargs["content"]
        assert content == "Welcome <@333>!\nStart here: <#999999999>"

    @pytest.mark.asyncio
    async def test_existing_guild_silently_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Existing disabled-card configuration needs no migration or notice."""
        mock_db.get_greeting_config.return_value = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": None,
            "onboardingChannelId": "999999999",
        }
        member = make_mock_member()

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_guild_old_row_loads_without_write_or_notice(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """Pre-change rows remain readable and dispatch stays silent."""
        # Intentionally omit onboardingChannelId to model pre-change rows.
        old_row = {
            **greeting_config_row,
            "welcomeCardEnabled": False,
            "welcomeMessage": None,
        }
        mock_db.get_greeting_config.return_value = old_row
        member = make_mock_member()

        config = await service.get_config(str(member.guild.id))

        assert config.onboarding_channel_id is None
        assert config.welcome_card_enabled is False

        with patch("bot.services.greeting_service._resolve_welcome_cta") as resolve_cta:
            await service.dispatch_welcome(member)

        mock_db.upsert_greeting_config.assert_not_awaited()
        mock_image_service.generate_greeting_card.assert_not_called()
        resolve_cta.assert_not_called()
        member.guild.get_channel.return_value.send.assert_not_awaited()


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

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("language", "expected_title", "expected_count"),
        [
            ("es", "¡Hasta luego y buena suerte!", "Eres el miembro número 150"),
            ("en", "Goodbye and good luck!", "You are member #150"),
        ],
    )
    async def test_localized_goodbye_dispatch_hands_off_copy_without_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
        language: str,
        expected_title: str,
        expected_count: str,
    ) -> None:
        """Leave dispatch hands off localized copy and never appends a welcome CTA."""
        mock_db.get_greeting_config.return_value = greeting_config_row
        member = make_mock_member(member_id=444, name="LeavingUser")
        set_guild_language(str(member.guild.id), language)

        await service.dispatch_goodbye(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_called_once()
        renderer_kwargs = mock_image_service.generate_greeting_card.call_args.kwargs
        assert renderer_kwargs["greeting_title"] == expected_title
        assert renderer_kwargs["member_count_text"] == expected_count
        channel.send.assert_called_once()
        assert "file" in channel.send.call_args.kwargs
        content = channel.send.call_args.kwargs["content"] or ""
        assert "<#999999999>" not in content
        assert "welcome_onboarding" not in content

    @pytest.mark.asyncio
    async def test_goodbye_never_appends_welcome_cta(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        greeting_config_row: dict,
    ) -> None:
        """Goodbye delivery remains CTA-free even when onboarding is configured."""
        mock_db.get_greeting_config.return_value = greeting_config_row
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)

        content = member.guild.get_channel.return_value.send.call_args.kwargs["content"]
        assert "welcome_onboarding" not in content
        assert "<#999999999>" not in content

    @pytest.mark.asyncio
    async def test_card_disabled_with_message_sends_text_only(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """When goodbye_card_enabled is False and a message is set, send text only (no file)."""
        disabled_card = {**greeting_config_row, "goodbyeCardEnabled": False}
        mock_db.get_greeting_config.return_value = disabled_card
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_called_once()
        assert "file" not in channel.send.call_args.kwargs
        content = channel.send.call_args.kwargs.get("content", "")
        assert "<@444>" in content  # {mention} substituted, not literal

    @pytest.mark.asyncio
    async def test_card_disabled_without_message_sends_nothing(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """When goodbye_card_enabled is False and no message is set, send nothing."""
        disabled_card = {
            **greeting_config_row,
            "goodbyeCardEnabled": False,
            "goodbyeMessage": None,
        }
        mock_db.get_greeting_config.return_value = disabled_card
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_skips_before_card_toggle(
        self,
        service: GreetingService,
        mock_db: AsyncMock,
        mock_image_service: MagicMock,
        greeting_config_row: dict,
    ) -> None:
        """Top-level goodbye_enabled guard MUST short-circuit before the card toggle.

        Regression guard: even with goodbye_card_enabled=True, when
        goodbye_enabled is False nothing is sent and no card is generated.
        """
        disabled = {**greeting_config_row, "goodbyeEnabled": False}
        mock_db.get_greeting_config.return_value = disabled
        member = make_mock_member(member_id=444, name="LeavingUser")

        await service.dispatch_goodbye(member)

        channel = member.guild.get_channel.return_value
        mock_image_service.generate_greeting_card.assert_not_called()
        channel.send.assert_not_called()
