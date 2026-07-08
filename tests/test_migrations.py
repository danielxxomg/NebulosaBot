"""Unit tests for SQL migration artifacts.

Covers the ``initial-schema`` delta spec scenarios for Migration 003
(tickets-subsidiados):

    - Migration 003 file exists and is additive/idempotent
    - ``ticket.parentId`` added as a nullable UUID (existing rows stay null)
    - ``ticket_note`` table created with the required columns and types
    - The three lookup indexes exist (parent, note-by-ticket, note composite)
    - No backfill/mutation of existing ticket rows (additive only)

The migration artifact is validated by parsing its SQL text. A live apply
against Supabase is performed separately in the SDD verify step — these
tests guard the artifact itself so a malformed or non-idempotent migration
is caught before it reaches the database.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_003 = MIGRATIONS_DIR / "003_subtickets_notes.sql"


def _migration_003_text() -> str:
    """Return Migration 003 SQL text, failing cleanly if the file is absent."""
    assert MIGRATION_003.is_file(), f"Migration 003 not found at {MIGRATION_003}"
    return MIGRATION_003.read_text()


def _ticket_note_block(sql: str) -> str:
    """Extract the ``CREATE TABLE ... ticket_note (...)`` body."""
    match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+ticket_note\s*\((.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, "CREATE TABLE ticket_note block not found in migration"
    return match.group(1)


# ---------------------------------------------------------------------------
# Migration 003 — existence + parentId column (existing data unaffected)
# ---------------------------------------------------------------------------


def test_migration_003_file_exists() -> None:
    """Migration 003 artifact MUST exist at migrations/003_subtickets_notes.sql."""
    assert MIGRATION_003.is_file(), f"Migration file missing: {MIGRATION_003}"


def test_migration_003_adds_nullable_parent_id_column() -> None:
    """parentId MUST be added as a nullable UUID so existing tickets stay null.

    Spec: 'all existing tickets have parentId=null' and 'parentId defaults to
    null'. A NOT NULL constraint or a non-null DEFAULT on the ADD COLUMN would
    break existing rows — this test rejects both.
    """
    sql = _migration_003_text()

    alter_match = re.search(
        r'ALTER\s+TABLE\s+ticket\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+"parentId"\s+UUID',
        sql,
        re.IGNORECASE,
    )
    assert alter_match is not None, 'ALTER TABLE ticket ADD COLUMN "parentId" UUID missing'

    # Grab the full ALTER statement (up to its semicolon) so the NOT NULL /
    # DEFAULT check is robust against multi-line formatting.
    alter_statement = sql[alter_match.start() :].split(";", 1)[0]
    assert "NOT NULL" not in alter_statement.upper(), (
        "parentId ADD COLUMN MUST NOT be NOT NULL — existing rows would break"
    )
    assert "DEFAULT" not in alter_statement.upper(), (
        "parentId ADD COLUMN MUST NOT carry a DEFAULT — existing rows must stay null"
    )


# ---------------------------------------------------------------------------
# ticket_note table — required columns and types
# ---------------------------------------------------------------------------


def test_migration_003_creates_ticket_note_table() -> None:
    """ticket_note table MUST be created with IF NOT EXISTS."""
    sql = _migration_003_text()
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+ticket_note\s*\(",
        sql,
        re.IGNORECASE,
    ), "CREATE TABLE IF NOT EXISTS ticket_note missing"


def test_ticket_note_id_is_uuid_primary_key_with_default() -> None:
    """ticket_note.id MUST be UUID PRIMARY KEY defaulting to gen_random_uuid()."""
    block = _ticket_note_block(_migration_003_text())
    assert re.search(
        r"\bid\s+UUID\s+PRIMARY\s+KEY\s+DEFAULT\s+gen_random_uuid\s*\(\s*\)",
        block,
        re.IGNORECASE,
    ), "ticket_note.id MUST be UUID PRIMARY KEY DEFAULT gen_random_uuid()"


def test_ticket_note_ticket_id_is_uuid_not_null() -> None:
    """ticket_note.ticketId MUST be UUID NOT NULL (references ticket)."""
    block = _ticket_note_block(_migration_003_text())
    assert re.search(
        r'"ticketId"\s+UUID\s+NOT\s+NULL',
        block,
        re.IGNORECASE,
    ), 'ticket_note."ticketId" MUST be UUID NOT NULL'


def test_ticket_note_author_id_is_text_not_null() -> None:
    """ticket_note.authorId MUST be TEXT NOT NULL."""
    block = _ticket_note_block(_migration_003_text())
    assert re.search(
        r'"authorId"\s+TEXT\s+NOT\s+NULL',
        block,
        re.IGNORECASE,
    ), 'ticket_note."authorId" MUST be TEXT NOT NULL'


def test_ticket_note_content_is_text_not_null() -> None:
    """ticket_note.content MUST be TEXT NOT NULL."""
    block = _ticket_note_block(_migration_003_text())
    assert re.search(
        r"\bcontent\s+TEXT\s+NOT\s+NULL",
        block,
        re.IGNORECASE,
    ), "ticket_note.content MUST be TEXT NOT NULL"


def test_ticket_note_created_at_is_timestamptz_defaulting_now() -> None:
    """ticket_note.createdAt MUST be TIMESTAMPTZ NOT NULL DEFAULT NOW()."""
    block = _ticket_note_block(_migration_003_text())
    assert re.search(
        r'"createdAt"\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+NOW\s*\(\s*\)',
        block,
        re.IGNORECASE,
    ), 'ticket_note."createdAt" MUST be TIMESTAMPTZ NOT NULL DEFAULT NOW()'


# ---------------------------------------------------------------------------
# Indexes — three lookup indexes from design.md
# ---------------------------------------------------------------------------


def test_migration_003_creates_parent_id_index() -> None:
    """Index idx_ticket_parent on ticket(parentId) MUST exist (IF NOT EXISTS)."""
    sql = _migration_003_text()
    assert re.search(
        r'CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_parent\s+ON\s+ticket\s*\(\s*"parentId"\s*\)',
        sql,
        re.IGNORECASE,
    ), 'CREATE INDEX idx_ticket_parent ON ticket ("parentId") missing'


def test_migration_003_creates_ticket_note_ticket_index() -> None:
    """Index idx_ticket_note_ticket on ticket_note(ticketId) MUST exist."""
    sql = _migration_003_text()
    assert re.search(
        r'CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_note_ticket\s+ON\s+ticket_note\s*\(\s*"ticketId"\s*\)',
        sql,
        re.IGNORECASE,
    ), 'CREATE INDEX idx_ticket_note_ticket ON ticket_note ("ticketId") missing'


def test_migration_003_creates_ticket_note_created_composite_index() -> None:
    """Composite index idx_ticket_note_created on (ticketId, createdAt DESC) MUST exist."""
    sql = _migration_003_text()
    assert re.search(
        r'CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_note_created\s+ON\s+ticket_note\s*\(\s*"ticketId"\s*,\s*"createdAt"\s+DESC\s*\)',
        sql,
        re.IGNORECASE,
    ), 'CREATE INDEX idx_ticket_note_created ON ticket_note ("ticketId", "createdAt" DESC) missing'


# ---------------------------------------------------------------------------
# Idempotency + additive-only (no mutation of existing rows)
# ---------------------------------------------------------------------------


def test_migration_003_is_idempotent() -> None:
    """Every CREATE/ALTER in Migration 003 MUST use IF NOT EXISTS (re-runnable)."""
    sql = _migration_003_text()

    create_tables = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+", sql, re.IGNORECASE)
    for stmt in create_tables:
        assert "IF NOT EXISTS" in stmt.upper(), f"Non-idempotent CREATE TABLE: {stmt!r} — MUST use IF NOT EXISTS"

    create_indexes = re.findall(r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+", sql, re.IGNORECASE)
    for stmt in create_indexes:
        assert "IF NOT EXISTS" in stmt.upper(), f"Non-idempotent CREATE INDEX: {stmt!r} — MUST use IF NOT EXISTS"

    alter_columns = re.findall(r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?", sql, re.IGNORECASE)
    assert alter_columns, "Expected at least one ADD COLUMN statement"
    for stmt in alter_columns:
        assert "IF NOT EXISTS" in stmt.upper(), "Non-idempotent ADD COLUMN — MUST use IF NOT EXISTS"


def test_migration_003_does_not_mutate_existing_tickets() -> None:
    """Migration 003 MUST be additive only — no UPDATE/DELETE/INSERT on existing rows."""
    sql = _mutation_free_sql(_migration_003_text())
    # After stripping comments, no DML that would touch existing data.
    assert not re.search(r"\bUPDATE\s+ticket\b", sql, re.IGNORECASE), (
        "Migration MUST NOT UPDATE ticket — existing rows must be untouched"
    )
    assert not re.search(r"\bDELETE\s+FROM\s+ticket\b", sql, re.IGNORECASE), (
        "Migration MUST NOT DELETE from ticket — existing rows must be untouched"
    )
    assert not re.search(r"\bINSERT\s+INTO\s+ticket\b", sql, re.IGNORECASE), (
        "Migration MUST NOT INSERT into ticket — no backfill of existing rows"
    )


def _mutation_free_sql(sql: str) -> str:
    """Strip SQL line comments (--) and block comments (/* */) before DML checks."""
    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    no_line = "\n".join(line.split("--", 1)[0] for line in no_block.splitlines())
    return no_line


# ===========================================================================
# Migration 005 — ticket_audit table + transfer normalization + note dedup index
# (B5 ticket-invariant-layer)
# ===========================================================================

MIGRATION_005 = MIGRATIONS_DIR / "005_ticket_audit.sql"


def _migration_005_text() -> str:
    """Return Migration 005 SQL text, failing cleanly if the file is absent."""
    assert MIGRATION_005.is_file(), f"Migration 005 not found at {MIGRATION_005}"
    return MIGRATION_005.read_text()


def _ticket_audit_block(sql: str) -> str:
    """Extract the ``CREATE TABLE ... ticket_audit (...)`` body."""
    match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+ticket_audit\s*\((.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, "CREATE TABLE ticket_audit block not found in migration"
    return match.group(1)


# --- existence -----------------------------------------------------------


def test_migration_005_file_exists() -> None:
    """Migration 005 artifact MUST exist at migrations/005_ticket_audit.sql."""
    assert MIGRATION_005.is_file(), f"Migration file missing: {MIGRATION_005}"


# --- ticket_audit table columns ------------------------------------------


def test_migration_005_creates_ticket_audit_table() -> None:
    """ticket_audit table MUST be created with IF NOT EXISTS."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+ticket_audit\s*\(",
        sql,
        re.IGNORECASE,
    ), "CREATE TABLE IF NOT EXISTS ticket_audit missing"


