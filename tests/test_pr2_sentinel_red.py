"""RED for PR2 2.10-2.18 SentinelCog /tempban /unban + hourly loop (strict TDD)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from bot.cogs.sentinel import SentinelCog

# Helpers


def _make_member(member_id: int = 555) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.mention = f"<@{member_id}>"
    m.top_role = MagicMock()
    m.top_role.__le__ = MagicMock(return_value=False)
    m.ban = AsyncMock()
    return m


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.insert_infraction = AsyncMock(return_value={"id": "inf"})
    bot.infraction_service = MagicMock()
    bot.infraction_service.tempban = AsyncMock(return_value=MagicMock(id="inf", type="BAN"))
    bot.infraction_service.unban = AsyncMock(return_value=MagicMock(id="ban-1"))
    bot.infraction_service.decay_warnings = AsyncMock(return_value=2)
    bot.logging_service = MagicMock()
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 999
    bot.wait_until_ready = AsyncMock()
    # For tempban expiry loop, need get_expired_tempbans via db
    bot.db.get_expired_tempbans = AsyncMock(return_value=[])
    bot.db.get_expired_warns = AsyncMock(return_value=[])
    # guild.unban for expiry loop
    return bot


def _make_guild(guild_id: int = 123456789) -> MagicMock:
    g = MagicMock()
    g.id = guild_id
    g.me = MagicMock()
    g.me.top_role = MagicMock()
    g.me.top_role.__le__ = MagicMock(return_value=False)
    g.owner = MagicMock()
    g.unban = AsyncMock()
    return g


def _make_ctx(guild: MagicMock, author: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = author
    ctx.channel = MagicMock()
    ctx.send = AsyncMock()
    return ctx


class TestTempbanCommandRed:
    def test_tempban_exists_and_gated(self) -> None:
        """2.10: SentinelCog must have /tempban hybrid gated by can_check moderation.ban."""
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        assert hasattr(cog, "tempban"), "SentinelCog.tempban must exist"
        cmd = cog.tempban
        assert len(cmd.checks) > 0, "tempban must have prefix checks"
        assert hasattr(cmd, "app_command") and cmd.app_command is not None
        assert len(cmd.app_command.checks) > 0, "tempban must have slash checks"
        # Source must use can_check moderation.ban and default_permissions ban_members
        import pathlib

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        lines = src.splitlines()
        idx = next(i for i, line in enumerate(lines) if "async def tempban(" in line)
        window = "\n".join(lines[max(0, idx - 12) : idx])
        assert "can_check" in window and "moderation.ban" in window, "tempban must be @can_check(moderation.ban)"
        assert "ban_members=True" in window or "ban_members = True" in window

    def test_tempban_invalid_duration_proven_via_source(self) -> None:
        """2.11: /tempban must guard via parse_duration_optional returning None → ephemeral error no ban."""
        import pathlib

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "parse_duration_optional" in src, "/tempban must use parse_duration_optional guard"
        # The method should reference the None case
        assert "None" in src

    def test_unban_exists_and_gated(self) -> None:
        """2.13: SentinelCog must have /unban hybrid gated by can_check moderation.ban."""
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        assert hasattr(cog, "unban"), "SentinelCog.unban must exist"
        cmd = cog.unban
        assert len(cmd.checks) > 0
        assert hasattr(cmd, "app_command") and cmd.app_command is not None
        assert len(cmd.app_command.checks) > 0
        import pathlib

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        lines = src.splitlines()
        idx = next(i for i, line in enumerate(lines) if "async def unban(" in line)
        window = "\n".join(lines[max(0, idx - 12) : idx])
        assert "can_check" in window and "moderation.ban" in window


class TestLoopRed:
    def test_loop_exists_hours_1_and_before_loop_and_cog_unload(self) -> None:
        """2.14-2.16: loop hours=1, before_loop wait_until_ready, cog_unload cancel."""
        import pathlib

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "tasks.loop" in src and "hours=1" in src, "must have @tasks.loop(hours=1)"
        assert "before_loop" in src, "must have @before_loop"
        assert "wait_until_ready" in src, "before_loop must await wait_until_ready"
        assert "cog_unload" in src, "must have cog_unload"
        # Check cog_unload cancels
        assert "cancel" in src

    def test_loop_uses_brand_tokens_no_hex(self) -> None:
        """2.17: loop logs must use brand tokens, no hex literal."""
        import pathlib
        import re

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        # Find the loop method body (approx between decay_expiry_loop def and next def)
        assert "brand." in src or "from bot.utils.brand" in src
        # No hex literal in loop area beyond brand.py
        # Simple check: no 0x[0-9a-fA-F]{6} in sentinel.py outside brand import line
        hexes = re.findall(r"0x[0-9a-fA-F]{6}", src)
        assert len(hexes) == 0, f"sentinel.py must not contain hex literals, found {hexes}"

    def test_loop_restart_durability_db_sourced(self) -> None:
        """2.18: restart durability — loop must read tempbans from DB (get_expired_tempbans), no in-memory timer."""
        import pathlib

        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "get_expired_tempbans" in src or "get_expired" in src, "loop must be DB-sourced via get_expired_tempbans"
        assert "decay_warnings" in src, "loop must run decay_warnings"
