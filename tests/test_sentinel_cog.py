"""Unit tests for bot.cogs.sentinel.SentinelCog.

Covers all 9 moderation commands and internal helpers:
    - warn / unwarn — infraction creation and deactivation
    - mute / unmute — timeout application and removal
    - kick / ban — member removal
    - lock / unlock — channel permission manipulation
    - modlogs — paginated infraction history
    - _ModlogsPaginator — prev/next button navigation
    - _validate_target — self-target, role hierarchy guards
    - _handle_mod_error — exception mapping to error embeds

TDD cycle: RED → GREEN — tests specify expected behavior of existing code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.sentinel import SentinelCog, _ModlogsPaginator
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
    """Return a mock NebulosaBot wired for sentinel tests."""
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
    # Target role is below bot role.
    m.top_role.__le__ = MagicMock(return_value=False)
    mock_guild.me = MagicMock()
    mock_guild.me.top_role = MagicMock()
    mock_guild.me.top_role.__le__ = MagicMock(return_value=False)
    return m


@pytest.fixture
def sentinel_ctx(mock_guild, mod_author) -> MagicMock:
    """Return a mock Context for sentinel commands."""
    return _make_ctx(mock_guild, mod_author)


@pytest.fixture
def warn_row() -> dict:
    """Return a sample WARN infraction DB row."""
    return {
        "id": "inf-001",
        "guildId": "123456789",
        "targetId": "555555555",
        "moderatorId": "111111111",
        "type": "WARN",
        "reason": "test reason",
        "active": True,
        "createdAt": datetime.now(UTC),
    }


@pytest.fixture
def member_row() -> dict:
    """Return a sample member DB row."""
    return {
        "guildId": "123456789",
        "userId": "555555555",
        "xp": 100,
        "level": 1,
        "warnings": 1,
        "coins": 50,
    }


# ---------------------------------------------------------------------------
# 3.6 — warn / unwarn commands
# ---------------------------------------------------------------------------


class TestWarnCommand:
    """Tests for the warn command."""

    async def test_warn_persists_infraction_and_sends_log_embed(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
        warn_row: dict,
        member_row: dict,
    ) -> None:
        """warn → insert_infraction called + log_moderation_action called + success embed."""
        mock_db.insert_infraction = AsyncMock(return_value=warn_row)
        mock_db.get_member = AsyncMock(return_value=member_row)
        mock_db.update_member_warnings = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.warn.callback(sentinel_cog, sentinel_ctx, target_member, reason="test reason")

        mock_db.insert_infraction.assert_awaited_once()
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Warned" in embed.title


class TestUnwarnCommand:
    """Tests for the unwarn command."""

    async def test_unwarn_deactivates_infraction(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """unwarn → deactivate_infraction called + success embed."""
        mock_db.get_active_warnings = AsyncMock(
            return_value=[
                {
                    "id": "inf-001",
                    "guildId": "123456789",
                    "targetId": "555555555",
                    "moderatorId": "111111111",
                    "type": "WARN",
                    "reason": "test",
                    "active": True,
                    "createdAt": datetime.now(UTC),
                }
            ]
        )
        mock_db.deactivate_infraction = AsyncMock()
        mock_db.update_member_warnings = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.unwarn.callback(sentinel_cog, sentinel_ctx, target_member)

        mock_db.deactivate_infraction.assert_awaited_once_with("inf-001")
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Revoked" in embed.title

    async def test_unwarn_no_warnings_shows_info(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """unwarn with no active warnings → info embed."""
        mock_db.get_active_warnings = AsyncMock(return_value=[])

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.unwarn.callback(sentinel_cog, sentinel_ctx, target_member)

        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "No" in embed.title


# ---------------------------------------------------------------------------
# 3.7 — mute / unmute / kick / ban commands
# ---------------------------------------------------------------------------


class TestMuteCommand:
    """Tests for the mute command."""

    async def test_mute_adds_timeout_and_logs(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """mute → member.timeout called + infraction inserted + log embed."""
        target_member.timeout = AsyncMock()
        mock_db.insert_infraction = AsyncMock(
            return_value={
                "id": "inf-mute-001",
                "guildId": "123456789",
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "MUTE",
                "reason": "spamming",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
        )

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.mute.callback(
                sentinel_cog, sentinel_ctx, target_member, duration="1h", reason="spamming"
            )

        target_member.timeout.assert_awaited_once()
        timeout_args = target_member.timeout.call_args
        assert timeout_args[0][0] == timedelta(seconds=3600)
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Muted" in embed.title


class TestUnmuteCommand:
    """Tests for the unmute command."""

    async def test_unmute_removes_timeout_and_logs(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """unmute → member.timeout(None) called + log embed."""
        target_member.timeout = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.unmute.callback(sentinel_cog, sentinel_ctx, target_member)

        target_member.timeout.assert_awaited_once_with(None, reason=f"Unmuted by {sentinel_ctx.author}")
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Unmuted" in embed.title


class TestKickCommand:
    """Tests for the kick command."""

    async def test_kick_calls_guild_kick(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """kick → member.kick called + infraction inserted + log embed."""
        target_member.kick = AsyncMock()
        mock_db.insert_infraction = AsyncMock(
            return_value={
                "id": "inf-kick-001",
                "guildId": "123456789",
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "KICK",
                "reason": "rule violation",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
        )

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

        target_member.kick.assert_awaited_once_with(reason="rule violation")
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Kicked" in embed.title


class TestBanCommand:
    """Tests for the ban command."""

    async def test_ban_calls_guild_ban(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """ban → member.ban called + infraction inserted + log embed."""
        target_member.ban = AsyncMock()
        mock_db.insert_infraction = AsyncMock(
            return_value={
                "id": "inf-ban-001",
                "guildId": "123456789",
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "BAN",
                "reason": "severe violation",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
        )

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.ban.callback(sentinel_cog, sentinel_ctx, target_member, reason="severe violation")

        target_member.ban.assert_awaited_once()
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Banned" in embed.title


# ---------------------------------------------------------------------------
# 3.8 — lock / unlock / modlogs + helpers
# ---------------------------------------------------------------------------


class TestLockCommand:
    """Tests for the lock command."""

    async def test_lock_sets_channel_permissions(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        mock_guild,
    ) -> None:
        """lock → channel.set_permissions called for @everyone."""
        channel = MagicMock()
        channel.mention = "<#111111>"
        channel.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
        channel.set_permissions = AsyncMock()
        sentinel_ctx.channel = channel

        mock_guild.default_role = MagicMock()
        sentinel_ctx.guild = mock_guild

        await sentinel_cog.lock.callback(sentinel_cog, sentinel_ctx, channel=None)

        channel.set_permissions.assert_awaited_once()
        call_kwargs = channel.set_permissions.call_args
        assert call_kwargs[0][0] == mock_guild.default_role
        overwrite = call_kwargs.kwargs.get("overwrite") or call_kwargs[1].get("overwrite")
        assert overwrite.send_messages is False

        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Locked" in embed.title


class TestUnlockCommand:
    """Tests for the unlock command."""

    async def test_unlock_restores_channel_permissions(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        mock_guild,
    ) -> None:
        """unlock → channel.set_permissions called with send_messages=None."""
        channel = MagicMock()
        channel.mention = "<#111111>"
        channel.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite(send_messages=False))
        channel.set_permissions = AsyncMock()
        sentinel_ctx.channel = channel

        mock_guild.default_role = MagicMock()
        sentinel_ctx.guild = mock_guild

        await sentinel_cog.unlock.callback(sentinel_cog, sentinel_ctx, channel=None)

        channel.set_permissions.assert_awaited_once()
        call_kwargs = channel.set_permissions.call_args
        overwrite = call_kwargs.kwargs.get("overwrite") or call_kwargs[1].get("overwrite")
        assert overwrite.send_messages is None

        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Unlocked" in embed.title


class TestModlogsCommand:
    """Tests for the modlogs command."""

    async def test_modlogs_shows_infraction_history(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """modlogs → paginated embed sent with infraction entries."""
        infractions = []
        for i in range(7):
            infractions.append(
                {
                    "id": f"inf-{i:03d}",
                    "guildId": "123456789",
                    "targetId": "555555555",
                    "moderatorId": "111111111",
                    "type": "WARN",
                    "reason": f"reason {i}",
                    "active": True,
                    "createdAt": datetime.now(UTC),
                }
            )
        mock_db.get_infractions = AsyncMock(return_value=infractions)

        await sentinel_cog.modlogs.callback(sentinel_cog, sentinel_ctx, target_member, type=None, after=None)

        sentinel_ctx.send.assert_awaited_once()
        call_kwargs = sentinel_ctx.send.call_args
        # Should have view for pagination (7 > MODLOGS_PER_PAGE=5).
        assert call_kwargs.kwargs.get("view") is not None


class TestModlogsPaginator:
    """Tests for _ModlogsPaginator prev/next navigation."""

    def test_prev_button_disabled_at_start(self) -> None:
        """Prev button disabled on page 0."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = _ModlogsPaginator(pages)
        children = list(view.children)
        assert children[0].disabled is True
        assert children[1].disabled is False

    async def test_next_button_advances_page(self) -> None:
        """Next button advances to next page and updates embed."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = _ModlogsPaginator(pages)
        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view.next_button.callback(interaction)

        assert view._current == 1
        interaction.response.edit_message.assert_awaited_once()

    async def test_prev_button_goes_back(self) -> None:
        """Prev button goes back after advancing."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = _ModlogsPaginator(pages)
        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        # Advance to page 2.
        view._current = 2
        view._update_buttons()

        await view.prev_button.callback(interaction)

        assert view._current == 1

    def test_next_button_disabled_at_end(self) -> None:
        """Next button disabled on last page."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(2)]
        view = _ModlogsPaginator(pages)
        view._current = 1
        view._update_buttons()
        children = list(view.children)
        assert children[1].disabled is True


class TestValidateTarget:
    """Tests for _validate_target helper."""

    async def test_self_target_rejection(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
    ) -> None:
        """Self-target returns False and sends error embed."""
        target = MagicMock()
        target.id = sentinel_ctx.author.id
        target.mention = "<@111111111>"

        result = await sentinel_cog._validate_target(sentinel_ctx, target, "warn")

        assert result is False
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "yourself" in embed.description

    async def test_higher_role_target_rejection(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        mock_guild,
    ) -> None:
        """Target with higher role returns False and sends error embed."""
        target = MagicMock()
        target.id = 555555555
        target.mention = "<@555555555>"
        target.top_role = MagicMock()
        # Target role is above bot role.
        target.top_role.__le__ = MagicMock(return_value=False)

        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        # bot.top_role <= target.top_role → True (bot is below target).
        mock_guild.me.top_role.__le__ = MagicMock(return_value=True)
        sentinel_ctx.guild = mock_guild

        result = await sentinel_cog._validate_target(sentinel_ctx, target, "warn")

        assert result is False
        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Role Hierarchy" in embed.title


class TestHandleModError:
    """Tests for _handle_mod_error helper."""

    async def test_forbidden_maps_to_permission_error(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """discord.Forbidden → permission error embed."""
        await sentinel_cog._handle_mod_error(
            sentinel_ctx, discord.Forbidden(response=MagicMock(), message="no perm"), "mute", target_member
        )

        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Permission Denied" in embed.title

    async def test_http_exception_maps_to_action_failed(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """discord.HTTPException → action failed embed."""
        await sentinel_cog._handle_mod_error(
            sentinel_ctx, discord.HTTPException(response=MagicMock(), message="http error"), "kick", target_member
        )

        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert "Action Failed" in embed.title
