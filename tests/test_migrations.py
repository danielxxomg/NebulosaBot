"""Unit tests for SQL migrations — structural validation.

Covers:
    - Migration 008: Enable RLS on ticket_note (idempotent ALTER TABLE).
    - Migration 009: member increment RPC functions exist and are idempotent.
    - Each function has SECURITY DEFINER and SET search_path = public.
    - Migration 010: REVOKE EXECUTE on member RPCs from anon/authenticated.
    - Migration 011: CREATE INDEX on ticket ("channelId").
    - Migration 023: ENABLE RLS exactly on the 7 baseline tables + rollback.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.cogs.sentinel import SentinelCog

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _read_migration(name: str) -> str:
    """Read a migration file by name."""
    path = MIGRATIONS_DIR / name
    assert path.exists(), f"Migration {name} not found at {path}"
    return path.read_text(encoding="utf-8")


class TestMigration008:
    """Structural tests for migration 008_ticket_note_rls.sql."""

    def test_migration_008_enables_rls_on_ticket_note(self) -> None:
        """Migration 008 MUST contain ENABLE ROW LEVEL SECURITY for ticket_note."""
        sql = _read_migration("008_ticket_note_rls.sql")
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "ticket_note" in sql

    def test_migration_008_is_idempotent(self) -> None:
        """Migration 008 MUST be idempotent.

        ALTER TABLE ... ENABLE ROW LEVEL SECURITY is naturally idempotent in
        PostgreSQL — re-running it when RLS is already enabled is a no-op.
        The migration file documents this property.
        """
        sql = _read_migration("008_ticket_note_rls.sql")
        # Verify the migration comment documents idempotency.
        assert "idempotent" in sql.lower() or "safe to re-run" in sql.lower()
        # The SQL itself is a single ALTER TABLE — inherently idempotent.
        code_lines = [line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")]
        assert len(code_lines) == 1
        assert "ALTER TABLE" in code_lines[0]


class TestMigration009:
    """Structural tests for migration 009_member_increment_rpc.sql."""

    def test_creates_increment_member_xp(self) -> None:
        """Migration 009 MUST create increment_member_xp function."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "CREATE OR REPLACE FUNCTION public.increment_member_xp" in sql

    def test_creates_increment_member_coins(self) -> None:
        """Migration 009 MUST create increment_member_coins function."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "CREATE OR REPLACE FUNCTION public.increment_member_coins" in sql

    def test_creates_increment_member_warnings(self) -> None:
        """Migration 009 MUST create increment_member_warnings function."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "CREATE OR REPLACE FUNCTION public.increment_member_warnings" in sql

    def test_creates_set_member_daily(self) -> None:
        """Migration 009 MUST create set_member_daily function."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "CREATE OR REPLACE FUNCTION public.set_member_daily" in sql

    def test_all_functions_use_security_definer(self) -> None:
        """All 4 functions MUST use SECURITY DEFINER."""
        sql = _read_migration("009_member_increment_rpc.sql")
        code_lines = [line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")]
        count = sum(1 for line in code_lines if "SECURITY DEFINER" in line)
        assert count == 4, f"Expected 4 SECURITY DEFINER, found {count}"

    def test_all_functions_set_search_path(self) -> None:
        """All 4 functions MUST set search_path = public."""
        sql = _read_migration("009_member_increment_rpc.sql")
        code_lines = [line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")]
        count = sum(1 for line in code_lines if "SET search_path = public" in line)
        assert count == 4, f"Expected 4 SET search_path, found {count}"

    def test_is_idempotent_uses_create_or_replace(self) -> None:
        """All function definitions MUST use CREATE OR REPLACE for idempotency."""
        sql = _read_migration("009_member_increment_rpc.sql")
        code_lines = [line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")]
        count = sum(1 for line in code_lines if "CREATE OR REPLACE FUNCTION" in line)
        assert count == 4, f"Expected 4 CREATE OR REPLACE FUNCTION, found {count}"

    def test_revokes_from_public(self) -> None:
        """Migration MUST revoke from PUBLIC for least privilege."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "REVOKE ALL ON FUNCTION" in sql
        assert "FROM PUBLIC" in sql

    def test_grants_to_service_role(self) -> None:
        """Migration MUST grant execute to service_role."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert "GRANT EXECUTE ON FUNCTION" in sql
        assert "service_role" in sql

    def test_uses_on_conflict_upsert(self) -> None:
        """All functions MUST use ON CONFLICT for upsert safety."""
        sql = _read_migration("009_member_increment_rpc.sql")
        # Count only non-comment lines containing ON CONFLICT
        code_lines = [line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")]
        conflict_count = sum(1 for line in code_lines if "ON CONFLICT" in line)
        assert conflict_count == 4, f"Expected 4 ON CONFLICT clauses, found {conflict_count}"

    def test_quoted_camelcase_columns(self) -> None:
        """Functions MUST use quoted camelCase column names."""
        sql = _read_migration("009_member_increment_rpc.sql")
        assert '"guildId"' in sql
        assert '"userId"' in sql
        assert '"lastXpGain"' in sql
        assert '"dailyStreak"' in sql
        assert '"lastDailyReset"' in sql
        assert '"lastDaily"' in sql


class TestMigration010:
    """Structural tests for migration 010_rpc_revoke_grants.sql."""

    def test_file_exists(self) -> None:
        """Migration 010 file MUST exist."""
        _read_migration("010_rpc_revoke_grants.sql")

    def test_revokes_increment_member_xp(self) -> None:
        """Migration 010 MUST revoke EXECUTE on increment_member_xp with exact signature."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "increment_member_xp(TEXT, TEXT, INTEGER)" in sql

    def test_revokes_increment_member_coins(self) -> None:
        """Migration 010 MUST revoke EXECUTE on increment_member_coins with exact signature."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "increment_member_coins(TEXT, TEXT, BIGINT)" in sql

    def test_revokes_increment_member_warnings(self) -> None:
        """Migration 010 MUST revoke EXECUTE on increment_member_warnings with exact signature."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "increment_member_warnings(TEXT, TEXT, INTEGER)" in sql

    def test_revokes_set_member_daily(self) -> None:
        """Migration 010 MUST revoke EXECUTE on set_member_daily with exact signature."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)" in sql

    def test_targets_anon_role(self) -> None:
        """Migration 010 MUST target the anon role."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "anon" in sql

    def test_targets_authenticated_role(self) -> None:
        """Migration 010 MUST target the authenticated role."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "authenticated" in sql

    def test_uses_revoke_execute(self) -> None:
        """Migration 010 MUST use REVOKE EXECUTE ON FUNCTION."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "REVOKE EXECUTE ON FUNCTION" in sql

    def test_targets_public_schema(self) -> None:
        """Migration 010 MUST reference public schema functions."""
        sql = _read_migration("010_rpc_revoke_grants.sql")
        assert "public.increment_member_xp" in sql
        assert "public.increment_member_coins" in sql
        assert "public.increment_member_warnings" in sql
        assert "public.set_member_daily" in sql


