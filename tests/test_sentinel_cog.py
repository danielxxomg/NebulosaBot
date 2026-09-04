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

import pathlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from freezegun import freeze_time

from bot.cogs.sentinel import SentinelCog, UnbanTarget, _build_modlog_pages
from bot.core.i18n import load_locales, set_guild_language, t
from bot.models.infraction import Infraction
from bot.services.infraction_service import InfractionService
from bot.services.logging_service import LoggingService
from bot.utils.paginator import EmbedPaginator

# Ensure real locales are loaded for sentinel_cog tests.
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
    # Confirm-flow commands post the final result to ctx.channel — the send
    # must be awaitable in mocks (C2 permanence contract).
    ctx.channel.send = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


def _confirm_sent_view(
    ctx: MagicMock,
) -> tuple[MagicMock, discord.ui.Button]:
    """Return (confirm_interaction, confirm_button) for the posted ConfirmCancelView.

    Superset of the seven former inline confirm-simulation blocks: the
    interaction user is a Member mock carrying the invoker's id, and both
    response.edit_message and response.send_message are AsyncMocks (the
    execute-path call sites exercise rejection edits via send_message).
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = ctx.author.id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    view = ctx.send.call_args.kwargs.get("view")
    confirm_button = next(
        c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:confirm"
    )
    return interaction, confirm_button


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sentinel_bot(mock_db) -> MagicMock:
    """Return a mock NebulosaBot wired for sentinel tests."""
    # Ensure guild language is set so t() returns localized strings.
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
    m = MagicMock(spec=discord.Member)
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
        warn_row: dict,
    ) -> None:
        """unwarn → deactivate_infraction called + success embed."""
        mock_db.get_active_warnings = AsyncMock(return_value=[warn_row])
        mock_db.deactivate_infraction = AsyncMock()
        mock_db.update_member_warnings = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.unwarn.callback(sentinel_cog, sentinel_ctx, target_member)

        mock_db.deactivate_infraction.assert_awaited_once_with("123456789", "inf-001")
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
    ) -> None:
        """mute → member.timeout called + infraction inserted + log embed."""
        target_member.timeout = AsyncMock()
        service_mute = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "mute", service_mute),
        ):
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
    """Tests for the kick command with confirmation dialog."""

    async def test_kick_shows_confirmation_before_executing(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """kick → sends ephemeral ConfirmCancelView, does NOT kick immediately."""
        target_member.kick = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

        # Should send ephemeral confirmation, NOT kick directly.
        target_member.kick.assert_not_awaited()
        sentinel_ctx.send.assert_awaited_once()
        call_kwargs = sentinel_ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        # Should include a view (ConfirmCancelView).
        assert call_kwargs.get("view") is not None

    async def test_kick_confirm_executes_kick(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """kick confirm → member.kick called + infraction inserted + log embed."""
        target_member.kick = AsyncMock()
        service_kick = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "kick", service_kick),
        ):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

            interaction, confirm_button = _confirm_sent_view(sentinel_ctx)

            await confirm_button.callback(interaction)

        target_member.kick.assert_awaited_once_with(reason="rule violation")
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()

    async def test_kick_wires_message_for_timeout(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """kick → view.message is the Message returned by ctx.send().

        Production wiring: ctx.send() returns a Message, and the view must
        store it so on_timeout can edit it. No private attribute injection.
        """
        mock_message = AsyncMock()
        sentinel_ctx.send = AsyncMock(return_value=mock_message)
        target_member.kick = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

        view = sentinel_ctx.send.call_args.kwargs.get("view")
        assert view is not None
        assert view.message is mock_message

    async def test_kick_timeout_edits_wired_message(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """kick → on_timeout edits the message wired by production code.

        Full production flow: kick sends confirmation, ctx.send returns a
        message which is wired to view.message, then on_timeout edits it.
        """
        mock_message = AsyncMock()
        sentinel_ctx.send = AsyncMock(return_value=mock_message)
        target_member.kick = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

        view = sentinel_ctx.send.call_args.kwargs.get("view")
        assert view is not None

        # Simulate timeout — should edit the wired message.
        await view.on_timeout()

        mock_message.edit.assert_awaited_once()
        call_kwargs = mock_message.edit.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
        assert embed is not None
        assert "Timed Out" in embed.title


class TestBanCommand:
    """Tests for the ban command with confirmation dialog."""

    async def test_ban_shows_confirmation_before_executing(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """ban → sends ephemeral ConfirmCancelView, does NOT ban immediately."""
        target_member.ban = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.ban.callback(sentinel_cog, sentinel_ctx, target_member, reason="severe violation")

        # Should send ephemeral confirmation, NOT ban directly.
        target_member.ban.assert_not_awaited()
        sentinel_ctx.send.assert_awaited_once()
        call_kwargs = sentinel_ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert call_kwargs.get("view") is not None

    async def test_ban_confirm_executes_ban(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """ban confirm → member.ban called + infraction inserted + log embed."""
        target_member.ban = AsyncMock()
        service_ban = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "ban", service_ban),
        ):
            await sentinel_cog.ban.callback(
                sentinel_cog,
                sentinel_ctx,
                target_member,
                reason="severe violation",
                delete_days=3,
            )

            interaction, confirm_button = _confirm_sent_view(sentinel_ctx)

            await confirm_button.callback(interaction)

        target_member.ban.assert_awaited_once()
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once()

    async def test_ban_wires_message_for_timeout(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """ban → view.message is the Message returned by ctx.send().

        Production wiring: ctx.send() returns a Message, and the view must
        store it so on_timeout can edit it. No private attribute injection.
        """
        mock_message = AsyncMock()
        sentinel_ctx.send = AsyncMock(return_value=mock_message)
        target_member.ban = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.ban.callback(sentinel_cog, sentinel_ctx, target_member, reason="severe violation")

        view = sentinel_ctx.send.call_args.kwargs.get("view")
        assert view is not None
        assert view.message is mock_message

    async def test_ban_timeout_edits_wired_message(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """ban → on_timeout edits the message wired by production code.

        Full production flow: ban sends confirmation, ctx.send returns a
        message which is wired to view.message, then on_timeout edits it.
        """
        mock_message = AsyncMock()
        sentinel_ctx.send = AsyncMock(return_value=mock_message)
        target_member.ban = AsyncMock()

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.ban.callback(sentinel_cog, sentinel_ctx, target_member, reason="severe violation")

        view = sentinel_ctx.send.call_args.kwargs.get("view")
        assert view is not None

        # Simulate timeout — should edit the wired message.
        await view.on_timeout()

        mock_message.edit.assert_awaited_once()
        call_kwargs = mock_message.edit.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
        assert embed is not None
        assert "Timed Out" in embed.title


class TestAuditReasonLocalization:
    """Audit-log reasons reaching localized log embeds MUST be guild-localized.

    The cog passes free-text reasons into LoggingService.log_moderation_action;
    with embed titles/labels now localized (cycle-5 S3), the reason body is
    the remaining user-facing fragment — route every constant through t().
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("command_name", "expected_reason"),
        [
            pytest.param("unwarn", None, id="unwarn"),
            pytest.param("unmute", None, id="unmute"),
            pytest.param("lock", None, id="lock"),
            pytest.param("unlock", None, id="unlock"),
            pytest.param("unban", "424242", id="unban"),
        ],
    )
    async def test_audit_reason_localized(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
        mock_guild,
        warn_row: dict,
        command_name: str,
        expected_reason: str | None,
    ) -> None:
        """Command audit reasons reaching log_moderation_action MUST resolve t() keys.

        Each branch mirrors its original dedicated test: unwarn deactivates
        the warn_row, unmute clears a timeout, lock/unlock set channel perms
        (no _validate_target patch — no member target), unban drives an
        active BAN row through the real service with user_id "424242".
        """
        command = getattr(sentinel_cog, command_name)
        if command_name == "unwarn":
            mock_db.get_active_warnings = AsyncMock(return_value=[warn_row])
            mock_db.deactivate_infraction = AsyncMock()
            mock_db.update_member_warnings = AsyncMock()
        elif command_name == "unmute":
            target_member.timeout = AsyncMock()
        elif command_name in ("lock", "unlock"):
            sentinel_ctx.channel.set_permissions = AsyncMock()
        elif command_name == "unban":
            mock_guild.unban = AsyncMock()
            mock_db_row = {
                "id": "inf-unban-001",
                "guildId": "123456789",
                "targetId": "424242",
                "moderatorId": "111111111",
                "type": "BAN",
                "reason": "spam",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
            sentinel_bot.db.get_infractions = AsyncMock(return_value=[mock_db_row])
            sentinel_bot.db.deactivate_infraction = AsyncMock()

        expected_reason = ""
        if command_name == "unwarn":
            expected_reason = t("123456789", "sentinel.unwarn.audit_reason", id=warn_row["id"])
        elif command_name == "unmute":
            expected_reason = t("123456789", "sentinel.unmute.audit_reason")
        elif command_name == "lock":
            expected_reason = t("123456789", "sentinel.lock.audit_reason", channel=sentinel_ctx.channel.mention)
        elif command_name == "unlock":
            expected_reason = t("123456789", "sentinel.unlock.audit_reason", channel=sentinel_ctx.channel.mention)
        elif command_name == "unban":
            expected_reason = t("123456789", "sentinel.unban.audit_reason", user_id="424242")

        if command_name in ("unwarn", "unmute"):
            with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
                if expected_reason is not None and command_name == "unban":
                    await command.callback(sentinel_cog, sentinel_ctx, expected_reason)
                elif command_name == "unban":
                    await command.callback(sentinel_cog, sentinel_ctx, "424242")
                else:
                    await command.callback(sentinel_cog, sentinel_ctx, target_member)
        elif command_name == "unban":
            await command.callback(sentinel_cog, sentinel_ctx, "424242")
        else:
            await command.callback(sentinel_cog, sentinel_ctx, None)

        log_args = sentinel_bot.logging_service.log_moderation_action.await_args.args
        assert log_args[4] == expected_reason

    def test_modlogs_unknown_date_localized(self, mock_guild) -> None:
        """modlog entries without created_at show the localized unknown label."""
        infraction = Infraction(
            id="inf-x",
            guild_id="123456789",
            target_id="555555555",
            moderator_id="111111111",
            type="WARN",
            reason="spam",
            created_at=None,  # type: ignore[arg-type]
        )

        pages = _build_modlog_pages(mock_guild, [infraction], guild_id="123456789")

        assert pages, "one entry must build one page"
        field_value = pages[0].fields[0].value or ""
        assert t("123456789", "sentinel.modlogs.unknown_date") in field_value

    @pytest.mark.asyncio
    async def test_mute_default_reason_localized(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """mute without explicit reason uses the localized default."""
        target_member.timeout = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "mute", AsyncMock()),
        ):
            await sentinel_cog.mute.callback(sentinel_cog, sentinel_ctx, target_member, duration="1h")

        expected_default = t("123456789", "sentinel.default_reason")
        timeout_kwargs = target_member.timeout.call_args.kwargs
        assert timeout_kwargs["reason"] == expected_default

    @pytest.mark.asyncio
    async def test_tempban_default_reason_localized_in_confirm_dialog(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """tempban without explicit reason shows the localized default in its dialog."""
        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await sentinel_cog.tempban.callback(sentinel_cog, sentinel_ctx, target_member, duration="2h")

        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert t("123456789", "sentinel.default_reason") in (embed.description or "")


class TestModerationServiceSwap:
    """SentinelCog persists MUTE/KICK/BAN via InfractionService (spec infraction-service).

    Cogs MUST NOT insert infraction rows directly: the persistence step
    goes through infraction_service.mute/kick/ban, while the cog keeps
    the Discord side-effect and the single caller-side audit call.
    """

    @pytest.mark.asyncio
    async def test_mute_persists_via_service(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """mute → infraction_service.mute called with identifier args."""
        target_member.timeout = AsyncMock()
        service_mute = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "mute", service_mute),
        ):
            await sentinel_cog.mute.callback(sentinel_cog, sentinel_ctx, target_member, duration="1h", reason="spam")

        service_mute.assert_awaited_once_with("123456789", "555555555", "111111111", "spam")

    @pytest.mark.asyncio
    async def test_mute_never_inserts_infraction_directly(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """mute → no direct db.insert_infraction from the cog."""
        target_member.timeout = AsyncMock()
        mock_db.insert_infraction = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "mute", AsyncMock()),
        ):
            await sentinel_cog.mute.callback(sentinel_cog, sentinel_ctx, target_member, duration="1h", reason="spam")

        mock_db.insert_infraction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_kick_persists_via_service_on_confirm(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """kick confirm → infraction_service.kick called; no direct insert."""
        target_member.kick = AsyncMock()
        service_kick = AsyncMock()
        sentinel_bot.db.insert_infraction = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "kick", service_kick),
        ):
            await sentinel_cog.kick.callback(sentinel_cog, sentinel_ctx, target_member, reason="rule violation")

            interaction, confirm_button = _confirm_sent_view(sentinel_ctx)

            await confirm_button.callback(interaction)

        service_kick.assert_awaited_once_with("123456789", "555555555", "111111111", "rule violation")
        sentinel_bot.db.insert_infraction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ban_persists_via_service_on_confirm(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
    ) -> None:
        """ban confirm → infraction_service.ban called; no direct insert."""
        target_member.ban = AsyncMock()
        service_ban = AsyncMock()
        sentinel_bot.db.insert_infraction = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            patch.object(InfractionService, "ban", service_ban),
        ):
            await sentinel_cog.ban.callback(
                sentinel_cog, sentinel_ctx, target_member, reason="severe violation", delete_days=3
            )

            interaction, confirm_button = _confirm_sent_view(sentinel_ctx)

            await confirm_button.callback(interaction)

        service_ban.assert_awaited_once_with("123456789", "555555555", "111111111", "severe violation")
        sentinel_bot.db.insert_infraction.assert_not_awaited()


