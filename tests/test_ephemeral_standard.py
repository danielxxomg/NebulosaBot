"""Unit tests for Phase 4: Ephemeral Standard + Permissions + Prefix.

Covers:
    - 4.1: _build_prefix_callable returns [config.prefix, ","]
    - 4.3: on_command_error — slash ephemeral, prefix DM, DM failure → channel
    - 4.5-4.7: ephemeral=True on admin/info slash responses
    - 4.8-4.10: @app_commands.default_permissions decorators
    - 4.11: Prefix DM fallback for admin commands

Strict TDD: RED phase — tests written BEFORE implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.bot import NebulosaBot, _build_prefix_callable
from bot.cogs.core import CoreCog
from bot.cogs.sentinel import SentinelCog
from bot.cogs.stellar import StellarCog
from bot.cogs.tickets import TicketsCog
from bot.config import BotConfig

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


def _make_message(guild_id: int | None = 123456789, prefix: str | None = "!") -> MagicMock:
    """Return a mock discord.Message for prefix tests."""
    msg = MagicMock(spec=discord.Message)
    msg.guild = MagicMock(spec=discord.Guild) if guild_id else None
    if msg.guild:
        msg.guild.id = guild_id
    return msg


# ===========================================================================
# 4.1 — Prefix callable returns [config.prefix, ","]
# ===========================================================================


class TestPrefixCallable:
    """Test that the prefix callable returns a list with config prefix + comma."""

    @pytest.mark.asyncio
    async def test_prefix_returns_list_with_config_prefix_and_comma(self) -> None:
        """get_prefix MUST return [config.prefix, ","] when config is available."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        config = MagicMock()
        config.prefix = "nb!"
        bot.guild_service.get_config = AsyncMock(return_value=config)

        get_prefix = _build_prefix_callable(bot)
        msg = _make_message(guild_id=123456789)
        result = await get_prefix(bot, msg)

        # discord.py expects a list of strings for multiple prefixes.
        assert isinstance(result, list)
        assert "nb!" in result
        assert "," in result

    @pytest.mark.asyncio
    async def test_prefix_fallback_when_no_config(self) -> None:
        """get_prefix MUST return [fallback, ","] when service is None."""
        bot = _make_bot()
        bot.guild_service = None

        get_prefix = _build_prefix_callable(bot)
        msg = _make_message(guild_id=123456789)
        result = await get_prefix(bot, msg)

        assert isinstance(result, list)
        assert "nb!" in result
        assert "," in result

    @pytest.mark.asyncio
    async def test_prefix_fallback_for_dm(self) -> None:
        """get_prefix MUST return [fallback, ","] for DMs (no guild)."""
        bot = _make_bot()
        bot.guild_service = MagicMock()

        get_prefix = _build_prefix_callable(bot)
        msg = _make_message(guild_id=None)
        result = await get_prefix(bot, msg)

        assert isinstance(result, list)
        assert "nb!" in result
        assert "," in result

    @pytest.mark.asyncio
    async def test_prefix_uses_custom_prefix(self) -> None:
        """get_prefix MUST use the guild's configured prefix, not hardcoded."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        config = MagicMock()
        config.prefix = "!"
        bot.guild_service.get_config = AsyncMock(return_value=config)

        get_prefix = _build_prefix_callable(bot)
        msg = _make_message(guild_id=123456789)
        result = await get_prefix(bot, msg)

        assert isinstance(result, list)
        assert "!" in result
        assert "," in result
        # The fallback "nb!" must NOT appear when a custom prefix is set.
        assert "nb!" not in result


# ===========================================================================
# 4.3 — on_command_error: slash ephemeral, prefix DM, DM failure → channel
# ===========================================================================


class TestOnCommandError:
    """Test error handling routes: slash → ephemeral, prefix → DM → channel."""

    @staticmethod
    def _make_prefix_ctx(guild_id: int | None = 123456789) -> MagicMock:
        """Build a mock context for prefix command error tests."""
        ctx = MagicMock()
        ctx.command = MagicMock()
        # Must NOT have on_error — hasattr check in handler
        del ctx.command.on_error
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
    async def test_prefix_error_tries_dm_first(self) -> None:
        """Prefix command error MUST try to DM the author first."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # MUST try DM first
        ctx.author.send.assert_awaited_once()
        dm_kwargs = ctx.author.send.call_args.kwargs
        embed = dm_kwargs.get("embed")
        assert embed is not None

        # MUST NOT send to channel if DM succeeded
        ctx.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prefix_error_dm_failure_falls_back_to_channel(self) -> None:
        """When DM fails, prefix error MUST send to channel with a note."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()
        ctx.author.send = AsyncMock(side_effect=discord.HTTPException(response=MagicMock(), message="Cannot send DM"))

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # DM was attempted
        ctx.author.send.assert_awaited_once()
        # Fallback to channel
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prefix_error_dm_forbidden_falls_back_to_channel(self) -> None:
        """When DM fails with Forbidden, prefix error MUST send to channel."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx()
        ctx.author.send = AsyncMock(side_effect=discord.Forbidden(response=MagicMock(), message="Cannot send DM"))

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # DM was attempted
        ctx.author.send.assert_awaited_once()
        # Fallback to channel
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prefix_error_in_dm_sends_to_channel(self) -> None:
        """Prefix error in DM (no guild) MUST send directly (no DM attempt)."""
        bot = _make_bot()
        ctx = self._make_prefix_ctx(guild_id=None)

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # In DM, ctx.send IS the DM — no author.send needed
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


