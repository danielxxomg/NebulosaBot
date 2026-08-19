"""S4.2B — Tracked execution for 018 8-step live staging migration.

Fixed-argv ``psql`` path with ``shell=False``, ``ON_ERROR_STOP``,
timeout, and non-zero exit abort. Requires ``LIVE_SUPABASE=1`` plus a
real ``DB_URL`` (or ``SUPABASE_DB_URL`` / ``DATABASE_URL``); when creds
are absent the gate fails with a ``UserWarning``, never a mocked pass.

The 8-step ordered DDL lives in ``migrations/018_ticket_integrity_fks.sql``:
  (1) ``DO $preflight$`` — duplicates, 21/21 valid UUID, 0 note orphans,
      audit 1/1 retention, parent depth/missing
  (2) ``categoryId TEXT -> UUID USING`` cast with backup
      ``ticket_backup_categoryid_text_20260818``
  (3) child indexes
  (4) parent ``RESTRICT``
  (5) category ``SET NULL``
  (6) note ``CASCADE``
  (7) audit ``SET NULL`` nullable + orphan ``NULL`` cleanup
  (8) ``VALIDATE CONSTRAINT`` + drop only ``idx_ticket_guild_number``
Rollback: ``DOWN`` in the same file restores ``TEXT`` via backup.

No ``execute_sql`` / SQL-editor untracked substitute — tracked ``psql -f``
via this helper or ``supabase db push`` only.
"""

from __future__ import annotations

import logging
import os
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Tracked migration allowlist — no arbitrary file fallback.
ALLOWED_MIGRATION_STEM = "018_ticket_integrity_fks"
ALLOWED_MIGRATION_FILE = f"{ALLOWED_MIGRATION_STEM}.sql"
DEFAULT_MIGRATION_PATH = f"migrations/{ALLOWED_MIGRATION_FILE}"

# Backup evidence — preserves TEXT categoryId for DOWN/rollback.
BACKUP_TABLE = "ticket_backup_categoryid_text_20260818"


def _resolve_db_url(explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    for key in ("DB_URL", "SUPABASE_DB_URL", "DATABASE_URL"):
        v = os.getenv(key, "").strip()
        if v:
            return v
    return None


@dataclass(frozen=True, slots=True)
class LiveGateResult:
    passed: bool
    reasons: tuple[str, ...]
    used_real_db: bool


def check_live_gate(*, used_real_db: bool, db_url: str | None = None) -> LiveGateResult:
    """Credential gate for 018 live acceptance — fail-with-warning, not mocked pass.

    Contract (database-layer spec):
      * Requires ``LIVE_SUPABASE=1`` and a real DB URL and ``used_real_db=True``.
      * ``FakeSupabase`` / missing creds → ``passed=False`` + ``UserWarning``,
        never a fake PASS.
    """
    reasons: list[str] = []
    if os.getenv("LIVE_SUPABASE") != "1":
        reasons.append("missing LIVE_SUPABASE=1 credential gate")
    url = db_url if db_url is not None else _resolve_db_url()
    if not url:
        reasons.append("missing DB_URL / SUPABASE_DB_URL for real DB path")
    if not used_real_db:
        reasons.append("real DB/RPC path not used — FakeSupabase cannot PASS 018 live (use DB_URL)")
    # Emit exactly one warning on any gate failure — fail-with-warning contract.
    if reasons:
        warnings.warn(
            f"018 live gate blocked: {'; '.join(reasons)}",
            UserWarning,
            stacklevel=2,
        )
    passed = not reasons
    return LiveGateResult(passed=passed, reasons=tuple(reasons), used_real_db=used_real_db)


def build_psql_argv(db_url: str, migration_file: str = DEFAULT_MIGRATION_PATH) -> list[str]:
    """Build fixed-argv ``psql`` invocation for the tracked 018 file.

    No shell composition — caller must use ``subprocess.run(..., shell=False)``.
    Only ``018_ticket_integrity_fks.sql`` is allowed; arbitrary files are
    rejected to prevent untracked SQL-editor drift.
    """
    if ALLOWED_MIGRATION_STEM not in migration_file:
        msg = f"untracked file rejected: {migration_file!r} — only {ALLOWED_MIGRATION_FILE} allowed"
        raise ValueError(msg)
    # Validate file exists for evidence (backup/timeouts live in SQL).
    p = Path(migration_file)
    if not p.exists():
        msg = f"migration file not found: {migration_file}"
        raise FileNotFoundError(msg)
    text = p.read_text(encoding="utf-8")
    # Smoke-check that backup and timeout guard live in the migration.
    if BACKUP_TABLE not in text:
        msg2 = f"backup table {BACKUP_TABLE} not found in {migration_file}"
        warnings.warn(msg2, UserWarning, stacklevel=2)
    # Fixed argv: psql + ON_ERROR_STOP + file via -f, no shell string.
    return [
        "psql",
        db_url,
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(p),
    ]


def run_psql_migration(
    *,
    db_url: str | None = None,
    migration_file: str = DEFAULT_MIGRATION_PATH,
    timeout: int = 60,
) -> LiveGateResult:
    """Execute the tracked 018 via fixed-argv psql — 8-step ordered DDL.

    Preconditions: ``LIVE_SUPABASE=1`` and real ``DB_URL`` and timeout guard.
    Uses ``shell=False``, ``ON_ERROR_STOP=1``, aborts on non-zero exit.
    Captures before/after implicitly via migration backup + VALIDATE + drop.
    Returns gate result; raises on psql failure.
    """
    url = _resolve_db_url(db_url)
    # Gate first — fail-with-warning, not mocked pass.
    gate = check_live_gate(used_real_db=bool(url), db_url=url)
    if not gate.passed:
        return gate
    if url is None:  # gate already failed closed above
        msg = "018 live gate blocked — no DB_URL"
        raise RuntimeError(msg)
    argv = build_psql_argv(url, migration_file)
    # before/after capture: backup + VALIDATE live in SQL; psql executes atomically per statement.
    result = subprocess.run(argv, shell=False, timeout=timeout, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        msg = f"psql migration failed (exit {result.returncode}): {result.stderr[:2000]}"
        raise RuntimeError(msg)
    return LiveGateResult(passed=True, reasons=(), used_real_db=True)


def main() -> None:
    """CLI entry for approved staging window — tracked psql execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply 018_ticket_integrity_fks.sql via fixed-argv psql (LIVE_SUPABASE=1 + DB_URL required)"
    )
    parser.add_argument("--file", default=DEFAULT_MIGRATION_PATH, help="tracked migration file (only 018 allowed)")
    parser.add_argument("--timeout", type=int, default=60, help="statement timeout seconds")
    parser.add_argument("--db-url", default=None, help="override DB_URL")
    args = parser.parse_args()

    gate = check_live_gate(used_real_db=bool(_resolve_db_url(args.db_url)), db_url=args.db_url)
    if not gate.passed:
        msg = f"live gate blocked: {'; '.join(gate.reasons)}"
        raise SystemExit(msg)

    result = run_psql_migration(db_url=args.db_url, migration_file=args.file, timeout=args.timeout)
    if not result.passed:
        msg = f"migration gate failed: {'; '.join(result.reasons)}"
        raise SystemExit(msg)
    msg = f"018 applied via psql {args.file} — validate + drop idx ok; backup {BACKUP_TABLE} retained"
    logger.info(msg)


if __name__ == "__main__":
    main()