class TestKickBanPermanentResult:
    """C2 (spec ephemeral-standard): final kick/ban result MUST be permanent.

    The ephemeral ConfirmCancelView gets a closed notice; the success result
    MUST be posted to the channel as a permanent message (tempban two-step).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("command_name", "reason", "delete_days", "member_method", "success_key"),
        [
            pytest.param("kick", "trolling", None, "kick", "sentinel.kick.success_title", id="kick"),
            pytest.param("ban", "harassment", 0, "ban", "sentinel.ban.success_title", id="ban"),
        ],
    )
    async def test_final_result_posted_permanently_to_channel(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        command_name: str,
        reason: str,
        delete_days: int,
        member_method: str,
        success_key: str,
    ) -> None:
        """kick/ban confirm → ephemeral edit is a closed notice; success goes permanent."""
        setattr(target_member, member_method, AsyncMock())
        command = getattr(sentinel_cog, command_name)
        kwargs: dict[str, object] = {"reason": reason}
        if delete_days is not None:
            kwargs["delete_days"] = delete_days

        with patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)):
            await command.callback(sentinel_cog, sentinel_ctx, target_member, **kwargs)

        interaction, confirm_button = _confirm_sent_view(sentinel_ctx)
        await confirm_button.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        await_args = interaction.response.edit_message.await_args
        assert await_args is not None
        edited_embed = await_args.kwargs.get("embed")
        assert edited_embed is not None
        assert edited_embed.title != t("123456789", success_key), (
            "ephemeral dialog must not double as the permanent record"
        )

        # Final result MUST be a permanent channel message (no ephemeral flag).
        sentinel_ctx.channel.send.assert_awaited_once()
        channel_kwargs = sentinel_ctx.channel.send.await_args.kwargs
        assert channel_kwargs.get("ephemeral") is not True, "final result must be permanent"
        result_embed = channel_kwargs.get("embed")
        assert result_embed is not None
        assert result_embed.title == t("123456789", success_key)


class TestTempbanNoDrift:
    """C11 (spec tempban 'no drift'): expires_at computed once AFTER Confirm."""

    @pytest.mark.asyncio
    async def test_expires_at_computed_at_execution_not_invocation(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        mock_db,
    ) -> None:
        """30s+ dialog latency must NOT drift expiresAt from real ban start."""
        row = {
            "id": "inf-tempban-001",
            "guildId": "123456789",
            "targetId": "555555555",
            "moderatorId": "111111111",
            "type": "BAN",
            "reason": "spam",
            "active": True,
            "createdAt": datetime.now(UTC),
            "expiresAt": None,
        }
        mock_db.insert_infraction = AsyncMock(return_value=row)
        target_member.ban = AsyncMock()

        with (
            patch.object(sentinel_cog, "_validate_target", new=AsyncMock(return_value=True)),
            freeze_time("2024-06-15 12:00:00") as ft,
        ):
            await sentinel_cog.tempban.callback(
                sentinel_cog, sentinel_ctx, target_member, duration="24h", reason="spam"
            )
            # Moderator deliberates past the 30s dialog window.
            ft.tick(delta=timedelta(seconds=35))

            interaction, confirm_button = _confirm_sent_view(sentinel_ctx)
            await confirm_button.callback(interaction)

        insert_args = mock_db.insert_infraction.await_args
        assert insert_args is not None
        kwargs = insert_args.kwargs
        assert kwargs["expires_at"] == "2024-06-16T12:00:35+00:00", (
            f"expiresAt must be execution-time + 24h, got {kwargs.get('expires_at')!r}"
        )


class TestUnbanTypedTarget:
    """C10 (spec unban): typed UnbanTarget value object replaces Object+patching."""

    @pytest.mark.asyncio
    async def test_unban_resolves_typed_target_without_monkey_patching(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        sentinel_ctx: MagicMock,
        mock_db,
        mock_guild,
    ) -> None:
        """unban → guild.unban + logging receive an UnbanTarget; no attr fabrication."""

        ban_row = {
            "id": "inf-ban-active",
            "guildId": "123456789",
            "targetId": "555000111",
            "moderatorId": "111111111",
            "type": "BAN",
            "reason": "tempban",
            "active": True,
            "createdAt": datetime.now(UTC),
            "expiresAt": None,
        }
        mock_db.get_infractions = AsyncMock(return_value=[ban_row])
        mock_db.deactivate_infraction = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.unban = AsyncMock()
        sentinel_ctx.guild = guild

        await sentinel_cog.unban.callback(sentinel_cog, sentinel_ctx, user_id="555000111")

        guild.unban.assert_awaited_once()
        unban_args = guild.unban.await_args
        assert unban_args is not None
        unban_arg = unban_args.args[0]
        assert isinstance(unban_arg, UnbanTarget), "target must be a typed UnbanTarget"
        assert not isinstance(unban_arg, discord.Object), "discord.Object must not be used"
        assert unban_arg.id == 555000111

        logged_target = sentinel_bot.logging_service.log_moderation_action.await_args.args[2]
        assert type(logged_target) is UnbanTarget, "logging must receive the same typed value object"
        assert logged_target.mention == "<@555000111>"
        assert logged_target.name == "555000111"


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
        channel = MagicMock(spec=discord.TextChannel)
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
        channel = MagicMock(spec=discord.TextChannel)
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
            infractions.append({
                "id": f"inf-{i:03d}",
                "guildId": "123456789",
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "WARN",
                "reason": f"reason {i}",
                "active": True,
                "createdAt": datetime.now(UTC),
            })
        mock_db.get_infractions = AsyncMock(return_value=infractions)

        await sentinel_cog.modlogs.callback(sentinel_cog, sentinel_ctx, target_member, type=None, after=None)

        sentinel_ctx.send.assert_awaited_once()
        call_kwargs = sentinel_ctx.send.call_args
        # Should have view for pagination (7 > MODLOGS_PER_PAGE=5).
        assert call_kwargs.kwargs.get("view") is not None


class TestModlogsPaginator:
    """Tests for EmbedPaginator used in /modlogs prev/next navigation."""

    def test_prev_button_disabled_at_start(self) -> None:
        """Prev button disabled on page 0."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = EmbedPaginator(pages, custom_id_prefix="modlogs:")
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[0].disabled is True
        assert buttons[1].disabled is False

    async def test_next_button_advances_page(self) -> None:
        """Next button advances to next page and updates embed."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = EmbedPaginator(pages, custom_id_prefix="modlogs:")
        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view.next_button.callback(interaction)

        assert view.current_page == 1
        interaction.response.edit_message.assert_awaited_once()

    async def test_prev_button_goes_back(self) -> None:
        """Prev button goes back after advancing."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = EmbedPaginator(pages, custom_id_prefix="modlogs:")
        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        # Advance to page 2.
        view.current_page = 2
        view.update_buttons()

        await view.prev_button.callback(interaction)

        assert view.current_page == 1

    def test_next_button_disabled_at_end(self) -> None:
        """Next button disabled on last page."""
        pages = [discord.Embed(title=f"Page {i}") for i in range(2)]
        view = EmbedPaginator(pages, custom_id_prefix="modlogs:")
        view.current_page = 1
        view.update_buttons()
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[1].disabled is True


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

    @pytest.mark.parametrize(
        ("exc", "action", "expected_title_fragment"),
        [
            pytest.param(
                discord.Forbidden(response=MagicMock(), message="no perm"), "mute", "Permission Denied", id="forbidden"
            ),
            pytest.param(
                discord.HTTPException(response=MagicMock(), message="http error"),
                "kick",
                "Action Failed",
                id="http-exception",
            ),
        ],
    )
    async def test_error_type_maps_to_expected_embed_title(
        self,
        sentinel_cog: SentinelCog,
        sentinel_ctx: MagicMock,
        target_member: MagicMock,
        exc: Exception,
        action: str,
        expected_title_fragment: str,
    ) -> None:
        """_handle_mod_error maps exception type to the matching error embed."""
        await sentinel_cog._handle_mod_error(sentinel_ctx, exc, action, target_member)

        sentinel_ctx.send.assert_awaited_once()
        embed = sentinel_ctx.send.call_args.kwargs.get("embed")
        assert expected_title_fragment in embed.title


