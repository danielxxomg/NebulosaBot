"""Unit tests for bot.cogs.utility — UtilityCog hybrid commands.

Covers:
    - /avatar — self and target member, embed thumbnail
    - /serverinfo — guild info fields, DM error path
    - /userinfo — self/target, role truncation at 20

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.utility import UtilityCog
from bot.core.i18n import load_locales, set_guild_language

# ---------------------------------------------------------------------------
# i18n setup — load real locale files for all tests
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n() -> None:
    """Load real locale files so t() returns actual strings."""
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    load_locales(Path("bot/locales"))
    set_guild_language(str(_GUILD_ID), "es")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock commands.Bot — no services needed by UtilityCog."""
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> UtilityCog:
    """Return a fresh UtilityCog with mocked bot."""
    return UtilityCog(mock_bot)


def _make_ctx(
    user_id: int = 111111111,
    guild_id: int = 123456789,
    user_display_name: str = "TestUser",
    member: MagicMock | None = None,
) -> MagicMock:
    """Build a mock commands.Context for UtilityCog tests.

    Provides ``.send()``, ``.author``, ``.guild`` with the minimal
    interface used by UtilityCog commands.
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()

    if member is not None:
        ctx.author = member
    else:
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.id = user_id
        ctx.author.display_name = user_display_name
        ctx.author.display_avatar = MagicMock()
        ctx.author.display_avatar.url = f"https://cdn.discord.com/avatars/{user_id}/default.png"
        ctx.author.default_avatar = MagicMock()
        ctx.author.default_avatar.url = "https://cdn.discord.com/embed/avatars/0.png"
        ctx.author.color = discord.Color.default()
        ctx.author.roles = []
        ctx.author.joined_at = datetime(2024, 1, 15, tzinfo=UTC)
        ctx.author.created_at = datetime(2023, 6, 1, tzinfo=UTC)
        ctx.author.mention = f"<@{user_id}>"
        ctx.author.__str__ = MagicMock(return_value=user_display_name)

    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    ctx.guild.name = "Test Server"
    ctx.guild.icon = MagicMock()
    ctx.guild.icon.url = "https://cdn.discord.com/icons/123456789/server.png"
    ctx.guild.owner = ctx.author
    ctx.guild.member_count = 42
    ctx.guild.channels = [MagicMock() for _ in range(15)]
    ctx.guild.roles = [MagicMock() for _ in range(8)]
    ctx.guild.premium_subscription_count = 3
    ctx.guild.created_at = datetime(2020, 3, 10, tzinfo=UTC)

    return ctx


def _make_member(
    user_id: int = 222222222,
    display_name: str = "TargetUser",
    roles: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a mock discord.Member with avatar, roles, and timestamps."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.display_name = display_name
    member.display_avatar = MagicMock()
    member.display_avatar.url = f"https://cdn.discord.com/avatars/{user_id}/target.png"
    member.color = discord.Color.blue()
    member.mention = f"<@{user_id}>"
    member.roles = roles or []
    member.joined_at = datetime(2024, 5, 1, tzinfo=UTC)
    member.created_at = datetime(2023, 1, 1, tzinfo=UTC)
    member.bot = False
    member.__str__ = MagicMock(return_value=f"{display_name}#1234")
    return member


# ---------------------------------------------------------------------------
# /avatar — show user avatar
# ---------------------------------------------------------------------------


class TestAvatarCommand:
    """Tests for /avatar hybrid command."""

    @pytest.mark.asyncio
    async def test_avatar_self_shows_author_thumbnail(
        self,
        cog: UtilityCog,
    ) -> None:
        """Invoking /avatar without a target shows the caller's avatar."""
        ctx = _make_ctx()

        await cog.avatar.callback(cog, ctx, member=None)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.thumbnail.url == ctx.author.display_avatar.url
        assert ctx.author.display_name in embed.title

    @pytest.mark.asyncio
    async def test_avatar_target_shows_member_thumbnail(
        self,
        cog: UtilityCog,
    ) -> None:
        """Invoking /avatar @member shows the target's avatar."""
        ctx = _make_ctx()
        target = _make_member()

        await cog.avatar.callback(cog, ctx, member=target)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.thumbnail.url == target.display_avatar.url
        assert target.display_name in embed.title

    @pytest.mark.asyncio
    async def test_avatar_fallback_when_no_avatar(
        self,
        cog: UtilityCog,
    ) -> None:
        """If a member has no custom avatar, default avatar is used."""
        ctx = _make_ctx()
        ctx.author.display_avatar.url = None  # no custom avatar

        await cog.avatar.callback(cog, ctx, member=None)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        # Should fall back to default_avatar
        assert embed.thumbnail.url == ctx.author.default_avatar.url


# ---------------------------------------------------------------------------
# /serverinfo — show server information
# ---------------------------------------------------------------------------


