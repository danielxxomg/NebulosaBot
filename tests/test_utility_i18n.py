"""Unit tests for bot.cogs.utility — UtilityCog with i18n migration.

Covers:
    - /avatar — localized title
    - /serverinfo — localized field names
    - /userinfo — localized field names

Uses distinct locale overrides to prove t() is called.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.utility import UtilityCog
from bot.core.i18n import load_locales, set_guild_language

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> None:
    """Load custom locale overrides."""
    from bot.core import i18n as i18n_mod

    # Save original state.
    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    es_data = {
        "common": {"footer": "NB • {timestamp}"},
        "utility": {
            "avatar": {"title": "AVATAR_{name}"},
            "serverinfo": {
                "error_title": "SRV_ERR",
                "error_description": "SRV_ERR_DESC",
                "owner_field": "OWN_FIELD",
                "members_field": "MEM_FIELD",
                "channels_field": "CH_FIELD",
                "roles_field": "RL_FIELD",
                "boosts_field": "BST_FIELD",
                "created_field": "CRT_FIELD",
            },
            "userinfo": {
                "id_field": "ID_FIELD",
                "roles_field": "ROLES_FIELD",
                "roles_none": "ROLES_NONE",
                "joined_field": "JOIN_FIELD",
                "created_field": "CRT_FIELD",
                "bot_field": "BOT_FIELD",
                "bot_yes": "BOT_YES",
                "roles_overflow": "... +{count}",
            },
        },
    }

    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "es.json").write_text(json.dumps(es_data), encoding="utf-8")

    load_locales(locale_dir)
    set_guild_language(str(_GUILD_ID), "es")

    yield

    # Restore original state so other test modules are not affected.
    i18n_mod._locales.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.clear()
    i18n_mod._guild_languages.update(orig_guild_langs)


@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> UtilityCog:
    return UtilityCog(mock_bot)


def _make_ctx(
    user_id: int = 111111111,
    guild_id: int | None = _GUILD_ID,
) -> MagicMock:
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = user_id
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = f"https://cdn.discord.com/avatars/{user_id}/default.png"
    ctx.author.default_avatar = MagicMock()
    ctx.author.default_avatar.url = "https://cdn.discord.com/embed/avatars/0.png"
    ctx.author.color = discord.Color.default()
    ctx.author.roles = []
    ctx.author.joined_at = datetime(2024, 1, 15, tzinfo=UTC)
    ctx.author.created_at = datetime(2023, 6, 1, tzinfo=UTC)
    ctx.author.mention = f"<@{user_id}>"
    ctx.author.__str__ = MagicMock(return_value="TestUser")
    ctx.author.bot = False

    if guild_id is not None:
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = guild_id
        ctx.guild.name = "Test Server"
        ctx.guild.icon = MagicMock()
        ctx.guild.icon.url = "https://cdn.discord.com/icons/test.png"
        ctx.guild.owner = ctx.author
        ctx.guild.member_count = 42
        ctx.guild.channels = [MagicMock() for _ in range(15)]
        ctx.guild.roles = [MagicMock() for _ in range(8)]
        ctx.guild.premium_subscription_count = 3
        ctx.guild.created_at = datetime(2020, 3, 10, tzinfo=UTC)
    else:
        ctx.guild = None

    return ctx


# ---------------------------------------------------------------------------
# /avatar — calls t()
# ---------------------------------------------------------------------------


class TestAvatarI18n:
    @pytest.mark.asyncio
    async def test_avatar_title_from_locale(self, cog: UtilityCog) -> None:
        """Avatar embed title MUST use t()."""
        ctx = _make_ctx()
        await cog.avatar.callback(cog, ctx, member=None)

        embed = ctx.send.call_args[1]["embed"]
        assert "AVATAR_TestUser" in embed.title


# ---------------------------------------------------------------------------
# /serverinfo — calls t()
# ---------------------------------------------------------------------------


class TestServerinfoI18n:
    @pytest.mark.asyncio
    async def test_serverinfo_dm_error_from_locale(self, cog: UtilityCog) -> None:
        """Serverinfo DM error MUST use t()."""
        ctx = _make_ctx(guild_id=None)
        await cog.serverinfo.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "SRV_ERR" in embed.title

    @pytest.mark.asyncio
    async def test_serverinfo_field_names_from_locale(self, cog: UtilityCog) -> None:
        """Serverinfo field names MUST use t()."""
        ctx = _make_ctx()

        with patch("discord.utils.format_dt", side_effect=lambda dt, *a: str(dt)):
            await cog.serverinfo.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name for f in embed.fields}
        assert "OWN_FIELD" in fields
        assert "MEM_FIELD" in fields
        assert "CH_FIELD" in fields
        assert "RL_FIELD" in fields
        assert "BST_FIELD" in fields
        assert "CRT_FIELD" in fields


# ---------------------------------------------------------------------------
# /userinfo — calls t()
# ---------------------------------------------------------------------------


class TestUserinfoI18n:
    @pytest.mark.asyncio
    async def test_userinfo_field_names_from_locale(self, cog: UtilityCog) -> None:
        """Userinfo field names MUST use t()."""
        ctx = _make_ctx()

        with patch("discord.utils.format_dt", side_effect=lambda dt, *a: str(dt)):
            await cog.userinfo.callback(cog, ctx, member=None)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name for f in embed.fields}
        assert "ID_FIELD" in fields
        assert "ROLES_FIELD" in fields
        assert "JOIN_FIELD" in fields

    @pytest.mark.asyncio
    async def test_userinfo_no_roles_from_locale(self, cog: UtilityCog) -> None:
        """Userinfo 'no roles' text MUST use t()."""
        ctx = _make_ctx()

        with patch("discord.utils.format_dt", side_effect=lambda dt, *a: str(dt)):
            await cog.userinfo.callback(cog, ctx, member=None)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert fields["ROLES_FIELD"] == "ROLES_NONE"