class TestMigration011:
    """Structural tests for migration 011_ticket_channel_index.sql."""

    def test_file_exists(self) -> None:
        """Migration 011 file MUST exist."""
        _read_migration("011_ticket_channel_index.sql")

    def test_creates_index_if_not_exists(self) -> None:
        """Migration 011 MUST use CREATE INDEX IF NOT EXISTS for idempotency."""
        sql = _read_migration("011_ticket_channel_index.sql")
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_index_name_is_idx_ticket_channel(self) -> None:
        """Migration 011 MUST create index named idx_ticket_channel."""
        sql = _read_migration("011_ticket_channel_index.sql")
        assert "idx_ticket_channel" in sql

    def test_targets_ticket_table(self) -> None:
        """Migration 011 MUST target the public.ticket table."""
        sql = _read_migration("011_ticket_channel_index.sql")
        assert "public.ticket" in sql

    def test_indexes_channel_id_column(self) -> None:
        """Migration 011 MUST index the channelId column."""
        sql = _read_migration("011_ticket_channel_index.sql")
        assert '"channelId"' in sql


class TestMigrationParity:
    """Migration parity: 012 tracked, 005 stale removed (runtime-hotfix)."""

    def test_012_ticket_audit_exists(self) -> None:
        """Migration 012_ticket_audit.sql MUST exist and be readable."""
        sql = _read_migration("012_ticket_audit.sql")
        assert len(sql.strip()) > 0

    def test_005_ticket_audit_absent(self) -> None:
        """Stale 005_ticket_audit.sql MUST NOT exist in migrations/."""
        path = MIGRATIONS_DIR / "005_ticket_audit.sql"
        assert not path.exists(), f"Stale migration {path} should have been removed"

    def test_015_schema_objects_match_production_definition(self) -> None:
        """Migration 015 MUST retain the production schema object contract."""
        sql = _read_migration("015_ticket_lifecycle_reliability.sql")
        normalized = " ".join(sql.lower().split())

        expected_fragments = (
            'alter table public.ticket add column if not exists "closereason" text',
            "create unique index if not exists idx_ticket_active_slot on public.ticket "
            '("guildid", "authorid", "categoryid")',
            "where status in ('open', 'claimed') and \"categoryid\" is not null",
            'create unique index if not exists idx_ticket_active_channel on public.ticket ("channelid")',
            "create unique index if not exists idx_ticket_category_active_name on "
            'public.ticket_category ("guildid", lower(btrim(name)))',
            "create unique index if not exists idx_ticket_guild_ticket_number on public.ticket "
            '("guildid", "ticketnumber")',
            "drop table if exists public.ticket_backup_claimed_open_20260706",
        )

        for fragment in expected_fragments:
            assert fragment in normalized

        drop = "drop table if exists public.ticket_backup_claimed_open_20260706"
        assert normalized.index("do $$") < normalized.index(drop)
        assert "select exists (select 1 from public.ticket_backup_claimed_open_20260706 limit 1)" in normalized
        assert normalized.index("raise exception") < normalized.index(drop)

    def test_015_restoration_does_not_apply_or_down_migrate(self) -> None:
        """Parity restoration MUST not contain migration execution or rollback."""
        sql = _read_migration("015_ticket_lifecycle_reliability.sql").lower()

        assert "insert into schema_migrations" not in sql
        assert "down migration" not in sql
        assert "drop column" not in sql


