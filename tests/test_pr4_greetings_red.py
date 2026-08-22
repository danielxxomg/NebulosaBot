"""RED for PR4 4.2 Greetings manage → _admin_guard / can_check greeting.manage (strict TDD)."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands


def _source() -> str:
    return pathlib.Path("bot/cogs/greetings.py").read_text(encoding="utf-8")


class TestGreetingsManageGateRed:
    def test_greetings_uses_greeting_manage(self) -> None:
        """4.2: greetings must be gated by greeting.manage (can_check or can via _admin_guard)."""
        src = _source()
        assert "greeting.manage" in src, "greetings.py must reference greeting.manage"
        # Must import can or can_check
        assert "can" in src, "greetings.py must import can/can_check"

    def test_admin_guard_uses_matrix_not_just_administrator(self) -> None:
        """_admin_guard must delegate to can("greeting.manage") not just administrator check."""
        src = _source()
        # Find _admin_guard body
        lines = src.splitlines()
        idx = next(i for i, line in enumerate(lines) if "async def _admin_guard" in line)
        window = "\n".join(lines[idx : idx + 20])
        # Old code checked guild_permissions.administrator directly; new must use can
        assert (
            'can("greeting.manage"' in window
            or "can('greeting.manage'" in window
            or 'can_check("greeting.manage"' in window
            or "greeting.manage" in window
        ), "_admin_guard must use greeting.manage"
        # Should not be bare administrator-only check without can
        # If still has administrator check without can, it's not migrated
        has_can = "can(" in window or "can_check" in window
        assert has_can, "_admin_guard must use can() for greeting.manage"

    @pytest.mark.asyncio
    async def test_greeting_manage_mod_role_denied(self) -> None:
        """modRoleId must NOT grant greeting.manage (non-moderation, no fallback)."""
        from bot.utils.checks import can

        guild_id = 123456789
        mod_role = 777
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        r = MagicMock(spec=discord.Role)
        r.id = mod_role
        member.roles = [r]
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

    @pytest.mark.asyncio
    async def test_greeting_manage_admin_and_matrix_pass(self) -> None:
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
            gs_mock.return_value.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
            assert await can("greeting.manage", ctx_admin) is True

        # matrix
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        r = MagicMock(spec=discord.Role)
        r.id = role_c
        member.roles = [r]
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
