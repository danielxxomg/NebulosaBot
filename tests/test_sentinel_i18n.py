"""Unit tests for SentinelCog i18n migration.

Verifies that sentinel commands return localized embeds using t()
instead of hardcoded strings.

Uses custom locale overrides with distinctive marker strings to prove
t() is called — same pattern as test_utility_i18n.py. Every command
concept is parametrized over the shared ES/EN locale matrix.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.sentinel import SentinelCog, _build_modlog_pages
from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales, set_guild_language
from bot.utils.paginator import EmbedPaginator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GUILD_ID_ES = 111111111
_GUILD_ID_EN = 222222222

# Locale matrix shared by every command concept below.
_LOCALE_MATRIX = [
    pytest.param(_GUILD_ID_ES, "ES", id="es"),
    pytest.param(_GUILD_ID_EN, "EN", id="en"),
]

# Marker strings — intentionally ugly so they're unmistakable in assertions.
_ES_MARKERS = {
    "sentinel.validate.self_target_title": "VAL_SELF_TITLE_ES",
    "sentinel.validate.self_target_description": "VAL_SELF_DESC_ES_{action}",
    "sentinel.validate.cannot_self_description": "VAL_CANNOT_SELF_DESC_ES_{action}",
    "sentinel.validate.role_hierarchy_title": "VAL_ROLE_TITLE_ES",
    "sentinel.validate.role_hierarchy_description": "VAL_ROLE_DESC_ES_{action}_{mention}",
    "sentinel.error.permission_denied_title": "ERR_PERM_TITLE_ES",
    "sentinel.error.permission_denied_description": "ERR_PERM_DESC_ES_{action}_{mention}",
    "sentinel.error.action_failed_title": "ERR_ACTION_TITLE_ES",
    "sentinel.error.action_failed_description": "ERR_ACTION_DESC_ES_{action}_{mention}",
    "sentinel.error.unexpected_title": "ERR_UNEXPECTED_TITLE_ES",
    "sentinel.error.unexpected_description": "ERR_UNEXPECTED_DESC_ES_{action}_{mention}",
    "sentinel.warn.failed_title": "WARN_FAIL_TITLE_ES",
    "sentinel.warn.failed_description": "WARN_FAIL_DESC_ES",
    "sentinel.warn.success_title": "WARN_SUCCESS_TITLE_ES",
    "sentinel.warn.success_description": "WARN_SUCCESS_DESC_ES_{mention}_{reason}",
    "sentinel.warn.auto_mute_description": "WARN_AUTO_MUTE_ES_{mention}_{threshold}",
    "sentinel.warn.auto_mute_failed_description": "WARN_AUTO_MUTE_FAIL_ES_{mention}",
    "sentinel.warn.auto_kick_description": "WARN_AUTO_KICK_ES_{mention}_{threshold}",
    "sentinel.warn.auto_kick_failed_description": "WARN_AUTO_KICK_FAIL_ES_{mention}",
    "sentinel.unwarn.failed_title": "UNWARN_FAIL_TITLE_ES",
    "sentinel.unwarn.failed_description": "UNWARN_FAIL_DESC_ES",
    "sentinel.unwarn.no_warnings_title": "UNWARN_NONE_TITLE_ES",
    "sentinel.unwarn.no_warnings_description": "UNWARN_NONE_DESC_ES_{mention}",
    "sentinel.unwarn.success_title": "UNWARN_SUCCESS_TITLE_ES",
    "sentinel.unwarn.success_description": "UNWARN_SUCCESS_DESC_ES_{mention}",
    "sentinel.mute.success_title": "MUTE_SUCCESS_TITLE_ES",
    "sentinel.mute.success_description": "MUTE_SUCCESS_DESC_ES_{mention}_{duration}_{reason}",
    "sentinel.unmute.success_title": "UNMUTE_SUCCESS_TITLE_ES",
    "sentinel.unmute.success_description": "UNMUTE_SUCCESS_DESC_ES_{mention}",
    "sentinel.kick.success_title": "KICK_SUCCESS_TITLE_ES",
    "sentinel.kick.success_description": "KICK_SUCCESS_DESC_ES_{mention}_{reason}",
    "sentinel.ban.success_title": "BAN_SUCCESS_TITLE_ES",
    "sentinel.ban.success_description": "BAN_SUCCESS_DESC_ES_{mention}_{reason}",
    "confirm.kick_confirm_title": "KICK_CONFIRM_TITLE_ES",
    "confirm.kick_confirm_description": "KICK_CONFIRM_DESC_ES_{mention}_{reason}",
    "confirm.ban_confirm_title": "BAN_CONFIRM_TITLE_ES",
    "confirm.ban_confirm_description": "BAN_CONFIRM_DESC_ES_{mention}_{reason}_{delete_days}",
    "confirm.not_owner_title": "CONFIRM_NOT_OWNER_TITLE_ES",
    "confirm.not_owner_description": "CONFIRM_NOT_OWNER_DESC_ES",
    "confirm.cancelled_title": "CONFIRM_CANCELLED_TITLE_ES",
    "confirm.cancelled_description": "CONFIRM_CANCELLED_DESC_ES",
    "confirm.timeout_title": "CONFIRM_TIMEOUT_TITLE_ES",
    "confirm.timeout_description": "CONFIRM_TIMEOUT_DESC_ES",
    "sentinel.lock.permission_denied_title": "LOCK_PERM_TITLE_ES",
    "sentinel.lock.permission_denied_description": "LOCK_PERM_DESC_ES_{channel}",
    "sentinel.lock.failed_title": "LOCK_FAIL_TITLE_ES",
    "sentinel.lock.failed_description": "LOCK_FAIL_DESC_ES_{channel}",
    "sentinel.lock.success_title": "LOCK_SUCCESS_TITLE_ES",
    "sentinel.lock.success_description": "LOCK_SUCCESS_DESC_ES_{channel}",
    "sentinel.unlock.permission_denied_title": "UNLOCK_PERM_TITLE_ES",
    "sentinel.unlock.permission_denied_description": "UNLOCK_PERM_DESC_ES_{channel}",
    "sentinel.unlock.failed_title": "UNLOCK_FAIL_TITLE_ES",
    "sentinel.unlock.failed_description": "UNLOCK_FAIL_DESC_ES_{channel}",
    "sentinel.unlock.success_title": "UNLOCK_SUCCESS_TITLE_ES",
    "sentinel.unlock.success_description": "UNLOCK_SUCCESS_DESC_ES_{channel}",
    "sentinel.modlogs.failed_title": "MODLOGS_FAIL_TITLE_ES",
    "sentinel.modlogs.failed_description": "MODLOGS_FAIL_DESC_ES",
    "sentinel.modlogs.no_modlogs_title": "MODLOGS_NONE_TITLE_ES",
    "sentinel.modlogs.no_modlogs_description": "MODLOGS_NONE_DESC_ES_{mention}_{filters}",
    "sentinel.modlogs.page_infractions": "MODLOGS_INFRACTIONS_ES_{total}",
    "sentinel.modlogs.page_info": "MODLOGS_PAGE_INFO_ES_{page}_{total_pages}",
    "sentinel.modlogs.title": "MODLOGS_TITLE_ES_{name}",
    "sentinel.modlogs.field_value": "MODLOGS_FIELD_ES_{moderator}_{reason}_{date}",
    "sentinel.modlogs.revoked": "MODLOGS_REVOKED_ES",
    "sentinel.modlogs.footer": "MODLOGS_FOOTER_ES_{id}",
    "sentinel.modlogs.prev_button": "MODLOGS_PREV_ES",
    "sentinel.modlogs.next_button": "MODLOGS_NEXT_ES",
}


def _build_nested_locale(markers: dict[str, str]) -> dict:
    """Convert flat dot-notation keys into a nested dict for locale JSON."""
    result: dict = {}
    for key, value in markers.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result


def _swap_suffix(markers: dict[str, str], sfx: str) -> dict[str, str]:
    """Derive a sibling-locale marker set by swapping the ``_ES`` suffix."""
    return {key: value.replace("_ES", sfx) for key, value in markers.items()}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> Generator[None, None, None]:
    """Load custom locale overrides for sentinel i18n tests."""

    # Save original state.
    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)

    (locale_dir / "es.json").write_text(
        json.dumps(_build_nested_locale(_ES_MARKERS)),
        encoding="utf-8",
    )
    (locale_dir / "en.json").write_text(
        json.dumps(_build_nested_locale(_swap_suffix(_ES_MARKERS, "_EN"))),
        encoding="utf-8",
    )

    load_locales(locale_dir)
    set_guild_language(str(_GUILD_ID_ES), "es")
    set_guild_language(str(_GUILD_ID_EN), "en")

    yield

    # Restore original state so other test modules are not affected.
    i18n_mod._locales.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.clear()
    i18n_mod._guild_languages.update(orig_guild_langs)


@pytest.fixture
def sentinel_bot() -> MagicMock:
    """Return a mock NebulosaBot wired for sentinel i18n tests.

    No ``spec`` on infraction_service/logging_service — avoids auto-creating
    AsyncMock children for unused async methods that leak unawaited coroutines.
    """
    bot = MagicMock()
    bot.db = AsyncMock(return_value=None)
    bot.infraction_service = MagicMock()
    bot.infraction_service.warn = AsyncMock()
    bot.infraction_service.unwarn = AsyncMock()
    bot.infraction_service.get_modlogs = AsyncMock()
    bot.infraction_service.check_escalation = MagicMock()
    bot.logging_service = MagicMock()
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.logging_service._should_log = MagicMock()
    bot.logging_service._send_log = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 999999999
    return bot


@pytest.fixture
def cog(sentinel_bot: MagicMock) -> SentinelCog:
    """Return a SentinelCog for the shared mock bot.

    Language resolution happens inside t() from ``ctx.guild.id``, so a single
    cog instance serves both locales of the matrix.
    """
    return SentinelCog(bot=sentinel_bot)


def _make_ctx(guild_id: int) -> MagicMock:
    """Build a mock Context with the given guild_id.

    No ``spec`` on guild — avoids auto-creating AsyncMock children for
    async Guild methods that leak unawaited coroutines.
    """
    ctx = MagicMock()
    guild = MagicMock()
    guild.id = guild_id
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.me.top_role = MagicMock()
    guild.me.top_role.__le__ = MagicMock(return_value=False)
    ctx.guild = guild
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 111111111
    ctx.author.mention = "<@111111111>"
    ctx.channel = MagicMock()
    ctx.channel.mention = "<#999>"
    ctx.channel.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    ctx.channel.set_permissions = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


def _make_target() -> MagicMock:
    """Build a mock target member below bot role."""
    target = MagicMock()
    target.id = 555555555
    target.mention = "<@555555555>"
    target.name = "TargetUser"
    target.top_role = MagicMock()
    target.top_role.__le__ = MagicMock(return_value=False)
    target.timeout = AsyncMock()
    target.kick = AsyncMock()
    target.ban = AsyncMock()
    return target


# ---------------------------------------------------------------------------
# Warn — localized title
# ---------------------------------------------------------------------------


class TestWarnI18n:
    """warn command returns localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_warn_success_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the warn success title in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.warn.return_value = (
            MagicMock(id="inf-001"),
            None,
        )
        sentinel_bot.db.insert_infraction = AsyncMock(
            return_value={
                "id": "inf-001",
                "guildId": str(guild_id),
                "targetId": "555555555",
                "moderatorId": "111111111",
                "type": "WARN",
                "reason": "test",
                "active": True,
                "createdAt": datetime.now(UTC),
            }
        )
        sentinel_bot.db.get_member = AsyncMock(
            return_value={
                "guildId": str(guild_id),
                "userId": "555555555",
                "warnings": 1,
            }
        )
        sentinel_bot.db.update_member_warnings = AsyncMock()

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.warn.callback(cog, ctx, target, reason="test")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"WARN_SUCCESS_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Unwarn — localized
# ---------------------------------------------------------------------------


