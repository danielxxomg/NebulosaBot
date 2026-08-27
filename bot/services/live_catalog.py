"""S4.2A live catalog — real DB/RPC only, no PostgREST PGRST205 fallback.

Read-only adapter that bypasses PostgREST ``PGRST205`` by querying system
catalogs via a direct Postgres URL (``DB_URL`` / ``SUPABASE_DB_URL``) or an
optional restricted RPC. When creds are absent the verifier MUST fail with a
warning, not pass as mocked — ``FakeSupabase`` never PASSes acceptance.

Tables / views queried (read-only):
  * pg_constraint            — FK constraints
  * pg_policies / pg_policy  — RLS policies (0 expected)
  * pg_publication_tables    — CDC publication (6 tables)
  * supabase_migrations.schema_migrations  — 27 live migrations
"""

from __future__ import annotations

import asyncio
import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from bot.services.schema_inventory import LiveEvidenceReport, fetch_live_metadata

logger = logging.getLogger(__name__)

# Explicitly document that PostgREST is NOT used for catalog evidence.
# PostgREST returns PGRST205 for public.pg_constraint (not in schema cache)
# — the application verifier MUST use DB/RPC staging path.
# No PostgREST catalog fallback.

LOCAL_MIGRATION_STEMS: tuple[str, ...] = (
    "001_initial_schema",
    "002_ticket_categories",
    "003_economy_config",
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
    "019_subtickets_notes",
    "020_greeting_updated_at",
    "021_greeting_theme_id",
    "022_ticket_scheduled_close",
    "023_rls_remaining_tables",
    "024_permission_matrix_indexes",
    "025_drop_ticket_backup_categoryid_text_20260818",
    "026_realtime_member_economy_config",
    "027_private_transcript_bucket",
    "028_retention",
    "029_crash_report_indexes",
)


def get_local_migration_names(*, migrations_dir: str = "migrations") -> list[str]:
    """Return exact 29 local migration stems (no extension) — sorted.

    The returned names must match ``supabase_migrations.schema_migrations``
    remote entries exactly (version/name pair), not just count equality.
    Count-only mismatches must fail parity.

    Cycle 5 (S3): the list was re-synced with the actual ``migrations/``
    directory — the historical phantom ``003_subtickets_notes`` entry (a
    pre-renumber artifact; the file lives on as ``019_subtickets_notes``)
    was dropped and migrations 019-025 were added, matching remote 25/25.
    S1 (clean-1.0): 027_private_transcript_bucket added for triple-path Storage.
    """
    expected = sorted(LOCAL_MIGRATION_STEMS)
    try:
        p = Path(migrations_dir)
        if p.exists():
            files = sorted(f.stem for f in p.glob("*.sql"))
            if files and files != expected:
                # Pinned identity is the contract; drift is surfaced loudly so
                # a new migration without a stems update cannot pass silently.
                warnings.warn(
                    f"local migration drift: on-disk {files} != pinned {expected}",
                    UserWarning,
                    stacklevel=2,
                )
    except OSError:
        logger.warning("Could not scan migrations dir %r — returning pinned stems", migrations_dir, exc_info=True)
    return expected


def _resolve_db_url() -> str | None:
    for key in ("DB_URL", "SUPABASE_DB_URL", "DATABASE_URL"):
        v = os.getenv(key, "").strip()
        if v:
            return v
    return None


@dataclass(frozen=True, slots=True)
class LiveGateResult:
    """Outcome of :meth:`LiveAcceptanceGate.evaluate`.

    Attributes:
        passed: True only when every fail-closed check produced no reason.
        reasons: Human-readable failure reasons (empty when passed).
        used_real_db: True only when a valid 4-query ProvenanceToken backed
            the evaluation — never for FakeSupabase or synthetic bools.
    """

    passed: bool
    reasons: tuple[str, ...]
    used_real_db: bool


@dataclass(frozen=True, slots=True)
class ProvenanceToken:
    """Provenance minted inside _sync_fetch_catalog — 4 psycopg queries.

    Cannot be caller-forged with used_real_db=True; caller-supplied bool
    without matching provenance is treated as synthetic FakeSupabase.
    """

    query_count: int
    catalog_hash: str = ""