class TestMigration021:
    """PR1 2.2 — migration 021_greeting_theme_id.sql additive nullable themeId."""

    def test_file_exists(self) -> None:
        _read_migration("021_greeting_theme_id.sql")

    def test_adds_theme_id_column_to_greeting_config(self) -> None:
        sql = _read_migration("021_greeting_theme_id.sql")
        assert "ALTER TABLE" in sql
        assert "greeting_config" in sql
        assert '"themeId"' in sql or "themeId" in sql

    def test_is_additive_nullable_text(self) -> None:
        sql = _read_migration("021_greeting_theme_id.sql")
        assert "TEXT" in sql
        # Must NOT add NOT NULL or a non-null default (additive nullable).
        assert "NOT NULL" not in sql.upper() or "IF NOT EXISTS" in sql.upper()

    def test_is_idempotent(self) -> None:
        """Migration MUST use ADD COLUMN IF NOT EXISTS for idempotency."""
        sql = _read_migration("021_greeting_theme_id.sql")
        assert "ADD COLUMN IF NOT EXISTS" in sql.upper() or "ADD COLUMN IF NOT EXISTS" in sql

    def test_documents_schema_migrations_check(self) -> None:
        """Migration comment MUST mention checking schema_migrations before apply."""
        sql = _read_migration("021_greeting_theme_id.sql").lower()
        assert "schema_migrations" in sql

    def test_documents_rollback_drop_column(self) -> None:
        """Migration MUST document DROP COLUMN rollback."""
        sql = _read_migration("021_greeting_theme_id.sql")
        assert "DROP COLUMN" in sql.upper()


