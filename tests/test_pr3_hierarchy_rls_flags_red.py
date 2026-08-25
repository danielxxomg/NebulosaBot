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
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.sentinel import SentinelCog
from bot.core.database import Database


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

    # Consolidation note (cycle-5 S5b/c): the former
    # ``test_source_has_author_hierarchy`` source-grep was deleted — the three
    # behavioral tests above exercise the real hierarchy path and subsume it.


# Consolidation note (cycle-5 S5b/c): the former TestDeleteCategoryGuard
# source-window grep was deleted — its assertion now lives as behavioral
# predicate tests in tests/test_pr4_tickets_red.py::TestDeleteCategoryAdminGate.


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
    async def test_connect_creates_scoped_async_client(self) -> None:
        """connect() builds the async client with schema/public + sessionless flags."""
        client = MagicMock()
        with (
            patch("bot.core.db.base.validate_service_role_key") as validate_mock,
            patch("bot.core.db.base.acreate_client", new=AsyncMock(return_value=client)) as create_mock,
            patch.object(Database, "health_check", new=AsyncMock(return_value=True)),
        ):
            db = Database(url="https://test.supabase.co", key="sb_secret_placeholder")
            await db.connect()

        # Service-role key validated before any network call (fail-closed).
        validate_mock.assert_called_once_with("sb_secret_placeholder")
        # AsyncClientOptions carry the AGENTS.md-mandated flags.
        create_mock.assert_awaited_once()
        options = create_mock.call_args.args[2]
        assert options.schema == "public"
        assert options.auto_refresh_token is False
        assert options.persist_session is False
        assert db._client is client


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
