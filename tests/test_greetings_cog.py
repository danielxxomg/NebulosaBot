"""Unit tests for bot.cogs.greetings — GreetingsCog.

Covers:
    - on_member_join calls greeting_service.dispatch_welcome
    - on_member_remove calls greeting_service.dispatch_goodbye
    - /welcome_test command (admin-only)
    - /goodbye_test command (admin-only)
    - Non-admin users blocked from test commands

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.greetings import GreetingsCog

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
    """Return a mock GreetingService with async dispatch methods."""
    svc = MagicMock()
    svc.dispatch_welcome = AsyncMock()
    svc.dispatch_goodbye = AsyncMock()
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
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR
        assert "Permission" in embed.title or "permission" in embed.title.lower()

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