# ---------------------------------------------------------------------------
# Permission wiring (harden-command-permissions)
# ---------------------------------------------------------------------------


def test_warn_is_mod_dual_path_gated(sentinel_cog: SentinelCog) -> None:
    """warn MUST be gated by can_check(moderation.warn) via slash checks.

    S6A: slash-only — hybrid dual-path (cmd.checks + app_command.checks) is
    gone. Pure app_commands.Command exposes checks directly on cmd.checks.
    """
    cmd = sentinel_cog.warn
    assert cmd is not None
    # Slash-only: single checks list on the Command
    assert hasattr(cmd, "checks") and len(cmd.checks) > 0, (
        "warn must have slash checks from @can_check(moderation.warn)"
    )
    # Must NOT be hybrid anymore
    assert not hasattr(cmd, "app_command"), "warn must be pure app command, not hybrid"


# ---------------------------------------------------------------------------
# PR1 6.2 — /ban re-gated to can_check("moderation.ban")
# ---------------------------------------------------------------------------


def test_ban_is_gated_by_can_check_moderation_ban(sentinel_cog: SentinelCog) -> None:
    """PR1 6.2: /ban MUST be gated by can_check(moderation.ban) not is_admin.

    Characterization: admin, matrix role, and mod fallback all pass; outsider denied.
    We prove dual registration and that can_check is the decorator used.
    """

    src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
    # ban decorator must be can_check("moderation.ban")
    assert 'can_check("moderation.ban")' in src or "can_check('moderation.ban')" in src
    # must not be is_admin on ban
    # Find the ban method definition and the decorator lines above it
    lines = src.splitlines()
    ban_idx = next(i for i, line in enumerate(lines) if "async def ban(" in line)
    window = "\n".join(lines[max(0, ban_idx - 10) : ban_idx])
    assert "is_admin" not in window, "ban MUST NOT use @is_admin — must use @can_check"
    assert "can_check" in window

    # Slash-only: single checks list
    cmd = sentinel_cog.ban
    assert hasattr(cmd, "checks") and len(cmd.checks) > 0
    assert not hasattr(cmd, "app_command"), "ban must be pure app command"


def test_ban_keeps_confirm_view_and_default_permissions(sentinel_cog: SentinelCog) -> None:
    """PR1 6.2: /ban MUST keep ConfirmCancelView + default_permissions(ban_members=True)."""

    src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
    # Check ban decorator area + its ConfirmCancelView usage (below the method)
    lines = src.splitlines()
    ban_idx = next(i for i, line in enumerate(lines) if "async def ban(" in line)
    decorator_window = "\n".join(lines[max(0, ban_idx - 15) : ban_idx + 1])
    assert "default_permissions(ban_members=True)" in decorator_window
    # ConfirmCancelView is inside the ban method body (~80 lines below)
    body_window = "\n".join(lines[ban_idx : ban_idx + 120])
    assert "ConfirmCancelView" in body_window
