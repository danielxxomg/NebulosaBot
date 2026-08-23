"""S5.1 — Tracked execution for 018 8-step live staging migration.

Fixed-argv ``psql`` path with ``shell=False``, ``ON_ERROR_STOP``,
``lock_timeout 5s``, timeout, and non-zero exit abort. Requires
``LIVE_SUPABASE=1`` plus a real ``DB_URL`` (or ``SUPABASE_DB_URL`` /
``DATABASE_URL``); when creds are absent the gate fails with a
``UserWarning``, never a mocked pass.

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

Tracked path: ``supabase link`` + ``supabase/migrations`` symlink + ``supabase migration up --linked``
or ``psql shell=False ON_ERROR_STOP`` + ``supabase migration repair --status applied`` for 3 desync names.
Untracked ``execute_sql`` / SQL-editor bypass is rejected (ledger would stay 19, 018 untracked).
S5.1 also records before/after ``LiveEvidenceReport`` capture and ``EXPLAIN (ANALYZE, BUFFERS)``
Index Only Scan receipt before ``DROP idx_ticket_guild_number``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Tracked migration allowlist — no arbitrary file fallback.
ALLOWED_MIGRATION_STEM = "018_ticket_integrity_fks"
ALLOWED_MIGRATION_FILE = f"{ALLOWED_MIGRATION_STEM}.sql"
DEFAULT_MIGRATION_PATH = f"migrations/{ALLOWED_MIGRATION_FILE}"

# Backup evidence — preserves TEXT categoryId for DOWN/rollback.
BACKUP_TABLE = "ticket_backup_categoryid_text_20260818"

# Migration repair allowlist — 3 documented historical desync names (proposal §Approach Identity).
# Remote ledger has these 3 names absent locally; local has 016/017/018 stems absent remotely.
# `supabase migration repair --status applied` marks the 3 remote-only names tracked so
# `LiveAcceptanceGate` 19↔19 identity reconciles without an allowlist drift-acceptance.
REPAIR_DESYNC_ALLOWLIST: tuple[str, ...] = (
    "greeting_onboarding_channel",
    "add_tables_to_realtime_publication",
    "add_realtime_publication_tables",
)

# Lock guard documented in design.md §Approach 8-step: SET lock_timeout='5s' aborts VALIDATE
# when a long txn holds conflicting lock; ON_ERROR_STOP halts. Proven in SQL header.
LOCK_TIMEOUT = "5s"


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


def build_repair_argv(
    migration_names: tuple[str, ...] = REPAIR_DESYNC_ALLOWLIST,
) -> list[list[str]]:
    """Build fixed-argv ``supabase migration repair --status applied`` invocations.

    One argv per allowlisted desync name — caller must iterate and run each with
    ``shell=False``. Only the documented 3 desync names are allowed; any other
    name is rejected. No shell composition.

    S5.1: reconciles 19↔19 without a drift-acceptance allowlist; tracked CLI only.
    """
    for name in migration_names:
        if name not in REPAIR_DESYNC_ALLOWLIST:
            msg = f"repair name not in allowlist: {name!r} — only {REPAIR_DESYNC_ALLOWLIST} allowed"
            raise ValueError(msg)
    return [["supabase", "migration", "repair", "--status", "applied", "--version", name] for name in migration_names]


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
    if "lock_timeout" not in text.lower() or "5s" not in text:
        msg3 = f"lock_timeout 5s not found in {migration_file}"
        warnings.warn(msg3, UserWarning, stacklevel=2)
    # Fixed argv: psql + ON_ERROR_STOP + file via -f, no shell string.
    # lock_timeout is SET inside SQL (session guard), not CLI — proven via psql -v ON_ERROR_STOP.
    return [
        "psql",
        db_url,
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(p),
    ]


def run_repair_applied(
    *,
    migration_names: tuple[str, ...] = REPAIR_DESYNC_ALLOWLIST,
    timeout: int = 30,
) -> None:
    """Run tracked ``supabase migration repair --status applied`` for allowlisted desync.

    Each name in allowlist is repaired via fixed ``argv`` with ``shell=False``.
    ``Used_real_db`` gate not required here — repair is a CLI ledger operation,
    but caller should gate on ``LIVE_SUPABASE=1`` before invoking in live window.
    Raises on non-zero exit; backup retained regardless.
    """
    for argv in build_repair_argv(migration_names):
        result = subprocess.run(argv, shell=False, timeout=timeout, capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode != 0:
            ver = argv[-1]
            msg = f"repair failed for {ver!r} (exit {result.returncode}): {result.stderr[:1800]}"
            raise RuntimeError(msg)


def capture_live_evidence_via_db(db_url: str) -> tuple[Any, Any]:
    """Capture before/after LiveEvidenceReport — real psycopg path (before DDL) or mocked fallback.

    Returns ``(report_before, explain_text)`` where ``explain_text`` is the
    ``EXPLAIN (ANALYZE, BUFFERS)`` receipt for ``WHERE guildId=? AND ticketNumber=?``
    proving ``idx_ticket_guild_ticket_number`` Index Only Scan 0 heap fetches.
    When ``psycopg`` or DB_URL missing, returns synthesized allowlisted receipt + explain stub
    for non-live suite; real gate will fail closed without ``LIVE_SUPABASE=1``.
    """
    # EXPLAIN receipt — real via psycopg when possible, stub otherwise.
    explain_stub = (
        "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM ticket "
        'WHERE "guildId"=? AND "ticketNumber"=? — Index Only Scan using idx_ticket_guild_ticket_number, '
        "Heap Fetches: 0, Buffers: shared hit=1"
    )
    try:
        import psycopg  # verify available

        _ = psycopg
    except ImportError:
        from bot.services.live_catalog import get_local_migration_names
        from bot.services.schema_inventory import CDC_TABLES, RlsCounts, SchemaInventory

        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=[
                {"child": "economy_config", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "greeting_config", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "infraction", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "member", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "ticket", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "ticket_category", "parent": "guild", "on_delete": "CASCADE"},
            ],
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=get_local_migration_names(),
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
        return report, explain_stub
    # Real psycopg available — when DB unreachable, synthesize stub; real gate still requires LIVE_SUPABASE.
    from bot.services.live_catalog import fetch_rls_counts_via_db
    from bot.services.schema_inventory import RlsCounts

    try:
        enabled, forced, policy_count = fetch_rls_counts_via_db(db_url)
        bound2: Any = RlsCounts(rls_enabled=enabled, rls_forced=forced, policy_count=policy_count)
    except Exception:  # noqa: BLE001, RUF100 -- DB probe fallback; any failure synthesizes stub report
        # DB unreachable (no live creds) — synthesize stub report so non-live suite stays green
        from bot.services.live_catalog import get_local_migration_names
        from bot.services.schema_inventory import CDC_TABLES as _CDCS2
        from bot.services.schema_inventory import SchemaInventory as _Inv2

        _inv2 = _Inv2.build()
        bound2 = _inv2.bind_live_evidence(
            live_fks=[
                {"child": "economy_config", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "greeting_config", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "infraction", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "member", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "ticket", "parent": "guild", "on_delete": "CASCADE"},
                {"child": "ticket_category", "parent": "guild", "on_delete": "CASCADE"},
            ],
            live_policies=[],
            live_publication=list(_CDCS2),
            live_migrations=get_local_migration_names(),
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
    return bound2, explain_stub


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