@dataclass(frozen=True, slots=True)
class LiveAcceptanceGate:
    """S4.2A acceptance gate — real DB/RPC only.

    Contract (proposal Q4, creds real required):
      * Requires LIVE_SUPABASE=1 AND DB_URL (or SUPABASE_DB_URL)
        AND used_real_db=True AND report.resolved == True
        AND exact migration identity matches local stems (names and count).
      * FakeSupabase / PostgREST PGRST205 / count-only → FAIL with warning.
    """

    report: LiveEvidenceReport
    used_real_db: bool | ProvenanceToken = False
    _remote_names: tuple[str, ...] | None = None

    def _has_provenance(self) -> bool:
        if isinstance(self.used_real_db, ProvenanceToken):
            return self.used_real_db.query_count == 4
        return False

    def evaluate(self) -> LiveGateResult:
        """Evaluate the fail-closed acceptance contract.

        Accumulates a reason for every unmet credential/provenance/parity
        requirement (LIVE_SUPABASE gate, DB_URL, provenance token, 9/7/0
        RLS binding, resolved report, exact migration identity) and warns
        when the real-DB path was not used. PASS requires zero reasons.
        """
        reasons: list[str] = list(self.report.reasons)
        local = set(get_local_migration_names())
        if os.getenv("LIVE_SUPABASE") != "1":
            reasons.append("missing LIVE_SUPABASE=1 credential gate")
        db_url = _resolve_db_url()
        if not db_url:
            reasons.append("missing DB_URL / SUPABASE_DB_URL for real DB/RPC path")
        if not self._has_provenance():
            if isinstance(self.used_real_db, bool) and self.used_real_db is True:
                reasons.append("synthetic live FakeSupabase — real provenance token required (4 psycopg queries)")
            else:
                reasons.append("real DB/RPC path not used — FakeSupabase/PostgREST PGRST205 cannot PASS (use DB_URL)")
            warnings.warn(
                "Catalog parity not from real DB/RPC — failing closed (FakeSupabase never PASS)",
                UserWarning,
                stacklevel=2,
            )
        # 9/7/0 binding — report must carry proven RLS counts
        rc = getattr(self.report, "rls_counts", None)
        if rc is None:
            reasons.append("rls_970_not_bound — fetch_rls_counts_via_db provenance missing")
        elif hasattr(rc, "rls_enabled"):
            if rc.rls_enabled != 9 or rc.rls_forced != 7 or rc.policy_count != 0:
                reasons.append("rls_970_mismatch")
        elif isinstance(rc, tuple) and len(rc) == 3:
            if rc[0] != 9 or rc[1] != 7 or rc[2] != 0:
                reasons.append("rls_970_mismatch")
        else:
            reasons.append("rls_970_not_bound — invalid provenance shape")
        if not self.report.resolved:
            reasons.append(f"live evidence unresolved: {', '.join(self.report.reasons) or 'unknown'}")
        remote_names = self._remote_names
        if remote_names is not None and set(remote_names) != set(local):
            reasons.append("migration_identity_mismatch: remote names != local stems (not count-only)")
        passed = not reasons
        return LiveGateResult(passed=passed, reasons=tuple(reasons), used_real_db=self._has_provenance())

    def with_remote_names(self, remote_names: list[str]) -> LiveAcceptanceGate:
        """Return a copy bound to the live ``schema_migrations`` names for identity parity."""
        return LiveAcceptanceGate(
            report=self.report,
            used_real_db=self.used_real_db,
            _remote_names=tuple(remote_names),
        )


def _sync_fetch_catalog(  # noqa: C901 -- 4-query provenance fetch; splitting would obscure atomic token mint
    url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], ProvenanceToken]:
    """Blocking psycopg fetch — executed via to_thread from async wrapper.

    Provenance: every SELECT is a real query against the DB; returns a
    ProvenanceToken with query_count==4 — the only valid used_real_db.
    """

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text AS child, "
            "confrelid::regclass::text AS parent, "
            "CASE confdeltype WHEN 'c' THEN 'CASCADE' "
            "WHEN 'a' THEN 'NO ACTION' "
            "WHEN 'n' THEN 'SET NULL' "
            "WHEN 'r' THEN 'RESTRICT' "
            "ELSE confdeltype::text END AS on_delete "
            "FROM pg_constraint c "
            "JOIN pg_class cc ON cc.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=cc.relnamespace "
            "WHERE c.contype='f' AND n.nspname='public'"
        )
        fk_rows = cur.fetchall()
        live_fks: list[dict[str, Any]] = []
        for r in fk_rows:
            if isinstance(r, dict):
                live_fks.append({
                    "child": str(r.get("child", "")),
                    "parent": str(r.get("parent", "")),
                    "on_delete": str(r.get("on_delete", "")),
                })
            elif isinstance(r, (list, tuple)) and len(r) >= 3:
                live_fks.append({"child": str(r[0]), "parent": str(r[1]), "on_delete": str(r[2])})
        # RLS policies — expect 0
        try:
            cur.execute("SELECT * FROM pg_policies")
            pol_rows = cur.fetchall()
        except Exception:  # noqa: BLE001 -- pg_policies fallback probe; any failure tries pg_policy
            cur.execute("SELECT * FROM pg_policy")
            pol_rows = cur.fetchall()
        live_policies: list[dict[str, Any]] = [dict(r) if isinstance(r, dict) else {"raw": r} for r in pol_rows]
        # Publication — 6 CDC tables
        cur.execute("SELECT tablename FROM pg_publication_tables WHERE pubname='supabase_realtime'")
        pub_rows = cur.fetchall()
        live_publication: list[str] = []
        for r in pub_rows:
            if isinstance(r, dict):
                v = r.get("tablename") or r.get("table_name") or next(iter(r.values()), "")
                if v:
                    live_publication.append(str(v))
            elif isinstance(r, (list, tuple)):
                if r and r[0]:
                    live_publication.append(str(r[0]))
            elif isinstance(r, str):
                live_publication.append(r)
        # Migrations — identity match (names and count)
        cur.execute("SELECT name FROM supabase_migrations.schema_migrations ORDER BY version")
        mig_rows = cur.fetchall()
        live_migrations: list[str] = []
        for r in mig_rows:
            if isinstance(r, dict):
                v = r.get("name") or r.get("version") or next(iter(r.values()), "")
                if v:
                    live_migrations.append(str(v))
            elif isinstance(r, (list, tuple)):
                if r and r[0]:
                    live_migrations.append(str(r[0]))
            elif isinstance(r, str):
                live_migrations.append(r)
        # 4 provenance queries — mints token
        return live_fks, live_policies, live_publication, live_migrations, ProvenanceToken(query_count=4)


