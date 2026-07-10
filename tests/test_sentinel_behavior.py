"""Behavioral tests for SentinelCog moderation commands.

Separated from i18n/locale tests. Covers escalation logic, confirmation
wiring, and _validate_target deny scenarios using mocked Discord objects
and services — no real API calls.

TDD cycle: RED → GREEN → REFACTOR.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.cogs.sentinel import SentinelCog
from bot.core.i18n import load_locales, set_guild_language
from bot.services.infraction_service import InfractionService
from bot.services.logging_service import LoggingService

load_locales()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    guild: MagicMock,
    author: MagicMock,
    channel: MagicMock | None = None,
) -> MagicMock:
    """Build a mock ``commands.Context`` for sentinel commands."""
    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = author
    ctx.channel = channel or MagicMock()
    ctx.send = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sentinel_bot(mock_db) -> MagicMock:
    """Return a mock NebulosaBot wired for sentinel behavior tests."""
    set_guild_language("123456789", "en")

    bot = MagicMock()
    bot.db = mock_db
    bot.infraction_service = InfractionService(db=mock_db)
    bot.logging_service = MagicMock(spec=LoggingService)
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 999999999
    return bot


@pytest.fixture
def sentinel_cog(sentinel_bot) -> SentinelCog:
    """Return a SentinelCog wired to the mock bot."""
    return SentinelCog(bot=sentinel_bot)


@pytest.fixture
def mod_author() -> MagicMock:
    """Return a mock moderator with a known ID."""
    m = MagicMock()
    m.id = 111111111
    m.mention = "<@111111111>"
    m.name = "TestMod"
    return m


@pytest.fixture
def target_member(mock_guild) -> MagicMock:
    """Return a mock target member with lower role than bot."""
    m = MagicMock()
    m.id = 555555555
    m.mention = "<@555555555>"
    m.name = "TargetUser"
    m.top_role = MagicMock()
    m.top_role.__le__ = MagicMock(return_value=False)
    mock_guild.me = MagicMock()
    mock_guild.me.top_role = MagicMock()
    mock_guild.me.top_role.__le__ = MagicMock(return_value=False)
    return m


@pytest.fixture
def sentinel_ctx(mock_guild, mod_author) -> MagicMock:
    """Return a mock Context for sentinel commands."""
    return _make_ctx(mock_guild, mod_author)


# ---------------------------------------------------------------------------
# Warn auto-escalation
# ---------------------------------------------------------------------------


class TestWarnAutoEscalation:
    """Tests for warn command auto-escalation to mute."""

    async def test_warn_auto_mute_triggered_at_threshold(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """warn → when escalation returns MUTE, member.timeout is called."""
        mock_db.insert_infraction = AsyncMock(
            return_value={
                "id": "inf-001",
                "guildId": "123456789",
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "WARN",
                "reason": "test",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
        )
        mock_db.update_member_warnings = AsyncMock()
        mock_db.get_member = AsyncMock(
            return_value={
                "guildId": "123456789",
                "userId": "555555555",
                "warnings": 3,
            }
        )

        target_member.timeout = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.warn.callback(
                sentinel_cog, sentinel_ctx, target_member, reason="repeated offense"
            )

        target_member.timeout.assert_awaited_once()
        timeout_args = target_member.timeout.call_args
        assert timeout_args[0][0].total_seconds() == 3600  # 1 hour
        assert "Auto-escalation" in timeout_args[1]["reason"]


# ---------------------------------------------------------------------------
# _validate_target — bot target denial
# ---------------------------------------------------------------------------


class TestValidateTargetBotDenial:
    """Tests for _validate_target denying the bot itself as a target."""

    async def test_deny_bot_as_target(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
    ) -> None:
        """_validate_target → returns False when target is the bot user."""
        bot_as_target = MagicMock()
        bot_as_target.id = sentinel_cog.bot.user.id  # Same as bot.user.id
        bot_as_target.mention = "<@999999999>"

        result = await sentinel_cog._validate_target(sentinel_ctx, bot_as_target, "warn")

        assert result is False
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "moderate" in embed.description.lower()

    async def test_deny_self_target(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
    ) -> None:
        """_validate_target → returns False when target is the invoker."""
        self_target = MagicMock()
        self_target.id = sentinel_ctx.author.id  # Same as ctx.author.id
        self_target.mention = "<@111111111>"

        result = await sentinel_cog._validate_target(sentinel_ctx, self_target, "warn")

        assert result is False
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "yourself" in embed.description.lower()

    async def test_deny_higher_role_target(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        mock_guild,
    ) -> None:
        """_validate_target → returns False when target outranks the bot."""
        high_target = MagicMock()
        high_target.id = 666666666
        high_target.mention = "<@666666666>"
        high_target.top_role = MagicMock()
        high_target.top_role.__le__ = MagicMock(return_value=False)

        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        # bot.top_role <= target.top_role → True (bot is below target)
        mock_guild.me.top_role.__le__ = MagicMock(return_value=True)
        sentinel_ctx.guild = mock_guild

        result = await sentinel_cog._validate_target(sentinel_ctx, high_target, "warn")

        assert result is False
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "role" in embed.title.lower()