def test_ticket_audit_id_is_uuid_primary_key_with_default() -> None:
    """ticket_audit.id MUST be UUID PRIMARY KEY defaulting to gen_random_uuid()."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r"\bid\s+UUID\s+PRIMARY\s+KEY\s+DEFAULT\s+gen_random_uuid\s*\(\s*\)",
        block,
        re.IGNORECASE,
    ), "ticket_audit.id MUST be UUID PRIMARY KEY DEFAULT gen_random_uuid()"


def test_ticket_audit_guild_id_is_text_not_null() -> None:
    """ticket_audit.guildId MUST be TEXT NOT NULL (guild scope key)."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r'"guildId"\s+TEXT\s+NOT\s+NULL',
        block,
        re.IGNORECASE,
    ), 'ticket_audit."guildId" MUST be TEXT NOT NULL'


def test_ticket_audit_ticket_id_is_uuid_not_null() -> None:
    """ticket_audit.ticketId MUST be UUID NOT NULL."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r'"ticketId"\s+UUID\s+NOT\s+NULL',
        block,
        re.IGNORECASE,
    ), 'ticket_audit."ticketId" MUST be UUID NOT NULL'


def test_ticket_audit_action_is_text_not_null() -> None:
    """ticket_audit.action MUST be TEXT NOT NULL."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r"\baction\s+TEXT\s+NOT\s+NULL",
        block,
        re.IGNORECASE,
    ), "ticket_audit.action MUST be TEXT NOT NULL"


