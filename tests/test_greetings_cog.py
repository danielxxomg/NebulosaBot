"""Unit tests for bot.cogs.greetings — GreetingsCog.

Covers:
    - on_member_join calls greeting_service.dispatch_welcome
    - on_member_remove calls greeting_service.dispatch_goodbye
    - /welcome_test command (admin-only)
    - /goodbye_test command (admin-only)
    - /welcome config|channel|toggle|message (admin-only)
    - /goodbye config|channel|toggle|message (admin-only)
    - Non-admin users blocked from test/config commands

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.greetings import GreetingsCog
from bot.models.greeting_config import GreetingConfig

# Minimal valid PNG for mock card buffers — avoids fd corruption when
# discord.File opens the buffer (MagicMock.__index__() returns 1, which
# makes open() interpret it as fd 1 / stdout).
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_greeting_service() -> MagicMock:
    """Return a mock GreetingService with async dispatch and config methods."""
    svc = MagicMock()
    svc.dispatch_welcome = AsyncMock()
    svc.dispatch_goodbye = AsyncMock()
    svc.get_config = AsyncMock(return_value=GreetingConfig(guild_id="123456789"))
    svc.save_config = AsyncMock()
    return svc


@pytest.fixture
def mock_image_service() -> MagicMock:
    """Return a mock ImageService with generate_greeting_card returning BytesIO.

    Returns a real io.BytesIO so discord.File receives a seekable/readable
    buffer instead of MagicMock (whose __index__ returns 1, causing
    open(MagicMock, 'rb') to corrupt stdout fd 1).
    """
    svc = MagicMock()

    def _make_card(**_kwargs: object) -> io.BytesIO:
        return io.BytesIO(_MINIMAL_PNG)

    svc.generate_greeting_card = MagicMock(side_effect=_make_card)
    return svc


@pytest.fixture
def mock_bot(mock_greeting_service: MagicMock, mock_image_service: MagicMock) -> MagicMock:
    """Return a mock NebulosaBot with greeting_service and image_service."""
    bot = MagicMock(spec=commands.Bot)
    bot.greeting_service = mock_greeting_service
    bot.image_service = mock_image_service
    return bot


@pytest.fixture
def cog(mock_bot: MagicMock) -> GreetingsCog:
    """Return a fresh GreetingsCog with mocked bot."""
    return GreetingsCog(mock_bot)


def _make_member(
    member_id: int = 111111111,
    guild_id: int = 123456789,
    display_name: str = "TestUser",
) -> MagicMock:
    """Build a mock discord.Member for event testing."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.name = display_name
    member.display_name = display_name
    member.bot = False
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = guild_id
    member.avatar = MagicMock()
    member.avatar.url = "https://cdn.discordapp.com/avatars/111/abc.png"
    return member


def _make_context(
    user_id: int = 111111111,
    guild_id: int = 123456789,
    admin: bool = True,
) -> MagicMock:
    """Build a mock commands.Context for testing hybrid commands.

    Args:
        admin: If True, the user has administrator permission.
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = user_id
    ctx.author.display_name = "TestUser"
    ctx.author.guild_permissions.administrator = admin
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    ctx.guild.member_count = 150
    return ctx


# ---------------------------------------------------------------------------
# on_member_join
# ---------------------------------------------------------------------------


class TestOnMemberJoin:
    """Tests for GreetingsCog.on_member_join()."""

    @pytest.mark.asyncio
    async def test_calls_dispatch_welcome(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """on_member_join must delegate to greeting_service.dispatch_welcome."""
        member = _make_member()
        await cog.on_member_join(member)
        mock_bot.greeting_service.dispatch_welcome.assert_awaited_once_with(member)

    @pytest.mark.asyncio
    async def test_ignore_bot_members(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Bot members should not trigger welcome cards."""
        member = _make_member()
        member.bot = True
        await cog.on_member_join(member)
        mock_bot.greeting_service.dispatch_welcome.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_member_remove
# ---------------------------------------------------------------------------


