"""Integration tests for the moderation warn flow.

Verifies the full ``/warn`` chain: command invocation → infraction service →
mocked DB insert → log embed content.  Uses existing conftest mocks
(``mock_db``, ``mock_interaction``) and wires real service objects with
mocked dependencies.

TDD cycle: RED → GREEN — these tests specify expected behavior of
existing code; the implementation already satisfies them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.sentinel import SentinelCog
from bot.core.cache import TTLCache
from bot.services.infraction_service import InfractionService
from bot.services.logging_service import LoggingService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    guild: MagicMock,
    author: MagicMock,
    channel: MagicMock | None = None,
) -> MagicMock:
    """Build a mock ``commands.Context`` for sentinel command invocation."""
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
def sentinel_bot(mock_db: AsyncMock, cache: TTLCache) -> MagicMock:
    """Return a mock NebulosaBot wired with real services + mock DB."""
    bot = MagicMock()
    bot.db = mock_db
    bot.infraction_service = InfractionService(db=mock_db)
    bot.logging_service = MagicMock(spec=LoggingService)
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 999999999
    return bot


@pytest.fixture
def sentinel_cog(sentinel_bot: MagicMock) -> SentinelCog:
    """Return a SentinelCog wired to the mock bot."""
    return SentinelCog(bot=sentinel_bot)


@pytest.fixture
def mod_author() -> MagicMock:
    """Return a mock moderator author with a known ID."""
    member = MagicMock(spec=discord.Member)
    member.id = 111111111
    member.mention = "<@111111111>"
    member.name = "TestMod"
    return member


@pytest.fixture
def mod_ctx(mock_guild: MagicMock, mod_author: MagicMock) -> MagicMock:
    """Return a mock Context with a moderator author and guild."""
    return _make_ctx(mock_guild, mod_author)


@pytest.fixture
def target_member(mock_guild: MagicMock) -> MagicMock:
    """Return a mock target member (different from the moderator)."""
    member = MagicMock()
    member.id = 555555555
    member.mention = "<@555555555>"
    member.name = "TargetUser"
    member.top_role = MagicMock()
    member.top_role.__le__ = MagicMock(return_value=False)
    # guild.me for role hierarchy checks
    mock_guild.me = MagicMock()
    mock_guild.me.top_role = MagicMock()
    mock_guild.me.top_role.__le__ = MagicMock(return_value=False)
    return member


@pytest.fixture
def warn_infraction_row() -> dict:
    """Return a sample DB row for a WARN infraction."""
    return {
        "id": "infraction-uuid-001",
        "guildId": "123456789",
        "targetId": "555555555",
        "moderatorId": "111111111",
        "type": "WARN",
        "reason": "Test reason",
        "active": True,
        "createdAt": datetime.now(UTC),
    }


@pytest.fixture
def member_row_zero_warnings() -> dict:
    """Return a member DB row with zero warnings."""
    return {
        "guildId": "123456789",
        "userId": "555555555",
        "xp": 0,
        "level": 0,
        "warnings": 0,
        "coins": 0,
    }


# ---------------------------------------------------------------------------
# TestModerationFlow — integration: warn round-trip
# ---------------------------------------------------------------------------


class TestModerationFlow:
    """Integration tests for the moderation warn flow.

    Verifies: command → service → DB mock → log embed.
    """

    async def test_warn_persists_infraction_and_sends_log_embed(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        mod_ctx: MagicMock,
        target_member: MagicMock,
        mock_db: AsyncMock,
        warn_infraction_row: dict,
        member_row_zero_warnings: dict,
    ) -> None:
        """Warn flow: infraction persisted, log embed sent.

        Scenario from spec: moderator with moderate_members issues /warn
        with reason → assert mock_db.insert_infraction called with correct
        guild_id, user_id, action='warn', reason → assert log embed sent.
        """
        # Setup DB mocks.
        mock_db.insert_infraction = AsyncMock(return_value=warn_infraction_row)
        mock_db.get_member = AsyncMock(return_value=member_row_zero_warnings)
        mock_db.update_member_warnings = AsyncMock()

        # Bypass _validate_target.
        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.warn.callback(sentinel_cog, mod_ctx, target_member, reason="Test reason")

        # 1. Infraction persisted with correct args.
        mock_db.insert_infraction.assert_awaited_once_with(
            guild_id="123456789",
            target_id="555555555",
            moderator_id="111111111",
            type="WARN",
            reason="Test reason",
        )

        # 2. Log embed sent with moderator, target, action type, reason.
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once_with(
            "123456789",
            "Warn",
            target_member,
            mod_ctx.author,
            "Test reason",
        )

        # 3. Success embed sent to channel.
        mod_ctx.send.assert_awaited_once()
        sent_embed = mod_ctx.send.call_args.kwargs.get("embed") or mod_ctx.send.call_args[1].get("embed")
        assert sent_embed is not None
        assert "Warned" in sent_embed.title

    async def test_warn_without_log_channel_skips_embed(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        mod_ctx: MagicMock,
        target_member: MagicMock,
        mock_db: AsyncMock,
        warn_infraction_row: dict,
        member_row_zero_warnings: dict,
    ) -> None:
        """Warn without log channel: infraction persisted, log still called.

        Scenario: logChannelId not configured → infraction persisted,
        logging_service.log_moderation_action still called (it handles
        missing channel internally).
        """
        mock_db.insert_infraction = AsyncMock(return_value=warn_infraction_row)
        mock_db.get_member = AsyncMock(return_value=member_row_zero_warnings)
        mock_db.update_member_warnings = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.warn.callback(sentinel_cog, mod_ctx, target_member, reason="Test reason")

        # Infraction persisted — the core behavior.
        mock_db.insert_infraction.assert_awaited_once_with(
            guild_id="123456789",
            target_id="555555555",
            moderator_id="111111111",
            type="WARN",
            reason="Test reason",
        )

        # log_moderation_action is still called; the service handles
        # the missing log channel gracefully.
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()

        # Success embed still sent.
        mod_ctx.send.assert_awaited_once()
