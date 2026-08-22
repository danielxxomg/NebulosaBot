"""RED for PR4 4.1 Tickets manage → @can_check("tickets.manage") (strict TDD)."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from bot.cogs.tickets import TicketsCog


def _source() -> str:
    return pathlib.Path("bot/cogs/tickets.py").read_text(encoding="utf-8")


class TestTicketsManageGateRed:
    def test_tickets_lifecycle_gated_by_tickets_manage(self) -> None:
        """4.1: Tickets lifecycle ops must be @can_check("tickets.manage") not @is_mod()."""
        src = _source()
        # Must import can_check
        assert "can_check" in src, "tickets.py must import can_check"
        assert "tickets.manage" in src, "tickets.py must reference tickets.manage"
        # All lifecycle/admin commands except delete_category must use can_check tickets.manage
        # Count can_check tickets.manage decorators
        count = src.count('can_check("tickets.manage")') + src.count("can_check('tickets.manage')")
        # At least 10 lifecycle commands should be gated (ticket_panel, create_category, list_categories, configure_fields, etc.)
        assert count >= 10, f"Expected >=10 can_check tickets.manage, found {count}"
        # delete_category must stay @is_admin
        assert "is_admin" in src, "delete_category must preserve @is_admin"

    def test_delete_category_preserves_is_admin(self) -> None:
        """delete_category must stay @is_admin (tickets domain constraint)."""
        src = _source()
        lines = src.splitlines()
        idx = next(i for i, line in enumerate(lines) if "async def delete_category" in line)
        window = "\n".join(lines[max(0, idx - 12) : idx])
        assert "is_admin" in window, "delete_category must be @is_admin"
        assert "tickets.manage" not in window, "delete_category must not be tickets.manage"

    def test_tickets_manage_has_no_moderation_fallback(self) -> None:
        """4.1: modRoleId must NOT grant tickets.manage (non-moderation, no fallback)."""
        from bot.utils.checks import can

        async def _run() -> None:
            guild_id = 123456789
            mod_role = 777
            # Member holds modRole but no matrix grant
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
                result = await can("tickets.manage", ctx)
                assert result is False, "modRoleId must NOT grant tickets.manage"

        import asyncio

        asyncio.run(_run())

    def test_tickets_manage_admin_and_matrix_pass(self) -> None:
        """4.1: admin pass and matrix-granted role must pass tickets.manage."""
        from bot.utils.checks import can

        async def _run() -> None:
            guild_id = 123456789
            role_c = 9001
            # admin
            admin = MagicMock(spec=discord.Member)
            admin.__class__ = discord.Member
            admin.guild_permissions.administrator = True
            admin.roles = []
            admin.id = 111
            guild = MagicMock(spec=discord.Guild)
            guild.id = guild_id
            ctx_admin = MagicMock(spec=commands.Context)
            ctx_admin.guild = guild
            ctx_admin.author = admin
            ctx_admin.bot = MagicMock()
            ctx_admin.bot._guild_mod_role_cache = {}
            with patch("bot.utils.checks._get_guild_service") as gs_mock:
                gs_mock.return_value.get_config = AsyncMock(
                    return_value=MagicMock(permission_matrix={}, mod_role_id=None)
                )
                assert await can("tickets.manage", ctx_admin) is True

            # matrix-granted
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
            cfg = MagicMock(permission_matrix={"tickets.manage": [str(role_c)]}, mod_role_id=None)
            with patch("bot.utils.checks._get_guild_service") as gs_mock:
                gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
                assert await can("tickets.manage", ctx) is True

        import asyncio

        asyncio.run(_run())

    def test_tickets_cog_commands_have_checks(self) -> None:
        """All tickets.manage commands must have BOTH prefix and slash checks via can_check."""
        bot = MagicMock()
        bot.db = MagicMock()
        bot.ticket_service = MagicMock()
        bot.ticket_service.sync_channel_cache = MagicMock()
        bot.guild_service = MagicMock()
        bot.guilds = []
        cog = TicketsCog(bot=bot)
        # Sample a few commands
        for name in ["ticket_panel", "create_category", "list_categories"]:
            cmd = getattr(cog, name)
            assert len(cmd.checks) > 0, f"{name} must have prefix checks"
            assert hasattr(cmd, "app_command") and cmd.app_command is not None
            assert len(cmd.app_command.checks) > 0, f"{name} must have slash checks"