class TestEphemeralAdminResponses:
    """Test that admin/info slash commands respond ephemerally."""

    @staticmethod
    def _has_ephemeral_calls(mock_send: AsyncMock) -> bool:
        """Check if any call to mock_send included ephemeral=True."""
        return any(call.kwargs.get("ephemeral") is True for call in mock_send.call_args_list)


class TestCoreCogEphemeral(TestEphemeralAdminResponses):
    """Core commands (ping, status, help) MUST be ephemeral on slash."""

    @pytest.mark.asyncio
    async def test_ping_slash_is_ephemeral(self) -> None:
        """Ping via slash MUST respond ephemerally."""
        from tests.test_core_cog import _make_ctx

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

        assert self._has_ephemeral_calls(ctx.send), "Ping MUST respond with ephemeral=True"

    @pytest.mark.asyncio
    async def test_status_slash_is_ephemeral(self) -> None:
        """Status via slash MUST respond ephemerally."""
        from tests.test_core_cog import _make_ctx

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

        assert self._has_ephemeral_calls(ctx.send), "Status MUST respond with ephemeral=True"

    @pytest.mark.asyncio
    async def test_help_slash_is_ephemeral(self) -> None:
        """Help via slash MUST respond ephemerally."""
        from tests.test_core_cog import _make_ctx

        bot = MagicMock()
        bot.latency = 0.042
        bot.get_cog = MagicMock(return_value=None)
        bot.cogs = {}

        cog = CoreCog(bot)
        ctx = _make_ctx()
        ctx.interaction = MagicMock()

        await cog.help_command.callback(cog, ctx, module="UnknownModule")

        assert self._has_ephemeral_calls(ctx.send), "Help MUST respond with ephemeral=True"


class TestTicketAdminEphemeral(TestEphemeralAdminResponses):
    """Ticket admin commands MUST be ephemeral on slash."""

    @pytest.mark.asyncio
    async def test_ticket_panel_slash_is_ephemeral(self) -> None:
        """ticket_panel via slash MUST respond ephemerally (at least the final success)."""
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

        assert self._has_ephemeral_calls(ctx.send), "ticket_panel MUST respond with ephemeral=True"

    @pytest.mark.asyncio
    async def test_create_category_slash_is_ephemeral(self) -> None:
        """create_category via slash MUST respond ephemerally."""
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

        assert self._has_ephemeral_calls(ctx.send), "create_category MUST respond with ephemeral=True"

    @pytest.mark.asyncio
    async def test_list_categories_slash_is_ephemeral(self) -> None:
        """list_categories via slash MUST respond ephemerally."""
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

        assert self._has_ephemeral_calls(ctx.send), "list_categories MUST respond with ephemeral=True"

    @pytest.mark.asyncio
    async def test_delete_category_slash_is_ephemeral(self) -> None:
        """delete_category via slash MUST respond ephemerally."""
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

        assert self._has_ephemeral_calls(ctx.send), "delete_category MUST respond with ephemeral=True"


class TestSentinelModlogsEphemeral(TestEphemeralAdminResponses):
    """modlogs MUST be ephemeral on slash."""

    @pytest.mark.asyncio
    async def test_modlogs_slash_is_ephemeral(self) -> None:
        """modlogs via slash MUST respond ephemerally."""
        from bot.core.i18n import set_guild_language

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

        assert self._has_ephemeral_calls(ctx.send), "modlogs MUST respond with ephemeral=True"


