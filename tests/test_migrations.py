"""Unit tests for SQL migrations — structural validation.

Covers:
    - Migration 008: Enable RLS on ticket_note (idempotent ALTER TABLE).
    - Migration 009: member increment RPC functions exist and are idempotent.
    - Each function has SECURITY DEFINER and SET search_path = public.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
        code_lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
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
        code_lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
        count = sum(1 for l in code_lines if "SECURITY DEFINER" in l)
        assert count == 4, f"Expected 4 SECURITY DEFINER, found {count}"

    def test_all_functions_set_search_path(self) -> None:
        """All 4 functions MUST set search_path = public."""
        sql = _read_migration("009_member_increment_rpc.sql")
        code_lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
        count = sum(1 for l in code_lines if "SET search_path = public" in l)
        assert count == 4, f"Expected 4 SET search_path, found {count}"

    def test_is_idempotent_uses_create_or_replace(self) -> None:
        """All function definitions MUST use CREATE OR REPLACE for idempotency."""
        sql = _read_migration("009_member_increment_rpc.sql")
        code_lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
        count = sum(1 for l in code_lines if "CREATE OR REPLACE FUNCTION" in l)
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
        code_lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
        conflict_count = sum(1 for l in code_lines if "ON CONFLICT" in l)
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