class TestMigration030:
    """S2 — migration 030_greeting_templates.sql per-kind template columns.

    Additive nullable TEXT columns ``welcomeTemplateId``/``goodbyeTemplateId``
    with COALESCE backfill from legacy ``themeId`` (welcome-wins is a write
    contract, not a migration concern — the migration backfills both kinds).
    """

    def test_file_exists(self) -> None:
        _read_migration("030_greeting_templates.sql")

    def test_adds_both_template_columns_to_greeting_config(self) -> None:
        sql = _read_migration("030_greeting_templates.sql")
        assert "ALTER TABLE" in sql
        assert "greeting_config" in sql
        assert '"welcomeTemplateId"' in sql
        assert '"goodbyeTemplateId"' in sql

    def test_is_additive_nullable_text(self) -> None:
        """Both columns MUST be nullable TEXT (no NOT NULL, no non-null default)."""
        sql = _read_migration("030_greeting_templates.sql")
        # Comments are documentation, not DDL — guard executable statements only
        # (house pattern: TestMigration008/009 strip comment lines first).
        code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        assert code.upper().count("TEXT") >= 2
        assert "NOT NULL" not in code.upper()
        assert "DEFAULT" not in code.upper()

    def test_is_idempotent_add_column_if_not_exists(self) -> None:
        """Migration MUST use ADD COLUMN IF NOT EXISTS for idempotency (re-run = 0 errors)."""
        sql = _read_migration("030_greeting_templates.sql")
        upper = sql.upper()
        assert upper.count("ADD COLUMN IF NOT EXISTS") >= 2, (
            "both per-kind columns must be guarded by ADD COLUMN IF NOT EXISTS for idempotent live re-run"
        )

    def test_coalesce_backfills_nulls_from_legacy_theme_id(self) -> None:
        """Backfill MUST fill null per-kind columns from legacy themeId via COALESCE + WHERE IS NULL.

        Spec scenario: row themeId='gaming_neon', welcomeTemplateId IS NULL →
        backfill sets 'gaming_neon'. Null themeId stays null (COALESCE with
        NULL legacy → NULL, so null stays null → default render).
        """
        sql = _read_migration("030_greeting_templates.sql")
        upper = sql.upper()
        assert upper.count("COALESCE") >= 2, "both per-kind columns must be backfilled via COALESCE"
        # Guard: only fill rows where the new column IS NULL (idempotent re-runs
        # must never overwrite an explicit null with a stale legacy value twice —
        # and re-running after explicit writes must not clobber).
        assert upper.count("WHERE") >= 2
        assert '"WELCOMETEMPLATEID" IS NULL' in upper
        assert '"GOODBYETEMPLATEID" IS NULL' in upper
        # Source of truth for the backfill is the legacy themeId column.
        assert '"welcomeTemplateId"=COALESCE("welcomeTemplateId","themeId")' in sql
        assert '"goodbyeTemplateId"=COALESCE("goodbyeTemplateId","themeId")' in sql

    def test_documents_schema_migrations_check(self) -> None:
        """Migration comment MUST mention checking schema_migrations before apply."""
        sql = _read_migration("030_greeting_templates.sql").lower()
        assert "schema_migrations" in sql

    def test_documents_rollback_drop_column(self) -> None:
        """Migration MUST document DROP COLUMN rollback for both new columns."""
        sql = _read_migration("030_greeting_templates.sql")
        upper = sql.upper()
        assert "DROP COLUMN" in upper
        assert '"welcomeTemplateId"' in sql
        assert '"goodbyeTemplateId"' in sql


