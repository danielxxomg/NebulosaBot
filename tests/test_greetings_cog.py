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
def mock_renderer() -> MagicMock:
    """Return a mock greeting renderer whose ``render`` yields a BytesIO PNG.

    Returns a real io.BytesIO so discord.File receives a seekable/readable
    buffer instead of MagicMock (whose __index__ returns 1, causing
    open(MagicMock, 'rb') to corrupt stdout fd 1).
    """
    renderer = MagicMock(spec=["render"])

    def _make_card(**_kwargs: object) -> io.BytesIO:
        return io.BytesIO(_MINIMAL_PNG)

    renderer.render = MagicMock(side_effect=_make_card)
    return renderer


@pytest.fixture
def mock_bot(mock_greeting_service: MagicMock, mock_renderer: MagicMock) -> MagicMock:
    """Return a mock NebulosaBot with greeting_service attached.

    The cog resolves the render callable via ``greeting_service.resolve_renderer()``
    (Phase 2: renderer-dispatch policy lives in the service, single copy). Wire
    the mock so the resolver returns the renderer's ``render`` — tests that
    assert on its ``call_args`` keep working, and error-side tests that set
    ``side_effect`` on it still propagate through the cog.
    """
    bot = MagicMock(spec=commands.Bot)
    bot.greeting_service = mock_greeting_service
    mock_greeting_service.resolve_renderer = MagicMock(return_value=mock_renderer.render)
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
# Legacy greeting commands — REMOVED in S2b.8 (welcome-goodbye spec)
# /welcome and /goodbye hybrid groups + welcome_test/goodbye_test deleted
# after parity verified via /setup modules. Guard ensures deletion sticks.
# ---------------------------------------------------------------------------


class TestLegacyWelcomeCommandsRemoved:
    def test_welcome_group_removed(self) -> None:
        from bot.cogs.greetings import GreetingsCog

        assert not hasattr(GreetingsCog, "welcome"), "welcome must be deleted (S2b.8)"
        assert not hasattr(GreetingsCog, "welcome_channel"), "welcome_channel must be deleted"
        assert not hasattr(GreetingsCog, "welcome_toggle"), "welcome_toggle must be deleted"
        assert not hasattr(GreetingsCog, "welcome_message"), "welcome_message must be deleted"
        assert not hasattr(GreetingsCog, "welcome_test"), "welcome_test must be deleted"

    def test_goodbye_group_removed(self) -> None:
        from bot.cogs.greetings import GreetingsCog

        assert not hasattr(GreetingsCog, "goodbye"), "goodbye must be deleted (S2b.8)"
        assert not hasattr(GreetingsCog, "goodbye_channel"), "goodbye_channel must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_toggle"), "goodbye_toggle must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_message"), "goodbye_message must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_test"), "goodbye_test must be deleted"

    def test_no_hybrid_greeting_in_source(self) -> None:
        import pathlib as _pl

        src = _pl.Path("bot/cogs/greetings.py").read_text(encoding="utf-8")
        assert "hybrid_group" not in src, "greetings.py must not contain hybrid_group"
        assert "hybrid_command" not in src, "greetings.py must not contain hybrid_command"