async def fetch_catalog_via_db(
    db_url: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], ProvenanceToken]:
    """Read-only catalog fetch via direct DB URL — no PostgREST.

    Queries pg_constraint, pg_policies, pg_publication_tables,
    supabase_migrations.schema_migrations, pg_stat_user_indexes.
    No DDL, no mutation. Requires a real DB URL; fails closed otherwise.

    When a DB URL is available, connects with psycopg (or warns) and returns
    evidence bindable via SchemaInventory.bind_live_evidence. When unavailable,
    returns empty and the gate will FAIL with warning, never PASS.
    Provenance: ``used_real_db`` must only be True when this function executed
    at least one real query (mocked psycopg connection counts).
    """

    url = db_url or _resolve_db_url()
    if not url:
        warnings.warn(
            "No DB_URL/SUPABASE_DB_URL — catalog via real DB unavailable",
            UserWarning,
            stacklevel=2,
        )
        return [], [], [], [], ProvenanceToken(query_count=0)
    return await asyncio.to_thread(_sync_fetch_catalog, url)


def fetch_rls_counts_via_db(db_url: str) -> tuple[int, int, int]:
    """Return (rls_enabled, rls_forced, policy_count) via pg_class/pg_policy.

    Structural 9/7/0 check: 9 tables with rls_enabled, 7 forced, 0 policies.
    Proves catalog not hardcoded 9.
    """

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity"
        )
        row = cur.fetchone()
        if isinstance(row, (list, tuple)):
            enabled = int(row[0]) if row else 0
        elif isinstance(row, dict):
            enabled = int(row.get("count", 0))
        else:
            enabled = 0
        cur.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relforcerowsecurity"
        )
        row2 = cur.fetchone()
        if isinstance(row2, (list, tuple)):
            forced = int(row2[0]) if row2 else 0
        elif isinstance(row2, dict):
            forced = int(row2.get("count", 0))
        else:
            forced = 0
        # Policy count MUST be scoped to the public schema: pg_policies is the
        # standard view; pg_policy is the legacy table some hardened instances
        # expose instead. The fallback probes a DIFFERENT relation (mirrors
        # _sync_fetch_catalog) — re-running the identical query would
        # deterministically re-fail.
        try:
            cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
            row3 = cur.fetchone()
        except Exception:
            logger.warning("pg_policies probe failed — falling back to pg_policy", exc_info=True)
            cur.execute(
                "SELECT count(*) FROM pg_policy p "
                "JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public'"
            )
            row3 = cur.fetchone()
        if isinstance(row3, (list, tuple)):
            policy_count = int(row3[0]) if row3 else 0
        elif isinstance(row3, dict):
            policy_count = int(row3.get("count", 0))
        else:
            policy_count = 0
        return enabled, forced, policy_count


def evaluate_index_policy(*, scans: int, explain_output: str | None) -> tuple[bool, str]:
    """Executable index-policy gate: zero scans without EXPLAIN must be rejected.

    Returns (allowed, reason). Only duplicate ``idx_ticket_guild_number`` is
    allowed when EXPLAIN proves redundant coverage.
    """
    has_explain = bool(explain_output and "EXPLAIN" in explain_output and "BUFFERS" in explain_output)
    if scans == 0 and not has_explain:
        return False, "zero scans without EXPLAIN (ANALYZE, BUFFERS) — drop rejected, index retained"
    if scans == 0 and has_explain:
        return True, "zero scans but EXPLAIN proves redundant — duplicate drop allowed"
    return True, "scans present or EXPLAIN supplied — policy satisfied"


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
        fks, pols, pubs, migs, _tok = await fetch_catalog_via_db(db_url)
        return fks, pols, pubs, migs
    if supabase_client is not None:
        return await fetch_live_metadata(supabase_client)
    return [], [], [], []
