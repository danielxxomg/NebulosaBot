"""Unit tests for Phase 4: Ephemeral Standard + Permissions.

Covers:
    - 4.1: prefix surface inertness — moved to tests/test_bot_core_prefix.py
      (slash-only policy, cycle-5-quality-zero; the old [prefix, ","] locks
      were replaced by inertness twins there)
    - 4.3: on_command_error — channel-direct delivery, no DM attempt
    - 4.5-4.7: ephemeral=True on admin/info slash responses
    - 4.8-4.10: @app_commands.default_permissions decorators

Strict TDD: RED phase — tests written BEFORE implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.cogs.core import CoreCog
from bot.cogs.sentinel import SentinelCog
from bot.cogs.stellar import StellarCog
from bot.cogs.tickets import TicketsCog
from bot.config import BotConfig
from bot.core.i18n import set_guild_language
from tests.test_core_cog import _make_ctx

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> BotConfig:
    """Minimal BotConfig for tests."""
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )


def _make_bot(config: BotConfig | None = None) -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    return NebulosaBot(config=config or _make_config(), intents=discord.Intents.default())


def _make_slash_ctx() -> MagicMock:
    """Build a slash-invocation context (interaction present) for cog callbacks."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.author = MagicMock()
    ctx.author.id = 111111111
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()  # slash invocation
    return ctx


# ===========================================================================
# 4.3 — on_command_error: channel-direct delivery (no DM-first branch)
# ===========================================================================


class TestOnCommandError:
    """Error delivery goes directly to the channel — no DM is ever attempted.

    Adapted for slash-only policy (cycle-5-quality-zero): the former
    DM-first-with-fallback locks now assert channel-direct delivery and
    absence of author.send calls.
    """

    @staticmethod
    def _make_prefix_ctx(guild_id: int | None = 123456789) -> MagicMock:
        """Build a mock context for prefix command error tests."""
        ctx = MagicMock()
        ctx.command = MagicMock()
        # Must NOT have on_error — hasattr check in handler
        del ctx.command.on_error
        ctx.command.cog = None
        ctx.guild = MagicMock() if guild_id else None
        if ctx.guild:
            ctx.guild.id = guild_id
        ctx.author = MagicMock()
        ctx.author.id = 111111111
        ctx.author.send = AsyncMock()
        ctx.send = AsyncMock()
        ctx.interaction = None  # prefix invocation
        return ctx

    @pytest.mark.asyncio
    async def test_error_sends_channel_embed_without_dm(self) -> None:
        """Command error MUST deliver a single embed to the channel, never DM."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # MUST NOT attempt DM delivery (no DM-first branch exists).
        ctx.author.send.assert_not_awaited()

        # Single channel embed with localized title.
        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None

    @pytest.mark.asyncio
    async def test_no_dm_attempt_when_author_http_exception_prone(self) -> None:
        """Delivery is channel-direct even for authors whose DMs would fail."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()
        ctx.author.send = AsyncMock(side_effect=discord.HTTPException(response=MagicMock(), message="Cannot send DM"))

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # The handler defines no DM path — author.send stays untouched.
        ctx.author.send.assert_not_awaited()
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_dm_attempt_when_author_dms_forbidden(self) -> None:
        """Forbidden-DM authors get the channel embed like everyone else."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()
        ctx.author.send = AsyncMock(side_effect=discord.Forbidden(response=MagicMock(), message="Cannot send DM"))

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        ctx.author.send.assert_not_awaited()
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_in_dm_sends_via_context_only(self) -> None:
        """No-guild context → single direct send, still zero author.send calls."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx(guild_id=None)

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        ctx.send.assert_awaited_once()
        ctx.author.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prefix_error_ignores_command_not_found(self) -> None:
        """CommandNotFound MUST be silently ignored."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()

        error = commands.CommandNotFound("nope")
        await bot.on_command_error(ctx, error)

        ctx.author.send.assert_not_awaited()
        ctx.send.assert_not_awaited()


# ===========================================================================
# 4.5-4.7 — ephemeral=True on admin/info slash responses
# ===========================================================================


async def _send_of_ping_slash() -> AsyncMock:
    """Invoke /ping via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.latency = 0.042
    bot.cogs = {"Core": MagicMock(), "Utility": MagicMock(), "Ocio": MagicMock()}
    for cog in bot.cogs.values():
        cog.get_commands.return_value = []

    cog = CoreCog(bot)
    ctx = _make_ctx()
    # Slash: ctx.interaction is not None
    ctx.interaction = MagicMock()

    await cog.ping.callback(cog, ctx)
    return ctx.send


