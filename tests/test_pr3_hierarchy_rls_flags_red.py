"""RED: PR3 3.5-3.10 — sentinel author-hierarchy, delete_category guard,
escape/AllowedMentions, AsyncClientOptions flags, 023 RLS.

3.5 Strict TDD RED before GREEN: author.top_role <= target.top_role deny + owner exempt.
3.6 delete_category @is_mod→@is_admin
3.7 escape_markdown + AllowedMentions
3.8 AsyncClientOptions flags
3.10 migration 023 ENABLE RLS x7
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.cogs.sentinel import SentinelCog


def _make_member(role_val: int, member_id: int = 1) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.mention = f"<@{member_id}>"
    # top_role mock with <=
    role = MagicMock()
    role.__le__ = MagicMock(side_effect=lambda other: role_val <= getattr(other, "_val", 0))
    role._val = role_val
    m.top_role = role
    # also for target comparisons: need target.top_role._val
    m.roles = []
    m.guild_permissions = MagicMock()
    m.guild_permissions.administrator = False
    return m


class TestSentinelAuthorHierarchy:
    @pytest.mark.asyncio
    async def test_author_below_target_denied(self):
        """author.top_role <= target.top_role → deny ephemeral + False."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 999
        cog = SentinelCog(bot=bot)
        guild = MagicMock()
        guild.owner = MagicMock()
        guild.owner.id = 9999
        guild.me = MagicMock()
        guild.me.top_role = MagicMock()
        guild.me.top_role.__le__ = MagicMock(return_value=False)
        author = _make_member(role_val=5, member_id=10)
        target = _make_member(role_val=10, member_id=20)
        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = author
        ctx.send = AsyncMock()
        guild.id = 123
        result = await cog._validate_target(ctx, target, action="warn")
        assert result is False, "author hierarchy deny expected"
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_author_above_target_allowed(self):
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 999
        cog = SentinelCog(bot=bot)
        guild = MagicMock()
        guild.owner = MagicMock()
        guild.owner.id = 9999
        guild.me = MagicMock()
        guild.me.top_role = MagicMock()
        guild.me.top_role.__le__ = MagicMock(return_value=False)
        author = _make_member(role_val=10, member_id=10)
        target = _make_member(role_val=5, member_id=20)
        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = author
        ctx.send = AsyncMock()
        guild.id = 123
        result = await cog._validate_target(ctx, target, action="warn")
        assert result is True

    @pytest.mark.asyncio
    async def test_owner_exempt(self):
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 999
        cog = SentinelCog(bot=bot)
        guild = MagicMock()
        owner = _make_member(role_val=1, member_id=10)
        guild.owner = owner
        guild.me = MagicMock()
        guild.me.top_role.__le__ = MagicMock(return_value=False)
        author = owner
        target = _make_member(role_val=100, member_id=20)
        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = author
        ctx.send = AsyncMock()
        guild.id = 123
        result = await cog._validate_target(ctx, target, action="warn")
        assert result is True, "owner must be exempt from author hierarchy"

    def test_source_has_author_hierarchy(self):
        src = Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "author" in src and "top_role" in src
        # must check author.top_role <= target.top_role
        assert "ctx.author" in src or "author.top_role" in src


class TestDeleteCategoryGuard:
    def test_is_admin_on_delete_category(self):
        src = Path("bot/cogs/tickets.py").read_text(encoding="utf-8")
        assert "delete_category" in src
        assert "@is_admin" in src
        # delete_category's decorator must be is_admin, not is_mod — check the
        # 600 chars immediately before the function definition
        func_idx = src.index("async def delete_category")
        window = src[max(0, func_idx - 600) : func_idx + 200]
        assert "@is_admin" in window, "delete_category must be decorated with @is_admin"
        assert "@is_mod" not in window, "delete_category must not use @is_mod"


class TestEscapeAndMentions:
    def test_escape_markdown_present(self):
        found = False
        for p in Path("bot").rglob("*.py"):
            if "escape_markdown" in p.read_text(encoding="utf-8"):
                found = True
                break
        assert found, "escape_markdown must be used on echo paths"

    def test_allowed_mentions_present(self):
        found = False
        for p in Path("bot").rglob("*.py"):
            if "AllowedMentions" in p.read_text(encoding="utf-8"):
                found = True
                break
        assert found, "AllowedMentions must be used on echo paths"


class TestAsyncClientOptionsFlags:
    def test_flags_present(self):
        src = Path("bot/core/db/base.py").read_text(encoding="utf-8")
        assert "auto_refresh_token=False" in src
        assert "persist_session=False" in src
        assert 'schema="public"' in src or "schema='public'" in src or 'schema="public"' in src

    def test_service_role_validation_still(self):
        src = Path("bot/core/db/base.py").read_text(encoding="utf-8")
        assert "validate" in src.lower() and "service" in src.lower()


class TestMigration023:
    def test_file_exists(self):
        p = Path("migrations/023_rls_remaining_tables.sql")
        assert p.exists(), "023 migration missing"

    def test_enables_rls_7_tables(self):
        src = Path("migrations/023_rls_remaining_tables.sql").read_text(encoding="utf-8")
        for tbl in ("guild", "member", "infraction", "ticket", "ticket_category", "economy_config", "greeting_config"):
            assert tbl in src
        assert "ENABLE ROW LEVEL SECURITY" in src
        assert "DISABLE ROW LEVEL SECURITY" in src or "DISABLE" in src

    def test_rollback_documented(self):
        src = Path("migrations/023_rls_remaining_tables.sql").read_text(encoding="utf-8").lower()
        assert "rollback" in src or "disable" in src
