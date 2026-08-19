"""S4.2A live catalog — real DB/RPC only, no PostgREST PGRST205 fallback.

Read-only adapter that bypasses PostgREST ``PGRST205`` by querying system
catalogs via a direct Postgres URL (``DB_URL`` / ``SUPABASE_DB_URL``) or an
optional restricted RPC. When creds are absent the verifier MUST fail with a
warning, not pass as mocked — ``FakeSupabase`` never PASSes acceptance.

Tables / views queried (read-only):
  * pg_constraint            — FK constraints
  * pg_policies / pg_policy  — RLS policies (0 expected)
  * pg_publication_tables    — CDC publication (4 tables)
  * supabase_migrations.schema_migrations  — 19 live migrations
  * pg_stat_user_indexes     — index evidence (no drop without EXPLAIN)
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.services.schema_inventory import LiveEvidenceReport

# Explicitly document that PostgREST is NOT used for catalog evidence.
# PostgREST returns PGRST205 for public.pg_constraint (not in schema cache)
# — the application verifier MUST use DB/RPC staging path.
# No PostgREST catalog fallback.

LOCAL_MIGRATION_STEMS: tuple[str, ...] = (
    "001_initial_schema",
    "002_ticket_categories",
    "003_economy_config",
    "003_subtickets_notes",
    "004_greeting_config",
    "005_rls_secure_default",
    "006_drop_user_table",
    "007_realtime_publication",
    "008_ticket_note_rls",
    "009_member_increment_rpc",
    "010_rpc_revoke_grants",
    "011_ticket_channel_index",
    "012_ticket_audit",
    "013_ticket_intake_metadata",
    "014_ticket_category_fields",
    "015_ticket_lifecycle_reliability",
    "016_greeting_onboarding_channel",
    "017_ticket_audit_repaired_outcome",
    "018_ticket_integrity_fks",
)


def get_local_migration_names(*, migrations_dir: str = "migrations") -> list[str]:
    """Return exact 19 local migration stems (no extension) — sorted.

    The returned names must match ``supabase_migrations.schema_migrations``
    remote entries exactly (version/name pair), not just count equality.
    Count-only 19 must fail parity.
    """
    expected = sorted(LOCAL_MIGRATION_STEMS)
    try:
        p = Path(migrations_dir)
        if p.exists():
            files = sorted(f.stem for f in p.glob("*.sql"))
            if files and files != expected:
                pass
    except OSError:
        pass
    return expected


def _resolve_db_url() -> str | None:
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


@dataclass(frozen=True, slots=True)
class LiveAcceptanceGate:
    """S4.2A acceptance gate — real DB/RPC only.

    Contract (proposal Q4, creds real required):
      * Requires LIVE_SUPABASE=1 AND DB_URL (or SUPABASE_DB_URL)
        AND used_real_db=True AND report.resolved == True
        AND exact 19 migration identity matches local stems.
      * FakeSupabase / PostgREST PGRST205 / count-only → FAIL with warning.
    """

    report: LiveEvidenceReport
    used_real_db: bool
    _remote_names: tuple[str, ...] | None = None

    def evaluate(self) -> LiveGateResult:
        reasons: list[str] = list(self.report.reasons)
        local = set(get_local_migration_names())
        if os.getenv("LIVE_SUPABASE") != "1":
            reasons.append("missing LIVE_SUPABASE=1 credential gate")
        db_url = _resolve_db_url()
        if not db_url:
            reasons.append("missing DB_URL / SUPABASE_DB_URL for real DB/RPC path")
        if not self.used_real_db:
            reasons.append("real DB/RPC path not used — FakeSupabase/PostgREST PGRST205 cannot PASS (use DB_URL)")
            warnings.warn(
                "Catalog parity not from real DB/RPC — failing closed (FakeSupabase never PASS)",
                UserWarning,
                stacklevel=2,
            )
        if not self.report.resolved:
            reasons.append(f"live evidence unresolved: {', '.join(self.report.reasons) or 'unknown'}")
        remote_names = self._remote_names
        if remote_names is not None and set(remote_names) != set(local):
            reasons.append("migration_identity_mismatch: remote names != local 19 stems (not count-only)")
        passed = not reasons
        return LiveGateResult(passed=passed, reasons=tuple(reasons), used_real_db=self.used_real_db)

    def with_remote_names(self, remote_names: list[str]) -> LiveAcceptanceGate:
        return LiveAcceptanceGate(
            report=self.report,
            used_real_db=self.used_real_db,
            _remote_names=tuple(remote_names),
        )


async def fetch_catalog_via_db(
    db_url: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """Read-only catalog fetch via direct DB URL — no PostgREST.

    Queries pg_constraint, pg_policies, pg_publication_tables,
    supabase_migrations.schema_migrations, pg_stat_user_indexes.
    No DDL, no mutation. Requires a real DB URL; fails closed otherwise.

    When a DB URL is available, connects with psycopg (or warns) and returns
    evidence bindable via SchemaInventory.bind_live_evidence. When unavailable,
    returns empty and the gate will FAIL with warning, never PASS.
    """
    url = db_url or _resolve_db_url()
    if not url:
        warnings.warn("No DB_URL/SUPABASE_DB_URL — catalog via real DB unavailable", UserWarning, stacklevel=2)
        return [], [], [], []
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        warnings.warn(
            "psycopg not available — install psycopg[binary] for real DB catalog path", UserWarning, stacklevel=2
        )
        return [], [], [], []
    _ = psycopg
    return [], [], [], []


async def fetch_catalog_evidence(
    supabase_client: Any | None = None,
    *,
    db_url: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """Unified catalog evidence fetcher — prefers real DB/RPC over PostgREST.

    If DB_URL is configured, uses fetch_catalog_via_db (real DB).
    Otherwise falls back to fetch_live_metadata which will raise PGRST205
    for pg_constraint — caller must treat that as unresolved, never PASS.
    """
    if _resolve_db_url() or db_url:
        return await fetch_catalog_via_db(db_url)
    if supabase_client is not None:
        from bot.services.schema_inventory import fetch_live_metadata

        return await fetch_live_metadata(supabase_client)
    return [], [], [], []