class TestServerinfoCommand:
    """Tests for /serverinfo hybrid command."""

    @pytest.mark.asyncio
    async def test_serverinfo_shows_guild_fields(
        self,
        cog: UtilityCog,
    ) -> None:
        """In a guild context, /serverinfo shows all server fields."""
        ctx = _make_ctx()

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.serverinfo.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.title == ctx.guild.name
        assert embed.thumbnail.url == ctx.guild.icon.url

        # Build a dict of field names → values for easy assertion
        fields = {f.name: f.value for f in embed.fields}
        assert "Owner" in fields or "Propietario" in fields
        assert "Members" in fields or "Miembros" in fields
        assert str(ctx.guild.member_count) in fields.get("Members", fields.get("Miembros", ""))
        assert "Channels" in fields or "Canales" in fields
        assert str(len(ctx.guild.channels)) in fields.get("Channels", fields.get("Canales", ""))
        assert "Roles" in fields
        assert str(len(ctx.guild.roles)) in fields.get("Roles", fields.get("Roles", ""))
        assert "Boosts" in fields or "Boosts" in fields
        assert str(ctx.guild.premium_subscription_count) in fields.get("Boosts", fields.get("Boosts", ""))
        assert "Created" in fields or "Creado" in fields

    @pytest.mark.asyncio
    async def test_serverinfo_dm_shows_error_embed(
        self,
        cog: UtilityCog,
    ) -> None:
        """Invoking /serverinfo in a DM returns an error embed."""
        ctx = _make_ctx()
        ctx.guild = None  # simulate DM

        await cog.serverinfo.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    async def test_serverinfo_no_icon_handles_none_thumbnail(
        self,
        cog: UtilityCog,
    ) -> None:
        """Guilds without an icon should not break the embed."""
        ctx = _make_ctx()
        ctx.guild.icon = None

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.serverinfo.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        # thumbnail should be None (discord.Embed ignores None gracefully)
        assert embed.thumbnail.url is None


# ---------------------------------------------------------------------------
# /userinfo — show user information
# ---------------------------------------------------------------------------


class TestUserinfoCommand:
    """Tests for /userinfo hybrid command."""

    @pytest.mark.asyncio
    async def test_userinfo_self_defaults_to_author(
        self,
        cog: UtilityCog,
    ) -> None:
        """Without a target, /userinfo shows the caller's own info."""
        ctx = _make_ctx()

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.userinfo.callback(cog, ctx, member=None)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.thumbnail.url == ctx.author.display_avatar.url

        fields = {f.name: f.value for f in embed.fields}
        id_field = "ID" if "ID" in fields else "Identificador"
        assert id_field in fields
        assert str(ctx.author.id) in fields[id_field]
        roles_field = "Roles"
        assert roles_field in fields
        joined_field = "Joined" if "Joined" in fields else "Se Unió"
        assert joined_field in fields
        created_field = "Account Created" if "Account Created" in fields else "Cuenta Creada"
        assert created_field in fields

    @pytest.mark.asyncio
    async def test_userinfo_target_shows_member_info(
        self,
        cog: UtilityCog,
    ) -> None:
        """Invoking /userinfo @member shows the target's details."""
        ctx = _make_ctx()
        target = _make_member(roles=[MagicMock(spec=discord.Role) for _ in range(3)])
        # give roles names
        for i, role in enumerate(target.roles):
            role.mention = f"<@&Role{i}>"

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.userinfo.callback(cog, ctx, member=target)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.thumbnail.url == target.display_avatar.url

        fields = {f.name: f.value for f in embed.fields}
        id_field = next(f for f in fields if "ID" in f or "Identificador" in f)
        assert str(target.id) in fields[id_field]

    @pytest.mark.asyncio
    async def test_userinfo_role_truncation_at_20(
        self,
        cog: UtilityCog,
    ) -> None:
        """More than 20 roles should show first 20 + 'and N more' suffix."""
        ctx = _make_ctx()
        roles = [MagicMock(spec=discord.Role) for _ in range(25)]
        for i, role in enumerate(roles):
            role.mention = f"<@&Role{i}>"
        target = _make_member(roles=roles)

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.userinfo.callback(cog, ctx, member=target)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]

        fields = {f.name: f.value for f in embed.fields}
        roles_field = next(f for f in fields if "Role" in f)
        roles_value = fields[roles_field]
        # Should not show all 25 roles
        assert "Role24" not in roles_value
        # Should show truncation suffix (either English or Spanish)
        assert "more" in roles_value or "más" in roles_value

    @pytest.mark.asyncio
    async def test_userinfo_no_roles_shows_none(
        self,
        cog: UtilityCog,
    ) -> None:
        """A member with no extra roles should show 'None'."""
        ctx = _make_ctx()

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.userinfo.callback(cog, ctx, member=None)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]

        fields = {f.name: f.value for f in embed.fields}
        roles_field = next(f for f in fields if "Role" in f)
        assert fields[roles_field] in ("None", "Ninguno")

    @pytest.mark.asyncio
    async def test_userinfo_shows_bot_flag(
        self,
        cog: UtilityCog,
    ) -> None:
        """A bot member should have a 'Bot' field indicating it's a bot."""
        ctx = _make_ctx()
        target = _make_member()
        target.bot = True

        with patch(
            "discord.utils.format_dt",
            side_effect=lambda dt, *args: dt.strftime("%Y-%m-%d"),
        ):
            await cog.userinfo.callback(cog, ctx, member=target)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]

        fields = {f.name: f.value for f in embed.fields}
        bot_field = next(f for f in fields if "Bot" in f)
        assert "Yes" in fields[bot_field] or "Sí" in fields[bot_field]
