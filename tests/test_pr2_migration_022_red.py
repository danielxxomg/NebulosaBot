from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _read(name):
    return (MIGRATIONS_DIR / name).read_text()


def test_022_exists():
    _read("022_ticket_scheduled_close.sql")


def test_022_has_both_columns():
    sql = _read("022_ticket_scheduled_close.sql")
    assert '"scheduledCloseAt"' in sql and '"scheduledCloseBy"' in sql
    assert "TIMESTAMPTZ" in sql


def test_022_partial_index_predicate():
    sql = _read("022_ticket_scheduled_close.sql")
    assert "idx_ticket_scheduled_close" in sql
    assert "status IN ('open', 'claimed')" in sql
    assert '"scheduledCloseAt" IS NOT NULL' in sql


def test_022_idempotent():
    sql = _read("022_ticket_scheduled_close.sql").upper()
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql.upper()


def test_022_documents_schema_migrations_and_rollback():
    sql = _read("022_ticket_scheduled_close.sql")
    assert "schema_migrations" in sql.lower()
    assert "DROP COLUMN" in sql.upper() and "DROP INDEX" in sql.upper()


def test_022_coexists_with_015():
    sql15 = _read("015_ticket_lifecycle_reliability.sql")
    sql22 = _read("022_ticket_scheduled_close.sql")
    assert "idx_ticket_active_channel" in sql15
    assert "idx_ticket_scheduled_close" in sql22
    assert "idx_ticket_scheduled_close" not in sql15
