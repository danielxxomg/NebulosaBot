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
    "configure_fields",
    "configure_fields_set",
    "subticket",
    "subticket_create",
    "reopen",
    "transfer",
    "note",
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


def _prefix_predicate(cmd: commands.Command):
    """Extract the registered prefix check predicate from a command."""
    assert len(cmd.checks) > 0, f"{cmd.name} must have registered checks"
    return cmd.checks[0]


class TestTicketsManageGateWiring:
    """Each lifecycle command's registered check enforces tickets.manage."""

    @pytest.mark.parametrize("name", _TICKETS_MANAGE_COMMANDS)
    async def test_gated_command_denies_ungranted_member(self, name: str) -> None:
        """Ungranted non-admin MUST be denied with a failure naming the key."""
        cog = _make_cog()
        ctx = _make_ctx(admin=False, role_ids=())
        pred = _prefix_predicate(getattr(cog, name))

        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            with pytest.raises(commands.CheckFailure, match=r"tickets\.manage"):
                await pred(ctx)

    @pytest.mark.parametrize("name", _TICKETS_MANAGE_COMMANDS)
    async def test_gated_command_allows_admin(self, name: str) -> None:
        """Administrator MUST pass every gated command's check."""
        cog = _make_cog()
        ctx = _make_ctx(admin=True, role_ids=())
        pred = _prefix_predicate(getattr(cog, name))

        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            assert await pred(ctx) is True


class TestDeleteCategoryAdminGate:
    """delete_category stays @is_admin — NOT tickets.manage."""

    async def test_delete_category_denies_non_admin(self) -> None:
        """Non-admin MUST be denied by the is_admin predicate."""
        cog = _make_cog()
        ctx = _make_ctx(admin=False, role_ids=())
        pred = _prefix_predicate(cog.delete_category)

        with pytest.raises(commands.MissingPermissions):
            await pred(ctx)

    async def test_delete_category_allows_admin(self) -> None:
        """Administrator passes without any matrix grant."""
        cog = _make_cog()
        ctx = _make_ctx(admin=True, role_ids=())
        pred = _prefix_predicate(cog.delete_category)

        assert await pred(ctx) is True


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
    """Gated commands must carry BOTH prefix and slash checks."""

    @pytest.mark.parametrize("name", ["ticket_panel", "create_category", "list_categories"])
    def test_command_has_prefix_and_slash_checks(self, name: str) -> None:
        """Sampled commands register checks on both invocation surfaces."""
        cog = _make_cog()
        cmd = getattr(cog, name)
        assert len(cmd.checks) > 0, f"{name} must have prefix checks"
        assert hasattr(cmd, "app_command") and cmd.app_command is not None
        assert len(cmd.app_command.checks) > 0, f"{name} must have slash checks"