def test_ticket_audit_actor_id_is_nullable_text() -> None:
    """ticket_audit.actorId MUST be TEXT (nullable — system actions have no actor)."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r'"actorId"\s+TEXT(?:\s|,|\))',
        block,
        re.IGNORECASE,
    ), 'ticket_audit."actorId" MUST be TEXT (nullable)'
    # Explicitly NOT NULL would break system-originated rows.
    actor_stmt = re.search(
        r'"actorId"\s+TEXT\s*(?:NOT\s+NULL)?',
        block,
        re.IGNORECASE,
    )
    assert actor_stmt is not None
    assert "NOT NULL" not in actor_stmt.group(0).upper(), (
        "ticket_audit.actorId MUST NOT be NOT NULL — system actions have no actor"
    )


def test_ticket_audit_outcome_is_text_not_null_with_check() -> None:
    """ticket_audit.outcome MUST be TEXT NOT NULL CHECK IN success|denied|error."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r"\boutcome\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*outcome\s+IN\s*\("
        r"\s*'success'\s*,\s*'denied'\s*,\s*'error'\s*\)\s*\)",
        block,
        re.IGNORECASE,
    ), "ticket_audit.outcome MUST be TEXT NOT NULL CHECK (outcome IN ('success','denied','error'))"


def test_ticket_audit_reason_is_nullable_text() -> None:
    """ticket_audit.reason MUST be TEXT (nullable)."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r"\breason\s+TEXT(?:\s|,|\))",
        block,
        re.IGNORECASE,
    ), "ticket_audit.reason MUST be TEXT (nullable)"


def test_ticket_audit_created_at_is_timestamptz_default_now() -> None:
    """ticket_audit.createdAt MUST be TIMESTAMPTZ NOT NULL DEFAULT now()."""
    block = _ticket_audit_block(_migration_005_text())
    assert re.search(
        r'"createdAt"\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+now\s*\(\s*\)',
        block,
        re.IGNORECASE,
    ), 'ticket_audit."createdAt" MUST be TIMESTAMPTZ NOT NULL DEFAULT now()'


# --- indexes -------------------------------------------------------------


def test_migration_005_creates_ticket_history_index() -> None:
    """idx_ticket_audit_ticket_history on (guildId, ticketId, createdAt DESC) MUST exist."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_audit_ticket_history"
        r'\s+ON\s+ticket_audit\s*\(\s*"guildId"\s*,\s*"ticketId"\s*,\s*"createdAt"\s+DESC\s*\)',
        sql,
        re.IGNORECASE,
    ), "idx_ticket_audit_ticket_history missing"


