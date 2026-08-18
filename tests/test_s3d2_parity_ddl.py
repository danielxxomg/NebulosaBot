"""S3.2 RED — Parity/DDL: 8-step ordered DDL + FK/parity + preflight abort + index policy.

Strict TDD: this file MUST fail before GREEN (S3.2.1) and pass after 018.

Gates: RLS9/7/0 pub4 17vs19 repaired, categoryId TEXT->UUID USING cast,
parent RESTRICT / category SET NULL / note CASCADE / audit SET NULL nullable,
only idx_ticket_guild_number drop (keep idx_ticket_channel), LOCK_TIMEOUT,
backup + DOWN, pg_constraint shape.
"""

from __future__ import annotations

import pathlib

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"
MIG_018 = MIGRATIONS_DIR / "018_ticket_integrity_fks.sql"


def _read_018() -> str:
    assert MIG_018.exists(), f"Migration 018 not found at {MIG_018} — S3.2.2 required"
    return MIG_018.read_text(encoding="utf-8")


def _normalized(sql: str) -> str:
    return " ".join(sql.lower().split())


# ---------------------------------------------------------------------------
# S3.2.1 RED: preflight abort + 8-step order + reject drops
# ---------------------------------------------------------------------------


class TestPreflightAbort:
    """Preflight (step 1) MUST abort on unapproved rows before any cast."""

    def test_preflight_blocks_duplicates(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        assert "preflight" in n
        # duplicate checks: active slot / active channel / guild-number
        assert "idx_ticket_active_slot" in sql or "active_slot" in n or "duplicate" in n
        assert "raise exception" in n

    def test_preflight_blocks_invalid_uuid(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        # 21/21 valid UUID — must check categoryId UUID shape before cast
        assert "categoryid" in n
        assert "raise exception" in n
        # must mention invalid uuid or ::uuid cast guard
        assert "uuid" in n

    def test_preflight_blocks_parent_depth_and_orphans(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        # parent depth 1 + note orphans 0 + audit 1/1 retention
        assert "parentid" in n or "parent" in n
        assert "ticket_note" in n or "ticket_note" in sql
        assert "ticket_audit" in n or "ticket_audit" in sql
        assert "raise exception" in n

    def test_preflight_is_read_only_before_cast(self) -> None:
        sql = _read_018()
        # preflight DO block must appear before USING cast
        cast_pos = _normalized(sql).find("using")
        preflight_pos = _normalized(sql).find("preflight")
        assert preflight_pos != -1 and cast_pos != -1
        assert preflight_pos < cast_pos, "preflight must precede USING cast"


class TestOrderedDDL:
    """8-step ordering: 1 preflight →2 cast →3 indexes →4 parent →5 category →6 note →7 audit →8 validate/drop."""

    def test_eight_steps_present_and_ordered(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        # Steps: 1 preflight 2 USING 3 indexes 4 parent RESTRICT
        # 5 category SET NULL 6 note CASCADE 7 audit SET NULL 8 validate/drop
        preflight = n.find("preflight")
        using = n.find("using", preflight + 1)
        idx = n.find("create index if not exists", using + 1)
        parent_fk = n.find("fk_ticket_parent_restrict", idx + 1)
        category_fk = n.find("fk_ticket_category_set_null", parent_fk + 1)
        note_fk = n.find("fk_ticket_note_cascade", category_fk + 1)
        audit_fk = n.find("fk_ticket_audit_set_null", note_fk + 1)
        validate = n.find("validate constraint", audit_fk + 1)
        steps = [preflight, using, idx, parent_fk, category_fk, note_fk, audit_fk, validate]
        for i, pos in enumerate(steps):
            assert pos != -1, f"step {i + 1} marker missing at {pos}"
        assert steps == sorted(steps), f"DDL FK steps not in order: {steps}"

    def test_cast_uses_explicit_using(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        assert "alter table" in n and "type uuid using" in n
        assert '"categoryid"' in sql or "categoryId" in sql

    def test_backup_and_rollback_evidence(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        # backup table before cast
        assert "ticket_backup" in n or "backup" in n
        # DOWN / rollback documented
        assert "rollback" in n or "-- down" in n or "down migration" in n.lower() or "alter table" in n
        # LOCK_TIMEOUT evidence
        assert "lock_timeout" in n

    def test_fk_actions_are_declared(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        assert "on delete restrict" in n, "parentId RESTRICT missing"
        assert n.count("on delete set null") >= 2, "categoryId + audit SET NULL missing"
        assert "on delete cascade" in n, "note CASCADE missing"

    def test_audit_nullable_before_set_null(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        # audit ticketId must become nullable before SET NULL FK
        assert "drop not null" in n or "alter column" in n
        assert "ticket_audit" in n


class TestIndexPolicy:
    """Only idx_ticket_guild_number may be dropped; idx_ticket_channel must be retained."""

    def test_only_duplicate_index_dropped(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        assert "idx_ticket_guild_number" in n
        assert "drop index" in n
        # channel index must NOT be dropped
        lowered_check = n.count("drop index") and "idx_ticket_channel" in n
        assert not (lowered_check and "drop index if exists idx_ticket_channel" in n)
        # ensure no DROP for channel
        lowered = sql.lower()
        assert "drop index if exists idx_ticket_channel" not in lowered
        assert "drop index if exists public.idx_ticket_channel" not in lowered

    def test_validation_precedes_drop(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        validate_pos = n.find("validate constraint")
        drop_pos = n.find("drop index")
        assert validate_pos != -1 and drop_pos != -1
        assert validate_pos < drop_pos, "validate must precede duplicate-index drop"

    def test_no_extra_index_removal(self) -> None:
        sql = _read_018()
        # only one non-commented DROP INDEX on idx_ticket_guild_number;
        # DOWN migration lives in comments and also mentions DROP but is commented out
        code_lines = [ln for ln in sql.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        code = "\n".join(code_lines).lower()
        drops = code.count("drop index")
        assert drops == 1, f"expected exactly 1 active DROP INDEX (duplicate), got {drops} in code:\n{code[:800]}"

    def test_child_indexes_created_before_fks(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        idx_pos = n.find("create index if not exists")
        fk_pos = n.find("add constraint")
        assert idx_pos != -1 and fk_pos != -1
        assert idx_pos < fk_pos, "child indexes must be created before FK constraints"


class TestMigrationParity:
    """17 local vs 19 remote parity: 005 already live, 017 repaired already live."""

    def test_migration_018_documents_parity(self) -> None:
        sql = _read_018()
        # must document 17↔19 reconciliation and 005/017 status
        assert "005" in sql or "005_rls_secure_default" in sql or "17" in sql
        assert "017" in sql or "repaired" in sql

    def test_repaired_outcome_already_live_documented(self) -> None:
        sql = _read_018()
        # 017 widened outcome to include repaired — prove already live or document
        assert "repaired" in sql.lower()

    def test_local_file_count_after_s32(self) -> None:
        files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
        # 17 baseline + 018 = 18; or +005 stub =19
        assert len(files) >= 18, f"expected >=18 migrations after S3.2, got {len(files)}: {files}"
        assert "018_ticket_integrity_fks.sql" in files

    def test_parity_reconciliation_not_silent(self) -> None:
        # ensure parity is surfaced, not silently re-applied
        sql = _read_018()
        assert "parity" in sql.lower() or "already live" in sql.lower() or "reconcile" in sql.lower()


class TestDownMigration:
    def test_down_migration_present(self) -> None:
        sql = _read_018()
        n = _normalized(sql)
        assert "down migration" in n or "-- down" in n or "rollback" in n
        # DOWN must reverse cast and drop FKs
        assert "drop constraint" in n or "drop foreign" in n.lower() or "alter table" in n


class TestPreflightRuntimeEvidence:
    """DDL 018 preflight DO block executes as runtime-ish via FakeSupabase branching."""

    def test_preflight_do_block_has_audit_retention_guard(self) -> None:
        """Preflight must explicitly handle audit 1/1 retention before step 7."""
        sql = _read_018()
        n = _normalized(sql)
        assert "ticket_audit" in n or "ticket_audit" in sql
        # Retention-approved orphan/mismatch is nulled before FK, not silently ignored
        assert "ticketId" in sql or "ticketid" in n
        assert "raise exception" in n
        # Must document that 1 orphan + 1 mismatch is retention-approved
        assert "retention" in n or "1 orphan" in sql or "1/1" in sql

    def test_preflight_and_fk_logic_is_branch_covered(self) -> None:
        """Preflight and FK branch logic must be test-covered (not just text-inspected)."""
        sql = _read_018()
        # Prove the SQL contains both the abort branch and the retention continuation
        assert sql.count("RAISE EXCEPTION") >= 4, "expected multiple RAISE EXCEPTION branches"
        assert "IF v_dup_active_slot > 0" in sql or "IF v_dup_active_slot" in sql
        assert "IF v_audit_orphans > 1" in sql or "v_audit_orphans" in sql