async def _send_of_status_slash() -> AsyncMock:
    """Invoke /status via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.latency = 0.042
    bot.db = AsyncMock()
    bot.db.health_check = AsyncMock(return_value=True)
    bot.cache = MagicMock()
    bot.cache._store = {}

    cog = CoreCog(bot)
    ctx = _make_ctx()
    ctx.guild_config = MagicMock()
    ctx.guild_config.prefix = "nb!"
    ctx.guild_config.language = "es"
    ctx.interaction = MagicMock()

    await cog.status.callback(cog, ctx)
    return ctx.send


async def _send_of_help_slash() -> AsyncMock:
    """Invoke /help via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.latency = 0.042
    bot.get_cog = MagicMock(return_value=None)
    bot.cogs = {}

    cog = CoreCog(bot)
    ctx = _make_ctx()
    ctx.interaction = MagicMock()

    await cog.help_command.callback(cog, ctx, module="UnknownModule")
    return ctx.send


async def _send_of_ticket_panel_slash() -> AsyncMock:
    """Invoke /ticket_panel via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.guild_service = MagicMock()
    bot.guild_service.update_guild_panel = AsyncMock()

    cog = TicketsCog(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()  # slash invocation
    ctx.channel = MagicMock()

    with patch("bot.cogs.tickets.deploy_ticket_panel", new_callable=AsyncMock):
        await cog.ticket_panel.callback(cog, ctx)
    return ctx.send


async def _send_of_create_category_slash() -> AsyncMock:
    """Invoke /create_category via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_ticket_categories = AsyncMock(return_value=[])
    bot.db.insert_ticket_category = AsyncMock(
        return_value={
            "id": "cat-001",
            "guildId": "123456789",
            "name": "Support",
            "emoji": None,
            "description": None,
            "position": 1,
            "active": True,
        }
    )

    cog = TicketsCog(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()

    await cog.create_category.callback(cog, ctx, name="Support")
    return ctx.send


async def _send_of_list_categories_slash() -> AsyncMock:
    """Invoke /list_categories via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_ticket_categories = AsyncMock(
        return_value=[
            {
                "id": "cat-001",
                "guildId": "123456789",
                "name": "Support",
                "emoji": None,
                "description": None,
                "position": 1,
                "active": True,
            }
        ]
    )

    cog = TicketsCog(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()

    await cog.list_categories.callback(cog, ctx)
    return ctx.send


async def _send_of_delete_category_slash() -> AsyncMock:
    """Invoke /delete_category via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_ticket_category = AsyncMock(
        return_value={
            "id": "cat-001",
            "guildId": "123456789",
            "name": "Support",
        }
    )
    bot.db.count_open_tickets_by_category = AsyncMock(return_value=0)
    bot.db.delete_ticket_category = AsyncMock()

    cog = TicketsCog(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = "123456789"
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()

    await cog.delete_category.callback(cog, ctx, category_id="cat-001")
    return ctx.send


async def _send_of_modlogs_slash() -> AsyncMock:
    """Invoke /modlogs via slash; return the ctx.send mock."""
    set_guild_language("123456789", "en")

    mock_db = AsyncMock()
    mock_db.get_infractions = AsyncMock(return_value=[])

    bot = MagicMock()
    bot.db = mock_db
    bot.infraction_service = MagicMock()
    bot.infraction_service.get_modlogs = AsyncMock(return_value=[])
    bot.logging_service = MagicMock()
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 999999999

    cog = SentinelCog(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.author = MagicMock()
    ctx.author.id = 111111111
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()

    target = MagicMock(spec=discord.Member)
    target.id = 555555555

    await cog.modlogs.callback(cog, ctx, target, type=None, after=None)
    return ctx.send


# Admin/info slash commands whose final response MUST be ephemeral.
_EPHEMERAL_SLASH_SENDERS = {
    "ping": _send_of_ping_slash,
    "status": _send_of_status_slash,
    "help": _send_of_help_slash,
    "ticket_panel": _send_of_ticket_panel_slash,
    "create_category": _send_of_create_category_slash,
    "list_categories": _send_of_list_categories_slash,
    "delete_category": _send_of_delete_category_slash,
    "modlogs": _send_of_modlogs_slash,
}


class TestSlashResponsesAreEphemeral:
    """Admin/info slash commands respond ephemerally on every send."""

    @staticmethod
    def _has_ephemeral_calls(mock_send: AsyncMock) -> bool:
        """Strict ephemeral guard — empty or no-ephemeral is NOT ephemeral."""
        if not mock_send.call_args_list:
            return False
        return any(call.kwargs.get("ephemeral") is True for call in mock_send.call_args_list)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cmd_name", list(_EPHEMERAL_SLASH_SENDERS))
    async def test_slash_response_is_ephemeral(self, cmd_name: str) -> None:
        """Command via slash MUST respond ephemerally (at least one send with ephemeral=True)."""
        send = await _EPHEMERAL_SLASH_SENDERS[cmd_name]()

        assert send.call_args_list, f"{cmd_name}: no channel send recorded — harness broken"
        assert self._has_ephemeral_calls(send), f"{cmd_name} MUST respond with ephemeral=True"


# ===========================================================================
# 4.8-4.10 — @app_commands.default_permissions decorators
# ===========================================================================

# Ticket admin commands that MUST default to administrator-only.
_TICKET_ADMIN_COMMANDS = ["ticket_panel", "create_category", "list_categories", "delete_category"]


class TestDefaultPermissions:
    """Test that @app_commands.default_permissions is applied correctly."""

    @staticmethod
    def _get_default_perms(cmd) -> discord.Permissions | None:
        # Slash-only: Command has .default_permissions directly — require explicit mapping
        if hasattr(cmd, "default_permissions"):
            val = getattr(cmd, "default_permissions", None)
            if isinstance(val, discord.Permissions):
                return val
            # None or non-Permissions is not a default-perms guard — fail lookup
            return None
        return None

    # -- 4.8: ticket admin commands → administrator=True --

    @pytest.mark.parametrize("cmd_name", _TICKET_ADMIN_COMMANDS)
    def test_ticket_admin_has_admin_perms(self, cmd_name: str) -> None:
        """Ticket admin command MUST have default_permissions(administrator=True)."""
        bot = MagicMock()
        cog = TicketsCog(bot)
        perms = self._get_default_perms(getattr(cog, cmd_name))
        assert perms is not None, f"{cmd_name} missing default_permissions"
        assert perms.administrator is True

    # -- 4.9: mod commands → moderate_members=True --

    @pytest.mark.parametrize(
        "cmd_name",
        [
            "status",
            "modlogs",
            "warn",
            "unwarn",
            "mute",
            "unmute",
            "kick",
            "lock",
            "unlock",
        ],
    )
    def test_mod_commands_have_moderate_members_perms(self, cmd_name: str) -> None:
        """Mod commands MUST have default_permissions(moderate_members=True)."""
        if cmd_name == "status":
            bot = MagicMock()
            bot.latency = 0.042
            cog = CoreCog(bot)
        else:
            bot = MagicMock()
            bot.user = MagicMock()
            cog = SentinelCog(bot)

        cmd = getattr(cog, cmd_name)
        perms = self._get_default_perms(cmd)
        assert perms is not None, f"{cmd_name} missing default_permissions"
        assert perms.moderate_members is True, f"{cmd_name} MUST have moderate_members=True, got {perms}"

    # -- 4.10: ban → ban_members=True --

    def test_ban_has_ban_members_perms(self) -> None:
        """ban MUST have default_permissions(ban_members=True)."""
        bot = MagicMock()
        bot.user = MagicMock()
        cog = SentinelCog(bot)
        perms = self._get_default_perms(cog.ban)
        assert perms is not None, "ban missing default_permissions"
        assert perms.ban_members is True


# ===========================================================================
# Economy commands — MUST be permanent (NOT ephemeral)
# ===========================================================================


async def _send_of_daily_permanent() -> AsyncMock:
    """Invoke /daily via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.economy_service = MagicMock()
    bot.economy_service.claim_daily = AsyncMock(return_value=(True, 100, 1))

    cog = StellarCog(bot)
    ctx = _make_slash_ctx()

    await cog.daily.callback(cog, ctx)
    return ctx.send


async def _send_of_coins_permanent() -> AsyncMock:
    """Invoke /coins via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.economy_service = MagicMock()
    bot.economy_service.get_balance = AsyncMock(return_value=500)

    cog = StellarCog(bot)
    ctx = _make_slash_ctx()

    await cog.coins.callback(cog, ctx, member=None)
    return ctx.send


async def _send_of_leaderboard_permanent() -> AsyncMock:
    """Invoke /leaderboard via slash; return the ctx.send mock."""
    bot = MagicMock()
    bot.economy_service = MagicMock()
    bot.economy_service.get_leaderboard = AsyncMock(return_value=[{"userId": "111111111", "xp": 1000, "coins": 500}])

    cog = StellarCog(bot)
    ctx = _make_slash_ctx()

    await cog.leaderboard.callback(cog, ctx, lb_type="xp")
    return ctx.send


# Economy/fun slash commands whose responses MUST stay permanent.
_PERMANENT_SLASH_SENDERS = {
    "daily": _send_of_daily_permanent,
    "coins": _send_of_coins_permanent,
    "leaderboard": _send_of_leaderboard_permanent,
}


class TestEconomyCommandsPermanent:
    """Economy/fun commands respond permanently (NOT ephemeral)."""

    @staticmethod
    def _has_ephemeral_calls(mock_send: AsyncMock) -> bool:
        """Strict ephemeral guard — empty or no-ephemeral is NOT ephemeral."""
        if not mock_send.call_args_list:
            return False
        return any(call.kwargs.get("ephemeral") is True for call in mock_send.call_args_list)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cmd_name", list(_PERMANENT_SLASH_SENDERS))
    async def test_response_is_permanent(self, cmd_name: str) -> None:
        """Command MUST respond permanently — zero ephemeral sends."""
        send = await _PERMANENT_SLASH_SENDERS[cmd_name]()

        assert send.call_args_list, f"{cmd_name}: no channel send recorded — harness broken"
        assert not self._has_ephemeral_calls(send), f"{cmd_name} MUST respond permanently (NOT ephemeral)"
