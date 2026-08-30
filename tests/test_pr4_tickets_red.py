"""PR4 4.1 — tickets.manage gate wiring proven behaviorally (strict TDD).

The original source-grep guards (counting ``@can_check("tickets.manage")``
occurrences in tickets.py) were replaced by per-command behavioral tests:
each gated command's registered prefix predicate must deny an ungranted
member with a CheckFailure naming ``tickets.manage`` and allow an admin.

Consolidation note (cycle-5 S5b/c): the grep assertions are subsumed by
these wiring tests — a removed decorator fails the matching parametrized
case, so drift is still caught, now against runtime behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.tickets import TicketsCog
from bot.utils.checks import can

# Every command wired with @can_check("tickets.manage") in bot/cogs/tickets.py.
_TICKETS_MANAGE_COMMANDS = [
    "ticket_panel",
    "create_category",
    "list_categories",
    "configure_fields_set",
    "subticket_create",
    "reopen",
    "transfer",
    "note_add",
    "note_list",
    "note_delete",
    "sweep_integrity",
    "repair_ticket",
]


def _make_cog() -> TicketsCog:
    """Build a TicketsCog on a minimal mock bot."""
    bot = MagicMock()
    bot.db = MagicMock()
    bot.ticket_service = MagicMock()
    bot.ticket_service.sync_channel_cache = MagicMock()
    bot.guild_service = MagicMock()
    bot.guilds = []
    return TicketsCog(bot=bot)


def _make_ctx(admin: bool, role_ids: tuple[int, ...]) -> MagicMock:
    """Build a mock prefix context for predicate invocation."""
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
    ctx.bot._guild_mod_role_cache = {}
    return ctx


def _prefix_predicate(cmd) -> Any:
    """Extract the registered check predicate from a (now pure slash) command."""
    # Slash-only: app_commands.Command exposes .checks
    if hasattr(cmd, "checks") and cmd.checks:
        return cmd.checks[0]
    # Group fallback
    if hasattr(cmd, "callback") and getattr(cmd.callback, "__discord_app_commands_checks__", None):
        return cmd.callback.__discord_app_commands_checks__[0]
    msg = f"{getattr(cmd, 'name', cmd)} must have registered checks"  # noqa: EM102 -- assign before raise
    raise AssertionError(msg)


class TestTicketsManageGateWiring:
    """Each lifecycle command's registered check enforces tickets.manage (slash-only)."""

    @pytest.mark.parametrize("name", _TICKETS_MANAGE_COMMANDS)
    async def test_gated_command_denies_ungranted_member(self, name: str) -> None:
        cog = _make_cog()
        member = _make_ctx(admin=False, role_ids=()).author
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = guild
        inter.user = member
        pred = _prefix_predicate(getattr(cog, name))  # test harness helper — intentional Any
        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            with pytest.raises(discord.app_commands.CheckFailure, match=r"tickets\.manage"):
                await pred(inter)

    @pytest.mark.parametrize("name", _TICKETS_MANAGE_COMMANDS)
    async def test_gated_command_allows_admin(self, name: str) -> None:
        cog = _make_cog()
        member = _make_ctx(admin=True, role_ids=()).author
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = guild
        inter.user = member
        pred = _prefix_predicate(getattr(cog, name))  # test harness helper — intentional Any
        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            assert await pred(inter) is True


class TestDeleteCategoryAdminGate:
    """delete_category stays @is_admin — NOT tickets.manage."""

    async def test_delete_category_denies_non_admin(self) -> None:
        """Non-admin MUST be denied by the is_admin predicate."""
        cog = _make_cog()
        member = _make_ctx(admin=False, role_ids=()).author
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = guild
        inter.user = member
        pred = _prefix_predicate(cog.delete_category)
        with pytest.raises(discord.app_commands.MissingPermissions):
            await pred(inter)

    async def test_delete_category_allows_admin(self) -> None:
        """Administrator passes without any matrix grant."""
        cog = _make_cog()
        member = _make_ctx(admin=True, role_ids=()).author
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = guild
        inter.user = member
        pred = _prefix_predicate(cog.delete_category)
        assert await pred(inter) is True


class TestTicketsManageMatrix:
    """can("tickets.manage") matrix semantics — no moderation fallback."""

    async def test_mod_role_does_not_grant_tickets_manage(self) -> None:
        """modRoleId must NOT grant tickets.manage (non-moderation, no fallback)."""
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
            result = await can("tickets.manage", ctx)
            assert result is False, "modRoleId must NOT grant tickets.manage"

    async def test_admin_and_matrix_grant_tickets_manage(self) -> None:
        """admin pass and matrix-granted role must pass tickets.manage."""
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
            gs_mock.return_value.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
            assert await can("tickets.manage", ctx_admin) is True

        # matrix-granted
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
        cfg = MagicMock(permission_matrix={"tickets.manage": [str(role_c)]}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            assert await can("tickets.manage", ctx) is True


class TestTicketsCogCommandCheckRegistration:
    """Gated commands must carry slash checks (S6A slash-only)."""

    @pytest.mark.parametrize("name", ["ticket_panel", "create_category", "list_categories"])
    def test_command_has_prefix_and_slash_checks(self, name: str) -> None:
        """Sampled commands register slash checks."""
        cog = _make_cog()
        cmd = getattr(cog, name)
        assert hasattr(cmd, "checks") and len(cmd.checks) > 0, f"{name} must have slash checks"
        assert not hasattr(cmd, "app_command"), f"{name} must be pure slash, not hybrid"