class TestUnwarnI18n:
    """unwarn command returns localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_unwarn_success_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the unwarn success message in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.unwarn.return_value = MagicMock(id="inf-001")
        sentinel_bot.db.get_active_warnings = AsyncMock(
            return_value=[
                {
                    "id": "inf-001",
                    "guildId": str(guild_id),
                    "targetId": "555555555",
                    "moderatorId": "111111111",
                    "type": "WARN",
                    "reason": "test",
                    "active": True,
                    "createdAt": datetime.now(UTC),
                }
            ]
        )
        sentinel_bot.db.deactivate_infraction = AsyncMock()
        sentinel_bot.db.update_member_warnings = AsyncMock()

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.unwarn.callback(cog, ctx, target)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"UNWARN_SUCCESS_TITLE_{suffix}" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_unwarn_no_warnings_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the 'no warnings' message in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.unwarn.return_value = None
        sentinel_bot.db.get_active_warnings = AsyncMock(return_value=[])

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.unwarn.callback(cog, ctx, target)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"UNWARN_NONE_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Mute — localized title
# ---------------------------------------------------------------------------


class TestMuteI18n:
    """mute command returns localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_mute_success_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the mute success message in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.mute = AsyncMock()

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.mute.callback(cog, ctx, target, duration="1h", reason="spam")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"MUTE_SUCCESS_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Kick / Ban — localized confirmation dialogs
# ---------------------------------------------------------------------------