class TestOnMemberRemove:
    """Tests for GreetingsCog.on_member_remove()."""

    @pytest.mark.asyncio
    async def test_calls_dispatch_goodbye(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """on_member_remove must delegate to greeting_service.dispatch_goodbye."""
        member = _make_member()
        await cog.on_member_remove(member)
        mock_bot.greeting_service.dispatch_goodbye.assert_awaited_once_with(member)

    @pytest.mark.asyncio
    async def test_ignore_bot_members(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Bot members should not trigger goodbye cards."""
        member = _make_member()
        member.bot = True
        await cog.on_member_remove(member)
        mock_bot.greeting_service.dispatch_goodbye.assert_not_awaited()


# ---------------------------------------------------------------------------
# /welcome_test
# ---------------------------------------------------------------------------


class TestWelcomeTestCommand:
    """Tests for /welcome_test hybrid command."""

    @pytest.mark.asyncio
    async def test_admin_can_use_welcome_test(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Admin users must be able to trigger a welcome test card."""
        ctx = _make_context(admin=True)
        await cog.welcome_test.callback(cog, ctx)

        ctx.defer.assert_awaited_once_with(ephemeral=True)
        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert "file" in call_kwargs
        assert isinstance(call_kwargs["file"], discord.File)
        assert call_kwargs["file"].filename == "welcome.png"
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_welcome_test(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Non-admin users must receive an error when using /welcome_test."""
        ctx = _make_context(admin=False)
        await cog.welcome_test.callback(cog, ctx)

        ctx.defer.assert_not_awaited()
        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        embed = call_kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color.value == 0xE74C3C  # type: ignore[union-attr]  # COLOR_ERROR
        title_lower = embed.title.lower() if embed.title else ""  # type: ignore[union-attr]
        assert "permission" in title_lower or "permiso" in title_lower

    @pytest.mark.asyncio
    async def test_welcome_test_card_generation_error(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """When card generation fails, an error embed is sent."""
        ctx = _make_context(admin=True)
        mock_bot.image_service.generate_greeting_card.side_effect = RuntimeError("Pillow crash")

        await cog.welcome_test.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert "file" not in call_kwargs  # No file on error
        embed = call_kwargs["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR


# ---------------------------------------------------------------------------
# /goodbye_test
# ---------------------------------------------------------------------------


class TestGoodbyeTestCommand:
    """Tests for /goodbye_test hybrid command."""

    @pytest.mark.asyncio
    async def test_admin_can_use_goodbye_test(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Admin users must be able to trigger a goodbye test card."""
        ctx = _make_context(admin=True)
        await cog.goodbye_test.callback(cog, ctx)

        ctx.defer.assert_awaited_once_with(ephemeral=True)
        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert "file" in call_kwargs
        assert isinstance(call_kwargs["file"], discord.File)
        assert call_kwargs["file"].filename == "goodbye.png"

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_goodbye_test(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Non-admin users must receive an error when using /goodbye_test."""
        ctx = _make_context(admin=False)
        await cog.goodbye_test.callback(cog, ctx)

        ctx.defer.assert_not_awaited()
        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args[1]["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    async def test_goodbye_test_card_generation_error(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """When card generation fails, an error embed is sent."""
        ctx = _make_context(admin=True)
        mock_bot.image_service.generate_greeting_card.side_effect = RuntimeError("Font missing")

        await cog.goodbye_test.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert "file" not in call_kwargs
        embed = call_kwargs["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR


# ---------------------------------------------------------------------------
# /welcome config — config, channel, toggle, message
# ---------------------------------------------------------------------------


class TestWelcomeConfigCommand:
    """Tests for /welcome hybrid group: config, channel, toggle, message."""

    @pytest.mark.asyncio
    async def test_config_shows_current_settings(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Admin invoking /welcome config gets an ephemeral embed with settings."""
        config = GreetingConfig(
            guild_id="123456789",
            welcome_enabled=True,
            welcome_channel_id="999888777",
            welcome_message="Welcome {user}!",
        )
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.welcome.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert call_kwargs["ephemeral"] is True
        embed = call_kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        # Embed description must contain the channel, toggle, and message values.
        desc = embed.description or ""
        assert "999888777" in desc
        assert "Welcome {user}!" in desc

    @pytest.mark.asyncio
    async def test_config_no_channel_shows_not_configured(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """When no welcome channel is set, config shows 'not configured'."""
        config = GreetingConfig(guild_id="123456789")
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.welcome.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        desc = embed.description or ""
        # Should indicate no channel configured (key from locale or raw).
        assert "not" in desc.lower() or "no" in desc.lower() or "config" in desc.lower()

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_welcome_config(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Non-admin must be blocked from /welcome config."""
        ctx = _make_context(admin=False)
        await cog.welcome.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color is not None
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    async def test_channel_saves_new_channel(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/welcome channel #general saves the channel and invalidates cache."""
        config = GreetingConfig(guild_id="123456789")
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 555666777
        channel.mention = "<#555666777>"

        await cog.welcome_channel.callback(cog, ctx, channel=channel)

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.welcome_channel_id == "555666777"
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_toggle_flips_enabled(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/welcome toggle flips the enabled state and saves."""
        config = GreetingConfig(guild_id="123456789", welcome_enabled=True)
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.welcome_toggle.callback(cog, ctx)

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.welcome_enabled is False
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_toggle_flips_disabled_to_enabled(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/welcome toggle when disabled flips to enabled."""
        config = GreetingConfig(guild_id="123456789", welcome_enabled=False)
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.welcome_toggle.callback(cog, ctx)

        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.welcome_enabled is True

    @pytest.mark.asyncio
    async def test_message_saves_template(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/welcome message saves the template and invalidates cache."""
        config = GreetingConfig(guild_id="123456789")
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.welcome_message.callback(cog, ctx, template="Welcome {user} to {server}!")

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.welcome_message == "Welcome {user} to {server}!"
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True


# ---------------------------------------------------------------------------
# /goodbye config — config, channel, toggle, message
# ---------------------------------------------------------------------------


class TestGoodbyeConfigCommand:
    """Tests for /goodbye hybrid group: config, channel, toggle, message."""

    @pytest.mark.asyncio
    async def test_config_shows_current_settings(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Admin invoking /goodbye config gets an ephemeral embed with settings."""
        config = GreetingConfig(
            guild_id="123456789",
            goodbye_enabled=True,
            goodbye_channel_id="111222333",
            goodbye_message="Goodbye {user}!",
        )
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.goodbye.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        call_kwargs = ctx.send.call_args[1]
        assert call_kwargs["ephemeral"] is True
        embed = call_kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        desc = embed.description or ""
        assert "111222333" in desc
        assert "Goodbye {user}!" in desc

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_goodbye_config(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Non-admin must be blocked from /goodbye config."""
        ctx = _make_context(admin=False)
        await cog.goodbye.callback(cog, ctx)

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color is not None
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    async def test_channel_saves_new_channel(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/goodbye channel saves the channel and invalidates cache."""
        config = GreetingConfig(guild_id="123456789")
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888999000
        channel.mention = "<#888999000>"

        await cog.goodbye_channel.callback(cog, ctx, channel=channel)

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.goodbye_channel_id == "888999000"
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_toggle_flips_enabled(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/goodbye toggle flips the enabled state and saves."""
        config = GreetingConfig(guild_id="123456789", goodbye_enabled=True)
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.goodbye_toggle.callback(cog, ctx)

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.goodbye_enabled is False
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_message_saves_template(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """/goodbye message saves the template and invalidates cache."""
        config = GreetingConfig(guild_id="123456789")
        mock_bot.greeting_service.get_config = AsyncMock(return_value=config)

        ctx = _make_context(admin=True)
        await cog.goodbye_message.callback(cog, ctx, template="Goodbye {user}!")

        mock_bot.greeting_service.save_config.assert_awaited_once()
        saved = mock_bot.greeting_service.save_config.call_args[0][0]
        assert saved.goodbye_message == "Goodbye {user}!"
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args[1]["ephemeral"] is True
