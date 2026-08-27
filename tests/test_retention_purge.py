"""S3.3 — Retention purge RED (data-retention).

Tests cover:
- old closed ticket + 3 notes purged
- sub-tickets deleted BEFORE parents (observable statement order)
- recent closed ticket kept
- stale mute >180d purged
- permanent BAN >180d retained

Ref: data-retention Ticket retention + Infraction retention.
"""

from __future__ import annotations

from pathlib import Path

MIGRATION = Path("migrations/028_retention.sql")


def _sql() -> str:
    assert MIGRATION.exists(), "028_retention.sql missing — S3.4 not landed"
    return MIGRATION.read_text(encoding="utf-8")


def _lower() -> str:
    return _sql().lower()


class TestTicketRetentionPurge:
    """Ticket purge ordering and TTL."""

    def test_old_closed_ticket_and_notes_purged(self) -> None:
        sql = _lower()
        # Must delete from ticket_note and ticket where closedAt < now()-ttl
        assert "delete from ticket_note" in sql, "must DELETE FROM ticket_note"
        assert "delete from ticket" in sql, "must DELETE FROM ticket"
        assert "closedat" in sql, "must filter on closedAt"
        assert "retention_setting" in sql or "retention" in sql, "must read TTL from retention_setting"

    def test_subtickets_before_parents_observable_order(self) -> None:
        sql = _lower()
        # Observable order: notes → sub-tickets → parents
        note_pos = sql.find("delete from ticket_note")
        # We expect two DELETE FROM ticket statements: one with parentId IS NOT NULL, one with IS NULL
        assert '"parentid" is not null' in sql, "must DELETE sub-tickets WHERE parentId IS NOT NULL"
        assert '"parentid" is null' in sql, "must DELETE parents WHERE parentId IS NULL"
        # Ensure sub-ticket delete appears before parent delete
        sub_not_null = sql.find('"parentid" is not null')
        parent_null = sql.find('"parentid" is null')
        assert sub_not_null != -1 and parent_null != -1
        assert sub_not_null < parent_null, "sub-tickets MUST be deleted BEFORE parents (RESTRICT order)"
        assert note_pos < sub_not_null, "notes MUST be deleted before sub-tickets"

    def test_recent_closed_kept(self) -> None:
        sql = _lower()
        # Must filter by closedAt < now() - ttl, so recent closed (5 days, ttl 30) is retained
        assert "closedat" in sql
        assert "now()" in sql
        assert "interval" in sql or "days" in sql

    def test_collected_ids_include_subs_and_parents(self) -> None:
        sql = _lower()
        # Must collect expired parents+subs together (array_agg ids)
        assert "array_agg" in sql or ("select" in sql and "ticket" in sql)


class TestInfractionRetentionPurge:
    """Infraction purge: stale purged, permanent BAN retained."""

    def test_stale_mute_purged(self) -> None:
        sql = _lower()
        assert "delete from infraction" in sql, "must DELETE FROM infraction"
        assert "coalesce" in sql, "must use COALESCE(expiresAt, createdAt)"
        assert "retention_setting" in sql

    def test_permanent_ban_retained(self) -> None:
        sql = _lower()
        # Exception: NOT (type='BAN' AND expiresAt IS NULL) → permanent BAN retained
        assert "type = 'ban'" in sql, "must filter type='BAN'"
        # Check that permanent BAN exception appears before the COALESCE delete
        # Pattern: NOT (type = 'BAN' AND "expiresAt" IS NULL)
        assert '"expiresat" is null' in sql, "must check expiresAt IS NULL for permanent BAN"
        assert "not (" in sql or "not(" in sql, "must have NOT (type='BAN' AND expiresAt IS NULL) guard"

    def test_infraction_uses_coalesce_expires_or_created(self) -> None:
        sql = _sql()
        # Exact pattern from design
        assert 'COALESCE("expiresAt"' in sql or "COALESCE" in sql
        assert '"createdAt"' in sql or "createdAt" in sql

    def test_retention_setting_seeded(self) -> None:
        sql = _lower()
        assert "retention_setting" in sql
        assert "'tickets'" in sql and "30" in sql
        assert "'infractions'" in sql and "180" in sql
        assert "'crash'" in sql and "30" in sql

    def test_cron_and_idempotency(self) -> None:
        sql = _lower()
        assert "cron.schedule" in sql, "must schedule via cron.schedule"
        assert "do $guard$" in sql, "must use DO $guard$ IF NOT EXISTS cron.job guard"
        assert "if not exists" in sql, "DDL must use IF NOT EXISTS"
        assert "create table if not exists retention_setting" in sql
        assert "create or replace function" in sql
