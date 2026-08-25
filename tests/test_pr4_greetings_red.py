"""PR4 4.2 — greeting.manage gate proven behaviorally (strict TDD).

The original source-grep guards (searching greetings.py for
``greeting.manage`` references and inspecting the ``_admin_guard`` window)
were replaced by behavioral tests against the real guard: an ungranted
member gets ``False`` plus a localized ephemeral error embed; admins and
matrix-granted roles pass.

Consolidation note (cycle-5 S5b/c): the grep assertions are subsumed —
if ``_admin_guard`` stops delegating to ``can("greeting.manage")``, the
guard tests below fail on real permission semantics.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.greetings import GreetingsCog


def _make_ctx(admin: bool, role_ids: tuple[int, ...], mod_role_id: str | None = None) -> MagicMock:
    """Build a mock prefix context for guard invocation."""
    member = MagicMock(spec=discord.Member)
    member.__class__ = discord.Member
    member.guild_permissions.administrator = admin
    member.id = 111
    roles = []
    for rid in role_ids:
        role = MagicMock(spec=discord.Role)
        role.id = rid
        roles.append(role)
    member.roles = roles

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = guild
    ctx.author = member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {123456789: mod_role_id} if mod_role_id else {}
    ctx.send = AsyncMock()
    return ctx


class TestAdminGuardBehavior:
    """_admin_guard delegates to can("greeting.manage") with real semantics."""

    async def test_guard_denies_ungranted_member_with_ephemeral_error(self) -> None:
        """Ungranted member → False + localized ephemeral error embed."""
        cog = GreetingsCog.__new__(GreetingsCog)  # guard touches no other state
        ctx = _make_ctx(admin=False, role_ids=())

        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await cog._admin_guard(ctx)

        assert result is False
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args.kwargs.get("ephemeral") is True
        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None

    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param("admin", id="admin-passes"),
            pytest.param("matrix", id="matrix-granted-passes"),
        ],
    )
    async def test_guard_allows_admin_and_matrix_grants(self, scenario: str) -> None:
        """Administrator and matrix-granted members pass the guard."""
        cog = GreetingsCog.__new__(GreetingsCog)
        if scenario == "admin":
            ctx = _make_ctx(admin=True, role_ids=())
            cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        else:
            ctx = _make_ctx(admin=False, role_ids=(9002,))
            cfg = MagicMock(permission_matrix={"greeting.manage": ["9002"]}, mod_role_id=None)

        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await cog._admin_guard(ctx)

        assert result is True
        ctx.send.assert_not_awaited()


class TestGreetingManageMatrix:
    """can("greeting.manage") matrix semantics — no moderation fallback."""

    async def test_mod_role_does_not_grant_greeting_manage(self) -> None:
        """modRoleId must NOT grant greeting.manage (non-moderation, no fallback)."""
        from bot.utils.checks import can

        guild_id = 123456789
        mod_role = 777
        # Member holds modRole but no matrix grant
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        role = MagicMock(spec=discord.Role)
        role.id = mod_role
        member.roles = [role]
        member.id = 111

        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id

        ctx = MagicMock(spec=commands.Context)
        ctx.guild = guild
        ctx.author = member
        ctx.bot = MagicMock()
        ctx.bot._guild_mod_role_cache = {guild_id: str(mod_role)}

        cfg = MagicMock(permission_matrix={}, mod_role_id=str(mod_role))
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await can("greeting.manage", ctx)
            assert result is False, "modRoleId must NOT grant greeting.manage"

    async def test_admin_and_matrix_grant_greeting_manage(self) -> None:
        """admin and matrix-granted role must pass greeting.manage."""
        from bot.utils.checks import can

        guild_id = 123456789
        role_c = 9002
        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id

        # admin
        admin = MagicMock(spec=discord.Member)
        admin.__class__ = discord.Member
        admin.guild_permissions.administrator = True
        admin.roles = []
        admin.id = 111
        ctx_admin = MagicMock(spec=commands.Context)
        ctx_admin.guild = guild
        ctx_admin.author = admin
        ctx_admin.bot = MagicMock()
        ctx_admin.bot._guild_mod_role_cache = {}
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(
                return_value=MagicMock(permission_matrix={}, mod_role_id=None)
            )
            assert await can("greeting.manage", ctx_admin) is True

        # matrix
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        granted = MagicMock(spec=discord.Role)
        granted.id = role_c
        member.roles = [granted]
        member.id = 222
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = guild
        ctx.author = member
        ctx.bot = MagicMock()
        ctx.bot._guild_mod_role_cache = {}
        cfg = MagicMock(permission_matrix={"greeting.manage": [str(role_c)]}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            assert await can("greeting.manage", ctx) is True