def test_migration_005_creates_guild_created_index() -> None:
    """idx_ticket_audit_guild_created on (guildId, createdAt DESC) MUST exist."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_audit_guild_created"
        r'\s+ON\s+ticket_audit\s*\(\s*"guildId"\s*,\s*"createdAt"\s+DESC\s*\)',
        sql,
        re.IGNORECASE,
    ), "idx_ticket_audit_guild_created missing"


def test_migration_005_creates_guild_action_index() -> None:
    """idx_ticket_audit_guild_action on (guildId, action) MUST exist."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_audit_guild_action"
        r'\s+ON\s+ticket_audit\s*\(\s*"guildId"\s*,\s*action\s*\)',
        sql,
        re.IGNORECASE,
    ), "idx_ticket_audit_guild_action missing"


def test_migration_005_creates_note_author_created_index() -> None:
    """idx_ticket_note_ticket_author_created on ticket_note (ticketId, authorId, createdAt DESC) MUST exist."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_ticket_note_ticket_author_created"
        r'\s+ON\s+ticket_note\s*\(\s*"ticketId"\s*,\s*"authorId"\s*,\s*"createdAt"\s+DESC\s*\)',
        sql,
        re.IGNORECASE,
    ), "idx_ticket_note_ticket_author_created missing"


# --- RLS ------------------------------------------------------------------


def test_migration_005_enables_rls_on_ticket_audit() -> None:
    """ALTER TABLE ticket_audit ENABLE ROW LEVEL SECURITY MUST be present."""
    sql = _migration_005_text()
    assert re.search(
        r"ALTER\s+TABLE\s+ticket_audit\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
        re.IGNORECASE,
    ), "ENABLE ROW LEVEL SECURITY on ticket_audit missing"


# --- transfer normalization (backup + UPDATE) -----------------------------


def test_migration_005_creates_idempotent_backup_table() -> None:
    """Backup of legacy claimed+open rows MUST use CREATE TABLE IF NOT EXISTS AS SELECT."""
    sql = _migration_005_text()
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+ticket_backup_claimed_open_20260706\s+AS\s+SELECT",
        sql,
        re.IGNORECASE,
    ), "Idempotent backup table (CREATE TABLE IF NOT EXISTS ... AS SELECT) missing"


def test_migration_005_backup_targets_claimed_open_rows() -> None:
    """Backup MUST select rows where claimedBy IS NOT NULL AND status='open'."""
    sql = _migration_005_text()
    assert re.search(
        r'SELECT\s+\*\s+FROM\s+ticket\s+WHERE\s+"claimedBy"\s+IS\s+NOT\s+NULL\s+AND\s+status\s*=\s*\'open\'',
        sql,
        re.IGNORECASE,
    ), "Backup WHERE clause (claimedBy IS NOT NULL AND status='open') missing"


def test_migration_005_normalizes_transfer_status() -> None:
    """UPDATE ticket SET status='claimed' WHERE claimedBy IS NOT NULL AND status='open' MUST exist."""
    sql = _migration_005_text()
    assert re.search(
        r"UPDATE\s+ticket\s+SET\s+status\s*=\s*'claime\w*'\s+"
        r"WHERE\s+\"claimedBy\"\s+IS\s+NOT\s+NULL\s+AND\s+status\s*=\s*'open'",
        sql,
        re.IGNORECASE,
    ), "Transfer normalization UPDATE missing"


# --- pg_cron retention (guarded) ------------------------------------------


def test_migration_005_schedules_cron_retention() -> None:
    """A cron.schedule('ticket_audit_retention', ...) statement MUST be present."""
    sql = _migration_005_text()
    assert re.search(
        r"cron\.schedule\s*\(\s*'ticket_audit_retention'",
        sql,
        re.IGNORECASE,
    ), "cron.schedule('ticket_audit_retention') missing"


def test_migration_005_cron_retention_deletes_old_rows() -> None:
    """The cron job MUST DELETE ticket_audit rows older than 90 days."""
    sql = _migration_005_text()
    assert re.search(
        r"DELETE\s+FROM\s+ticket_audit\s+WHERE\s+\"createdAt\"\s*<\s*now\s*\(\s*\)\s*-\s*interval\s+'90\s+days'",
        sql,
        re.IGNORECASE,
    ), "cron retention DELETE (createdAt < now() - interval '90 days') missing"


def test_migration_005_cron_schedule_is_guarded() -> None:
    """The cron schedule MUST be guarded so re-running does not create a duplicate job."""
    sql = _migration_005_text()
    # Guard checks cron.job by jobname before scheduling.
    assert re.search(
        r"cron\.job\s+WHERE\s+jobname\s*=\s*'ticket_audit_retention'",
        sql,
        re.IGNORECASE,
    ), "cron.job guard (jobname = 'ticket_audit_retention') missing — re-run would error"


# ===========================================================================
# Migration 006 — drop user table + FK constraints
# ===========================================================================

MIGRATION_006 = MIGRATIONS_DIR / "006_drop_user_table.sql"


def _migration_006_text() -> str:
    """Return Migration 006 SQL text, failing cleanly if the file is absent."""
    assert MIGRATION_006.is_file(), f"Migration 006 not found at {MIGRATION_006}"
    return MIGRATION_006.read_text()


def test_migration_006_file_exists() -> None:
    """Migration 006 artifact MUST exist at migrations/006_drop_user_table.sql."""
    assert MIGRATION_006.is_file(), f"Migration file missing: {MIGRATION_006}"


def test_migration_006_drops_four_fk_constraints() -> None:
    """Migration 006 MUST drop all 4 FK constraints referencing user(id).

    Spec: member.userId, infraction.targetId, infraction.moderatorId,
    ticket.authorId all had FK to user(id). Migration drops each constraint.
    """
    sql = _migration_006_text()

    # The 4 FK constraints following the Postgres auto-naming convention:
    # {table}_{column}_fkey
    expected_constraints = [
        "member_userId_fkey",
        "infraction_targetId_fkey",
        "infraction_moderatorId_fkey",
        "ticket_authorId_fkey",
    ]

    for constraint_name in expected_constraints:
        assert re.search(
            rf'DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+"?{re.escape(constraint_name)}"?',
            sql,
            re.IGNORECASE,
        ), f"DROP CONSTRAINT IF EXISTS {constraint_name} missing"


def test_migration_006_drops_user_table() -> None:
    """Migration 006 MUST drop the user table with IF EXISTS."""
    sql = _migration_006_text()
    assert re.search(
        r'DROP\s+TABLE\s+IF\s+EXISTS\s+"user"',
        sql,
        re.IGNORECASE,
    ), 'DROP TABLE IF EXISTS "user" missing'


def test_migration_006_is_idempotent() -> None:
    """Every ALTER/DROP in Migration 006 MUST use IF EXISTS (re-runnable)."""
    sql = _migration_006_text()

    # All DROP CONSTRAINT must use IF EXISTS
    drop_constraints = re.findall(r'DROP\s+CONSTRAINT\s+(IF\s+EXISTS\s+)?"?\w+"?', sql, re.IGNORECASE)
    for stmt in drop_constraints:
        assert "IF EXISTS" in stmt.upper(), f"Non-idempotent DROP CONSTRAINT: {stmt!r} — MUST use IF EXISTS"

    # DROP TABLE must use IF EXISTS
    drop_tables = re.findall(r"DROP\s+TABLE\s+(IF\s+EXISTS\s+)?", sql, re.IGNORECASE)
    assert drop_tables, "Expected at least one DROP TABLE statement"
    for stmt in drop_tables:
        assert "IF EXISTS" in stmt.upper(), "Non-idempotent DROP TABLE — MUST use IF EXISTS"


# ===========================================================================
# Migration sequence -- final state (user table removed after 001-006)
# ===========================================================================


def _read_all_migrations_in_order() -> list[str]:
    """Return SQL text for each migration file in numeric order."""
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    texts: list[str] = []
    for f in migration_files:
        assert f.is_file(), f"Migration file missing: {f}"
        texts.append(f.read_text())
    return texts


def test_final_state_has_no_user_table_after_all_migrations() -> None:
    """GIVEN all migrations 001-006 run in order, WHEN the final state is
    checked, THEN the user table does not exist (Migration 006 DROP cancels
    Migration 001 CREATE).

    This is a static analysis test: verify that 006_drop_user_table.sql
    contains the DROP TABLE that counters the CREATE TABLE in 001.
    """
    create_sql = (MIGRATIONS_DIR / "001_initial_schema.sql").read_text()
    drop_sql = (MIGRATIONS_DIR / "006_drop_user_table.sql").read_text()

    # Migration 001 creates the user table (even though the final state won't have it)
    assert re.search(
        r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"user"',
        create_sql,
        re.IGNORECASE,
    ), "Migration 001 should CREATE the user table (it will be dropped by 006)"

    # Migration 006 drops the user table — this is what ensures the final state
    assert re.search(
        r'DROP\s+TABLE\s+IF\s+EXISTS\s+"user"',
        drop_sql,
        re.IGNORECASE,
    ), "Migration 006 MUST DROP the user table to achieve the final state"

    # Migration 006 also drops all 4 FK constraints referencing user(id)
    expected_constraints = [
        "member_userId_fkey",
        "infraction_targetId_fkey",
        "infraction_moderatorId_fkey",
        "ticket_authorId_fkey",
    ]
    for constraint in expected_constraints:
        assert re.search(
            rf'DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+"?{re.escape(constraint)}"?',
            drop_sql,
            re.IGNORECASE,
        ), f"Migration 006 MUST DROP CONSTRAINT {constraint}"


def test_no_fk_references_to_user_table_in_final_schema() -> None:
    """After all migrations through 006, no active FK references user(id).

    Static analysis: scan all migration SQL and verify that any
    REFERENCES "user"(id) from 001 are countered by DROP CONSTRAINT in 006.
    """
    create_sql = (MIGRATIONS_DIR / "001_initial_schema.sql").read_text()
    drop_sql = (MIGRATIONS_DIR / "006_drop_user_table.sql").read_text()

    # Count how many FK references to "user"(id) exist in 001
    fk_refs = re.findall(
        r'REFERENCES\s+"user"\s*\(\s*id\s*\)',
        create_sql,
        re.IGNORECASE,
    )
    assert len(fk_refs) == 4, f"Expected 4 FK references to user(id) in 001, found {len(fk_refs)}"

    # Count how many FK constraints 006 drops
    fk_drops = re.findall(
        r"DROP\s+CONSTRAINT\s+IF\s+EXISTS",
        drop_sql,
        re.IGNORECASE,
    )
    assert len(fk_drops) == 4, f"Expected 4 DROP CONSTRAINT in 006, found {len(fk_drops)}"


# ===========================================================================
# Migration 007 — realtime publication (idempotent, reproducibility)
# ===========================================================================

MIGRATION_007 = MIGRATIONS_DIR / "007_realtime_publication.sql"


def test_migration_007_file_exists() -> None:
    """Migration 007 artifact MUST exist at migrations/007_realtime_publication.sql."""
    assert MIGRATION_007.is_file(), f"Migration file missing: {MIGRATION_007}"


def test_migration_007_adds_tables_to_realtime_publication() -> None:
    """Migration 007 MUST add guild, greeting_config, ticket, ticket_note
    to the supabase_realtime publication for CDC support.

    The publication is already configured in the live Supabase DB — this
    migration exists purely for reproducibility.
    """
    sql = MIGRATION_007.read_text()

    # Must reference the supabase_realtime publication
    assert re.search(
        r"ALTER\s+PUBLICATION\s+supabase_realtime",
        sql,
        re.IGNORECASE,
    ), "ALTER PUBLICATION supabase_realtime statement missing"

    # Must reference all 4 tables
    for table in ("guild", "greeting_config", "ticket", "ticket_note"):
        assert re.search(
            rf"\b{table}\b",
            sql,
            re.IGNORECASE,
        ), f"Table {table} missing from publication migration"


def test_migration_007_is_idempotent() -> None:
    """Migration 007 MUST be safe to re-run without error.

    ALTER PUBLICATION ... ADD TABLE does not support IF NOT EXISTS natively,
    so the migration must use a DO block or exception handling for idempotency.
    """
    sql = MIGRATION_007.read_text()

    # Check for idempotency mechanism: either DO block with EXCEPTION,
    # or a check-and-skip approach
    has_do_block = re.search(r"DO\s+\$", sql, re.IGNORECASE)
    has_exception = re.search(r"EXCEPTION", sql, re.IGNORECASE)
    has_already_exists = re.search(
        r"already\s+exists|duplicate|42710",
        sql,
        re.IGNORECASE,
    )

    assert has_do_block or has_exception or has_already_exists, (
        "Migration 007 must be idempotent — use a DO block with EXCEPTION handling "
        "or check pg_publication_tables before ALTER PUBLICATION"
    )