class TestKickI18n:
    """kick command returns localized confirmation dialog."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_kick_confirmation_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the kick confirmation dialog in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.kick = AsyncMock()

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.kick.callback(cog, ctx, target, reason="rule violation")

        # Kick sends ephemeral confirmation, not direct success.
        call_kwargs = ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert f"KICK_CONFIRM_TITLE_{suffix}" in embed.title


class TestBanI18n:
    """ban command returns localized confirmation dialog."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_ban_confirmation_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the ban confirmation dialog in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.ban = AsyncMock()

        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.ban.callback(cog, ctx, target, reason="severe")

        # Ban sends ephemeral confirmation, not direct success.
        call_kwargs = ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert f"BAN_CONFIRM_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Lock / Unlock — localized titles
# ---------------------------------------------------------------------------


class TestLockI18n:
    """lock command returns localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_lock_success_is_localized(
        self,
        cog: SentinelCog,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the lock success message in its language."""
        ctx = _make_ctx(guild_id)

        await cog.lock.callback(cog, ctx, channel=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"LOCK_SUCCESS_TITLE_{suffix}" in embed.title


class TestUnlockI18n:
    """unlock command returns localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_unlock_success_is_localized(
        self,
        cog: SentinelCog,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the unlock success message in its language."""
        ctx = _make_ctx(guild_id)
        # Make overwrites have send_messages=False so unlock does something
        ctx.channel.overwrites_for = MagicMock(
            return_value=discord.PermissionOverwrite(send_messages=False),
        )

        await cog.unlock.callback(cog, ctx, channel=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"UNLOCK_SUCCESS_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Modlogs — localized titles + page builder
# ---------------------------------------------------------------------------


class TestModlogsI18n:
    """modlogs command and page builder return localized strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_modlogs_no_infractions_is_localized(
        self,
        cog: SentinelCog,
        sentinel_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Guild gets the 'no modlogs' message in its language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        sentinel_bot.infraction_service.get_modlogs = AsyncMock(return_value=[])

        await cog.modlogs.callback(cog, ctx, target, type=None, after=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"MODLOGS_NONE_TITLE_{suffix}" in embed.title

    @staticmethod
    def _page_builder_target() -> MagicMock:
        """Build a display-ready target for _build_modlog_pages."""
        target = MagicMock()
        target.id = 555555555
        target.display_name = "TestTarget"
        target.display_avatar = MagicMock()
        target.display_avatar.url = "https://cdn.discord.com/avatars/test.png"
        return target

    @staticmethod
    def _sample_infraction() -> MagicMock:
        """Build a minimal infraction row for the page builder."""
        infraction = MagicMock()
        infraction.type = "WARN"
        infraction.moderator_id = "111111111"
        infraction.reason = "test reason"
        infraction.active = True
        infraction.created_at = datetime.now(UTC)
        return infraction

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_modlogs_page_builder_is_localized(
        self,
        guild_id: int,
        suffix: str,
    ) -> None:
        """_build_modlog_pages uses t() for embed title and field values."""
        pages = _build_modlog_pages(
            self._page_builder_target(),
            [self._sample_infraction()],
            guild_id=str(guild_id),
        )

        assert len(pages) == 1
        embed = pages[0]
        assert embed.title is not None
        assert f"MODLOGS_TITLE_{suffix}" in embed.title
        # Field values should use t()
        field_values = {f.value for f in embed.fields if f.value is not None}
        assert any(f"MODLOGS_FIELD_{suffix}" in v for v in field_values)


# ---------------------------------------------------------------------------
# Validate target — localized errors
# ---------------------------------------------------------------------------


class TestValidateTargetI18n:
    """_validate_target returns localized error strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_self_target_is_localized(
        self,
        cog: SentinelCog,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Self-target error renders in the guild language."""
        ctx = _make_ctx(guild_id)
        target = MagicMock()
        target.id = ctx.author.id  # same as author
        target.mention = "<@111111111>"

        result = await cog._validate_target(ctx, target, "warn")

        assert result is False
        embed = ctx.send.call_args.kwargs.get("embed")
        assert f"VAL_SELF_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Handle mod error — localized errors
# ---------------------------------------------------------------------------


class TestHandleModErrorI18n:
    """_handle_mod_error returns localized error strings."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_forbidden_is_localized(
        self,
        cog: SentinelCog,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Forbidden error renders in the guild language."""
        ctx = _make_ctx(guild_id)
        target = _make_target()

        await cog._handle_mod_error(
            ctx,
            discord.Forbidden(response=MagicMock(), message="no"),
            "mute",
            target,
        )

        embed = ctx.send.call_args.kwargs.get("embed")
        assert f"ERR_PERM_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# Paginator button labels — i18n
# ---------------------------------------------------------------------------


class TestPaginatorButtonI18n:
    """EmbedPaginator button labels are localized via t()."""

    @pytest.mark.parametrize(
        ("guild_id", "expected_labels"),
        [
            pytest.param(_GUILD_ID_ES, ("Anterior", "Siguiente", "Detener"), id="es"),
            pytest.param(_GUILD_ID_EN, ("Previous", "Next", "Stop"), id="en"),
        ],
    )
    def test_paginator_buttons_localized(
        self,
        guild_id: int,
        expected_labels: tuple[str, str, str],
    ) -> None:
        """Guild language drives prev/next/stop button labels."""

        # Load real locales (the autouse fixture replaced them with markers).
        orig_locales = dict(i18n_mod._locales)
        orig_guild_langs = dict(i18n_mod._guild_languages)
        i18n_mod._locales.clear()
        i18n_mod._guild_languages.clear()
        load_locales(Path("bot/locales"))
        set_guild_language(str(guild_id), "es" if guild_id == _GUILD_ID_ES else "en")

        try:
            page = discord.Embed(title="test")
            view = EmbedPaginator([page, page], guild_id=str(guild_id), custom_id_prefix="modlogs:")

            buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
            labels = {b.custom_id: b.label for b in buttons}

            expected_prev, expected_next, expected_stop = expected_labels
            assert labels["modlogs:prev"] is not None
            assert expected_prev in labels["modlogs:prev"]
            assert labels["modlogs:next"] is not None
            assert expected_next in labels["modlogs:next"]
            assert labels["modlogs:stop"] is not None
            assert expected_stop in labels["modlogs:stop"]
        finally:
            i18n_mod._locales.clear()
            i18n_mod._locales.update(orig_locales)
            i18n_mod._guild_languages.clear()
            i18n_mod._guild_languages.update(orig_guild_langs)