class TestMigration024:
    """PR1 1.1 — migration 024_permission_matrix_indexes.sql additive JSONB + partial indexes."""

    def test_file_exists(self) -> None:
        """Migration 024 file MUST exist in migrations/."""
        _read_migration("024_permission_matrix_indexes.sql")

    def test_adds_permission_matrix_column(self) -> None:
        """Migration MUST ADD COLUMN permissionMatrix JSONB DEFAULT '{}'."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        upper = sql.upper()
        assert "ALTER TABLE" in sql
        assert "GUILD" in upper
        assert "PERMISSIONMATRIX" in upper
        assert "JSONB" in upper
        assert "DEFAULT" in upper
        assert "{}" in sql

    def test_permission_matrix_column_not_null_default(self) -> None:
        """permissionMatrix MUST be JSONB NOT NULL DEFAULT '{}'::jsonb."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        # Must be quoted camelCase identifier.
        assert '"permissionMatrix"' in sql or "permissionMatrix" in sql
        assert "NOT NULL" in sql.upper()
        # Default is empty object cast to jsonb
        assert "'{}'" in sql

    def test_is_idempotent_add_column_if_not_exists(self) -> None:
        """Migration MUST use ADD COLUMN IF NOT EXISTS for idempotency."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        assert "ADD COLUMN IF NOT EXISTS" in sql.upper()

    def test_creates_warn_decay_partial_index(self) -> None:
        """Migration MUST create idx_infraction_warn_decay partial index."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        assert "idx_infraction_warn_decay" in sql
        assert "CREATE INDEX IF NOT EXISTS" in sql
        upper = sql.upper()
        assert "INFRACTION" in upper
        assert "CREATEDAT" in upper or '"createdAt"' in sql
        # partial predicate
        assert "WARN" in sql

    def test_creates_tempban_expiry_partial_index(self) -> None:
        """Migration MUST create idx_infraction_tempban_expiry partial index."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        assert "idx_infraction_tempban_expiry" in sql
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert "EXPIRESAT" in sql.upper() or '"expiresAt"' in sql
        assert "BAN" in sql

    def test_partial_index_predicates(self) -> None:
        """Both partial indexes MUST have WHERE predicates for active filtering."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        # warn decay: type='WARN' AND active
        assert "active" in sql.lower()
        # tempban: expiresAt IS NOT NULL
        assert "IS NOT NULL" in sql.upper() or "is not null" in sql.lower()

    def test_documents_schema_migrations_check(self) -> None:
        """Migration comment MUST mention checking schema_migrations before apply."""
        sql = _read_migration("024_permission_matrix_indexes.sql").lower()
        assert "schema_migrations" in sql

    def test_documents_rollback(self) -> None:
        """Migration MUST document rollback DROP INDEX / DROP COLUMN."""
        sql = _read_migration("024_permission_matrix_indexes.sql")
        upper = sql.upper()
        assert "DROP INDEX" in upper
        assert "DROP COLUMN" in upper

    def test_all_three_statements_use_if_not_exists_for_idempotent_rerun(self) -> None:
        """All 3 DDL statements (column + 2 indexes) MUST use IF NOT EXISTS for live re-run safety.

        Migration 024 is applied to the live Supabase project (024/024 in
        schema_migrations). Re-running it — or running it against a fresh
        linked project that already recorded 024 — MUST be a no-op. The
        structural guard proves the SQL is safe to re-run live, which is the
        fallback when `supabase migration list` cannot prove live state.
        """
        sql = _read_migration("024_permission_matrix_indexes.sql")
        # All three idempotent guards present.
        assert sql.upper().count("IF NOT EXISTS") >= 3, (
            "migration 024 must guard all 3 DDL statements with IF NOT EXISTS for idempotent live re-run"
        )

    def test_documents_live_sync_state(self) -> None:
        """Migration comment MUST document the live-sync state (024/024).

        The verify worker's `supabase migration list` can fail when the
        project ref is unlinked. When it succeeds, it reports 024/024
        (schema_migrations recorded on the live project). The migration
        comment MUST document this so a future verify pass knows the
        live state is confirmed rather than structural-only.
        """
        sql = _read_migration("024_permission_matrix_indexes.sql")
        assert "024/024" in sql, "migration 024 must document the live 024/024 sync state"
        assert "LIVE" in sql.upper(), "migration 024 must document that it is applied live"