# ===========================================================================
# 4.8-4.10 — @app_commands.default_permissions decorators
# ===========================================================================


class TestDefaultPermissions:
    """Test that @app_commands.default_permissions is applied correctly."""

    @staticmethod
    def _get_default_perms(cmd) -> discord.Permissions | None:
        """Extract default_permissions from a command's app_command."""
        if hasattr(cmd, "app_command") and cmd.app_command is not None:
            return cmd.app_command.default_permissions
        return None

    # -- 4.8: ticket admin commands → administrator=True --

    def test_ticket_panel_has_admin_perms(self) -> None:
        """ticket_panel MUST have default_permissions(administrator=True)."""
        bot = MagicMock()
        cog = TicketsCog(bot)
        perms = self._get_default_perms(cog.ticket_panel)
        assert perms is not None, "ticket_panel missing default_permissions"
        assert perms.administrator is True

    def test_create_category_has_admin_perms(self) -> None:
        """create_category MUST have default_permissions(administrator=True)."""
        bot = MagicMock()
        cog = TicketsCog(bot)
        perms = self._get_default_perms(cog.create_category)
        assert perms is not None, "create_category missing default_permissions"
        assert perms.administrator is True

    def test_list_categories_has_admin_perms(self) -> None:
        """list_categories MUST have default_permissions(administrator=True)."""
        bot = MagicMock()
        cog = TicketsCog(bot)
        perms = self._get_default_perms(cog.list_categories)
        assert perms is not None, "list_categories missing default_permissions"
        assert perms.administrator is True

    def test_delete_category_has_admin_perms(self) -> None:
        """delete_category MUST have default_permissions(administrator=True)."""
        bot = MagicMock()
        cog = TicketsCog(bot)
        perms = self._get_default_perms(cog.delete_category)
        assert perms is not None, "delete_category missing default_permissions"
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


class TestEconomyCommandsPermanent:
    """Test that economy/fun commands respond permanently (NOT ephemeral)."""

    @staticmethod
    def _has_ephemeral_calls(mock_send: AsyncMock) -> bool:
        """Check if any call to mock_send included ephemeral=True."""
        return any(call.kwargs.get("ephemeral") is True for call in mock_send.call_args_list)

    @pytest.mark.asyncio
    async def test_daily_is_permanent(self) -> None:
        """daily command MUST respond permanently (NOT ephemeral)."""
        bot = MagicMock()
        bot.economy_service = MagicMock()
        bot.economy_service.claim_daily = AsyncMock(return_value=(True, 100, 1))

        cog = StellarCog(bot)
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.author = MagicMock()
        ctx.author.id = 111111111
        ctx.send = AsyncMock()
        ctx.interaction = MagicMock()  # slash invocation

        await cog.daily.callback(cog, ctx)

        assert not self._has_ephemeral_calls(ctx.send), "daily MUST respond permanently (NOT ephemeral)"

    @pytest.mark.asyncio
    async def test_coins_is_permanent(self) -> None:
        """coins command MUST respond permanently (NOT ephemeral)."""
        bot = MagicMock()
        bot.economy_service = MagicMock()
        bot.economy_service.get_balance = AsyncMock(return_value=500)

        cog = StellarCog(bot)
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.author = MagicMock()
        ctx.author.id = 111111111
        ctx.send = AsyncMock()
        ctx.interaction = MagicMock()  # slash invocation

        await cog.coins.callback(cog, ctx, member=None)

        assert not self._has_ephemeral_calls(ctx.send), "coins MUST respond permanently (NOT ephemeral)"

    @pytest.mark.asyncio
    async def test_leaderboard_is_permanent(self) -> None:
        """leaderboard command MUST respond permanently (NOT ephemeral)."""
        bot = MagicMock()
        bot.economy_service = MagicMock()
        bot.economy_service.get_leaderboard = AsyncMock(
            return_value=[{"userId": "111111111", "xp": 1000, "coins": 500}]
        )

        cog = StellarCog(bot)
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.author = MagicMock()
        ctx.author.id = 111111111
        ctx.send = AsyncMock()
        ctx.interaction = MagicMock()  # slash invocation

        await cog.leaderboard.callback(cog, ctx, lb_type="xp")

        assert not self._has_ephemeral_calls(ctx.send), "leaderboard MUST respond permanently (NOT ephemeral)"