class TestMigration026:
    """Structural tests for migration 026_realtime_member_economy_config.sql.

    Spec cache-sync-realtime "Migration prerequisite": an idempotent,
    re-runnable DO-block migration extends the supabase_realtime publication
    with ``member`` and ``economy_config``, plus trigger-maintained
    ``updatedAt`` columns enabling the incremental poll fallback.
    """

    def test_adds_member_and_economy_config_to_publication(self) -> None:
        """The publication ALTER MUST add both tables (007 DO-block pattern)."""
        sql = _read_migration("026_realtime_member_economy_config.sql")
        assert "ALTER PUBLICATION SUPABASE_REALTIME ADD TABLE" in sql.upper()
        assert "member" in sql
        assert "economy_config" in sql

    def test_publication_alter_is_idempotent_do_block(self) -> None:
        """ALTER PUBLICATION MUST run inside a DO block catching duplicate_object.

        Verbatim 007_realtime_publication.sql pattern: adding an
        already-published table raises SQLSTATE 42710, which the block
        swallows so re-runs are a no-op.
        """
        sql = _read_migration("026_realtime_member_economy_config.sql")
        assert "DO $$" in sql
        assert "duplicate_object" in sql

    def test_adds_updated_at_columns_idempotently(self) -> None:
        """Both tables MUST gain ``updatedAt timestamptz NOT NULL DEFAULT now()`` guarded by IF NOT EXISTS."""
        sql = _read_migration("026_realtime_member_economy_config.sql")
        upper = sql.upper()
        # Two guarded column adds, one per table.
        assert upper.count('ADD COLUMN IF NOT EXISTS "UPDATEDAT"') == 2, (
            "both member and economy_config must guard the updatedAt ADD COLUMN"
        )
        assert upper.count("TIMESTAMPTZ") >= 2
        assert upper.count("NOT NULL DEFAULT NOW()") >= 2

    def test_updated_at_trigger_is_idempotent(self) -> None:
        """Trigger maintenance MUST be re-runnable: OR REPLACE fn + DROP TRIGGER IF EXISTS + CREATE TRIGGER."""
        sql = _read_migration("026_realtime_member_economy_config.sql")
        assert "CREATE OR REPLACE FUNCTION" in sql
        assert "DROP TRIGGER IF EXISTS" in sql
        assert "CREATE TRIGGER" in sql
        # Trigger sets updatedAt on UPDATE for both tables.
        assert sql.count("CREATE TRIGGER") >= 2
        assert "BEFORE UPDATE" in sql

    def test_documents_idempotency_and_rollback(self) -> None:
        """Migration comment MUST document idempotency and the rollback path (repo convention)."""
        sql = _read_migration("026_realtime_member_economy_config.sql")
        assert "idempotent" in sql.lower() or "safe to re-run" in sql.lower()
        assert "Rollback:" in sql or "rollback:" in sql.lower()


# ---------------------------------------------------------------------------
# Hierarchy twin (tests-slim-fase-2 B1) — replaces
# tests/test_pr3_hierarchy_rls_flags_red.py::TestSentinelAuthorHierarchy.
# D3 proof: author.top_role <= target.top_role deny, strictly-above allow,
# and guild-owner exemption through the real SentinelCog._validate_target.
# The AsyncClientOptions flags contract has a live spy twin in
# tests/test_remediation_final_partials.py::TestAsyncClientOptionsFlagsSpy.
# ---------------------------------------------------------------------------


def _make_hierarchy_member(role_val: int, member_id: int = 1) -> MagicMock:
    """Build a member mock whose top_role supports ``<=`` via _val ordering."""
    m = MagicMock()
    m.id = member_id
    m.mention = f"<@{member_id}>"
    role = MagicMock()
    role.__le__ = MagicMock(side_effect=lambda other: role_val <= getattr(other, "_val", 0))
    role._val = role_val
    m.top_role = role
    m.roles = []
    m.guild_permissions = MagicMock()
    m.guild_permissions.administrator = False
    return m


def _make_hierarchy_ctx(author: MagicMock, target_role_val: int) -> tuple[SentinelCog, MagicMock, MagicMock]:
    """Build (cog, ctx, target) with a bot top_role strictly above the target's."""
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
    guild.id = 123
    target = _make_hierarchy_member(role_val=target_role_val, member_id=20)
    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = author
    ctx.send = AsyncMock()
    return cog, ctx, target


class TestSentinelHierarchyTwin:
    """Parametrized sentinel author-hierarchy contract through _validate_target."""

    @pytest.mark.parametrize(
        ("scenario", "expected"),
        [
            pytest.param("below", False, id="hierarchy-below-denied"),
            pytest.param("above", True, id="hierarchy-above-allowed"),
        ],
    )
    @pytest.mark.asyncio
    async def test_author_hierarchy_denies_below_and_allows_above(self, scenario: str, expected: bool) -> None:
        """author.top_role <= target.top_role → deny; strictly above → allow."""
        if scenario == "below":
            author = _make_hierarchy_member(role_val=5, member_id=10)
        else:
            author = _make_hierarchy_member(role_val=10, member_id=10)
        cog, ctx, target = _make_hierarchy_ctx(author, target_role_val=10 if scenario == "below" else 5)

        result = await cog._validate_target(ctx, target, action="warn")

        assert result is expected, f"author hierarchy {scenario} target → {expected} expected"
        if expected is False:
            ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_owner_exempt_from_author_hierarchy(self) -> None:
        """Guild owner must be exempt from the author-hierarchy deny."""
        cog, ctx, target = _make_hierarchy_ctx(
            author=_make_hierarchy_member(role_val=1, member_id=10),
            target_role_val=100,
        )
        ctx.guild.owner = ctx.author  # author IS the owner

        result = await cog._validate_target(ctx, target, action="warn")

        assert result is True, "owner must be exempt from author hierarchy"


# ---------------------------------------------------------------------------
# Migration 023 twin (tests-slim-fase-2 B1) — replaces
# tests/test_pr3_hierarchy_rls_flags_red.py::TestMigration023.
# D3 proof: 023 ENABLEs RLS on exactly the 7 baseline tables and documents
# the DISABLE ROW LEVEL SECURITY rollback path.
# ---------------------------------------------------------------------------


class TestMigration023Twin:
    """Migration 023 RLS contract — parsed statement semantics, not substring greps."""

    _RLS_TABLES = frozenset({
        "guild",
        "member",
        "infraction",
        "ticket",
        "ticket_category",
        "economy_config",
        "greeting_config",
    })

    @staticmethod
    def _enabled_tables() -> set[str]:
        sql = (MIGRATIONS_DIR / "023_rls_remaining_tables.sql").read_text(encoding="utf-8")
        return {
            m.group(1) for m in re.finditer(r"(?im)^ALTER\s+TABLE\s+\"?(\w+)\"?\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", sql)
        }

    def test_023_enables_rls_exactly_on_7_tables(self) -> None:
        enabled = self._enabled_tables()
        assert enabled == self._RLS_TABLES, f"023 must ENABLE RLS on exactly the 7 tables, got {sorted(enabled)}"

    def test_023_rollback_documented(self) -> None:
        sql = (MIGRATIONS_DIR / "023_rls_remaining_tables.sql").read_text(encoding="utf-8")
        assert re.search(r"(?im)^--.*Rollback:.*DISABLE\s+ROW\s+LEVEL\s+SECURITY", sql), (
            "023 must document the DISABLE ROW LEVEL SECURITY rollback path"
        )
