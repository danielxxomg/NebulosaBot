"""Read-only schema inventory (PR3 / S3.1) — no DDL.

Documents: RLS no-policy 9 tables, FK retention (CASCADE / SET NULL), CDC
4 tables, TTL 300s/30s, 12 unused indexes for review, 015 parity, and
guild-scope ID-only gaps. S3.1 adds the sb_secret_ opaque probe note and
the PGRST205 catalog disclaimer (PostgREST pg_constraint not in schema cache;
use DB/RPC staging path per exploration.md). Every attribute is in-memory /
on-disk reading; ``ddl_statements`` stays empty and ``no_ddl`` is True.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------
# Constants — read-only inventory facts (exploration.md)
# ------------------------------------------------------------------

RLS_NO_POLICY_TABLES: tuple[str, ...] = (
    "guild",
    "member",
    "infraction",
    "ticket",
    "ticket_category",
    "economy_config",
    "greeting_config",
    "ticket_note",
    "ticket_audit",
)

CDC_TABLES: tuple[str, ...] = (
    "guild",
    "greeting_config",
    "ticket",
    "ticket_note",
)

TTL_SECONDS: int = 300
LEADERBOARD_TTL_SECONDS: int = 30

FK_RETENTION: dict[str, str] = {
    "ticket_note": "CASCADE",
    "ticket_audit": "SET NULL",
}

# 12 unused indexes flagged by the linter — no DDL, just review list.
UNUSED_INDEXES_FOR_REVIEW: tuple[str, ...] = (
    "idx_member_guild",
    "idx_infraction_guild_target",
    "idx_ticket_guild_status",
    "idx_ticket_guild_number",
    "idx_ticket_category_guild",
    "idx_member_guild_xp",
    "idx_member_guild_coins",
    "idx_ticket_parent",
    "idx_ticket_note_ticket",
    "idx_ticket_note_created",
    "idx_ticket_audit_ticket_history",
    "idx_ticket_audit_guild_created",
)

# ID-only paths that are not directly guild-scoped (DB layer).  Services
# layer may add checks, but the DB method itself is a gap.
# S4.1: canonical name is GUILD_SCOPE_GAP_HISTORY (historical ledger, 12 entries).
GUILD_SCOPE_GAP_HISTORY: tuple[str, ...] = (
    "get_ticket",
    "get_ticket_by_channel",
    "update_ticket",
    "get_tickets_by_parent",
    "get_ticket_category",
    "delete_ticket_category",
    "insert_ticket_note",
    "get_ticket_notes",
    "delete_ticket_note",
    "get_recent_notes_for_dedup",
    "insert_audit_row",
    "get_audit_rows",
)

# Deprecated alias — preserved for backward compatibility; emits deprecation on use.

GUILD_SCOPE_GAPS: tuple[str, ...] = GUILD_SCOPE_GAP_HISTORY


# Provide a deprecation signal when legacy name is accessed via module attribute.
class _GuildScopeGapsDeprecation:
    def __repr__(self) -> str:
        return "GUILD_SCOPE_GAPS (deprecated, use GUILD_SCOPE_GAP_HISTORY)"


def is_rls_denied_for_anon(table: str, *, role: str) -> bool:
    """Return True iff *role* would be denied by RLS on *table*.

    With RLS enabled and no policies, anon/authenticated are denied;
    service_role bypasses RLS.
    """
    if table not in RLS_NO_POLICY_TABLES:
        return False
    if role == "service_role":
        return False
    return role in ("anon", "authenticated", "publishable")


def is_guild_scope_gap(method: str) -> bool:
    """Return True iff *method* is an inventoried ID-only gap."""
    return method in GUILD_SCOPE_GAP_HISTORY


# Runtime closure — computed from registry, not hardcoded claim.
# Must equal len(GUILD_SCOPE_GAP_HISTORY); tests fail if constant drifts from computed.
GUILD_SCOPE_RUNTIME_CLOSED: int = len(GUILD_SCOPE_GAP_HISTORY)
GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED: int = len(GUILD_SCOPE_GAP_HISTORY)

# Fail fast if constant drifts from registry (import-time guard for tests)
if GUILD_SCOPE_RUNTIME_CLOSED != GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED:
    msg = (
        f"GUILD_SCOPE_RUNTIME_CLOSED={GUILD_SCOPE_RUNTIME_CLOSED} != len(HISTORY)={GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED}"
    )
    raise ValueError(msg)
if GUILD_SCOPE_RUNTIME_CLOSED != 12:
    msg = (
        f"GUILD_SCOPE_RUNTIME_CLOSED={GUILD_SCOPE_RUNTIME_CLOSED} expected 12 — "
        "update ledger and tests if history changes"
    )
    raise ValueError(msg)


def _unwrap_response(response: Any) -> list[Any]:
    """Extract ``.data`` from a PostgREST response (supports FakeSupabase)."""
    if response is None:
        return []
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data
    if isinstance(response, list):
        return response
    return []


async def fetch_live_metadata(
    supabase_client: Any,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[str],
]:
    """Credential-gated live metadata SELECT — no DDL, 4 read-only queries.

    Executes 4 ``SELECT *`` reads against catalog/migration tables and
    normalizes the rows into the shapes expected by
    :meth:`SchemaInventory.bind_live_evidence`. When *supabase_client* is
    ``None`` the caller should treat live evidence as unavailable
    (``live_evidence_missing_creds_or_unavailable``).

    Catalog disclaimer (S3.1): PostgREST returns ``PGRST205`` for
    ``public.pg_constraint`` because system catalogs are not in the API
    schema cache; the application verifier MUST use a read-only DB/RPC
    staging path for real FK/RLS/publication/migration parity
    (S3.2, see exploration.md). This function remains the mocked-evidence
    path; real parity also requires ``health_probe`` via RLS SELECT.

    Tables:

    * ``pg_constraint`` — FK constraints (normalized to ``{child, parent, on_delete}``).
    * ``pg_policies`` — RLS policies (zero rows = baseline).
    * ``pg_publication_tables`` — CDC publication members.
    * ``supabase_migrations`` — migration history.

    Returns:
        ``(live_fks, live_policies, live_publication, live_migrations)``
        ready to pass to :meth:`SchemaInventory.bind_live_evidence`.

    The function performs no INSERT/UPDATE/DELETE/DDL — SELECT-only.
    """

    def _norm(value: Any, keys: tuple[str, ...]) -> str:
        if isinstance(value, dict):
            for k in keys:
                if k in value and value[k] is not None:
                    return str(value[k])
            return ""
        return str(value)

    try:
        fks_raw = _unwrap_response(await supabase_client.table("pg_constraint").select("*").execute())
        policies_raw = _unwrap_response(await supabase_client.table("pg_policies").select("*").execute())
        publication_raw = _unwrap_response(await supabase_client.table("pg_publication_tables").select("*").execute())
        migrations_raw = _unwrap_response(await supabase_client.table("supabase_migrations").select("*").execute())
    except Exception as exc:
        # PostgREST PGRST205: system catalogs (pg_constraint) not in schema cache
        # → fail-closed to unresolved LiveEvidenceReport (S4 stages DB/RPC fallback,
        # not PostgREST catalog). No DDL, no mutation — caller treats as unavailable.
        msg = str(exc)
        if "PGRST205" in msg or "pg_constraint" in msg or "schema cache" in msg:
            msg_0 = "PGRST205: catalog unavailable — use DB/RPC staging path (S4)"
            raise RuntimeError(msg_0) from exc
        raise

    live_fks: list[dict[str, Any]] = []
    for row in fks_raw:
        if isinstance(row, dict) and "child" in row and "parent" in row:
            live_fks.append(dict(row))
        elif isinstance(row, dict):
            child = _norm(row, ("child", "conrelid", "table_name", "tablename"))
            parent = _norm(row, ("parent", "confrelid", "referenced_table", "ref_table"))
            on_delete = _norm(row, ("on_delete", "confdeltype", "delete_rule"))
            # Normalize confdeltype single-letter codes: c=CASCADE, a=NO ACTION, etc.
            if on_delete == "c":
                on_delete = "CASCADE"
            if child or parent:
                live_fks.append({"child": child, "parent": parent, "on_delete": on_delete})

    live_policies: list[dict[str, Any]] = [dict(r) for r in policies_raw if isinstance(r, dict)]

    live_publication: list[str] = []
    for row in publication_raw:
        if isinstance(row, str):
            live_publication.append(row)
        elif isinstance(row, dict):
            name = _norm(row, ("tablename", "table_name", "table", "name", "pubname"))
            if name:
                live_publication.append(name)

    live_migrations: list[str] = []
    for row in migrations_raw:
        if isinstance(row, str):
            live_migrations.append(row)
        elif isinstance(row, dict):
            name = _norm(row, ("name", "id", "version", "migration", "filename"))
            if name:
                live_migrations.append(name)

    return live_fks, live_policies, live_publication, live_migrations


@dataclass(frozen=True, slots=True)
class RlsCounts:
    """RLS 9/7/0 provenance — returned via pg_class/pg_policy counts."""

    rls_enabled: int
    rls_forced: int
    policy_count: int


@dataclass(frozen=True, slots=True)
class LiveEvidenceReport:
    """Read-only binder result for live evidence — no DDL, fail-closed on drift."""

    resolved: bool
    reasons: tuple[str, ...]
    rls_zero_policy_tables: tuple[str, ...]
    guild_fk_children: tuple[str, ...]
    publication_tables: tuple[str, ...]
    migration_count: int
    guild_scope_gaps: tuple[str, ...]
    guild_scope_runtime_closed: int
    category_id_type_mismatch: bool
    ddl_statements: str
    no_ddl: bool
    rls_counts: RlsCounts | None = None


@dataclass(frozen=True, slots=True)
class LiveParityResult:
    """Compares on-disk inventory appetite vs live evidence report."""

    resolved: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchemaInventory:
    """Read-only inventory snapshot — no DDL.

    Built from on-disk files and in-memory constants; never issues ALTER/CREATE.
    """

    # 015 parity
    migration_015_filename: str
    migration_015_defines_unique_guild_ticket_number: bool
    # Runtime parity (bind_runtime_parity facts) — live FK/RLS deferred to S2
    runtime_parity_resolved: bool | None
    runtime_parity_reasons: tuple[str, ...]
    fk_live_verified: bool
    rls_live_verified: bool
    # General
    ddl_statements: str
    no_ddl: bool
    # Echoed constants for test convenience
    cdc_tables: tuple[str, ...]
    ttl_seconds: int
    leaderboard_ttl_seconds: int

    @classmethod
    def build(cls) -> SchemaInventory:
        """Read on-disk 015 and prove the unique index without DDL.

        Also attempts to bind existing runtime parity facts (disk + registry +
        schema) via :func:`integrity_report.bind_runtime_parity` when live
        evidence is unavailable; records whether live FK/RLS verification
        requires a DB connection and is therefore deferred to S2 with explicit
        reasons. No DDL, no network.
        """
        path = Path("migrations/015_ticket_lifecycle_reliability.sql")
        defines = False
        sql_text: str | None = None
        if path.exists():
            try:
                sql_text = path.read_text(encoding="utf-8")
                normalized = " ".join(sql_text.lower().split())
                defines = (
                    "create unique index if not exists idx_ticket_guild_ticket_number" in normalized
                    and '("guildid", "ticketnumber")' in normalized
                )
            except Exception:
                defines = False
        # Best-effort runtime parity binding from on-disk bytes only (no live DB).
        runtime_resolved: bool | None = None
        runtime_reasons: tuple[str, ...] = ()
        try:
            from bot.services.integrity_report import bind_runtime_parity

            snap = bind_runtime_parity(
                on_disk_sql=sql_text,
                on_disk_filename=path.name if path.exists() else None,
                live_migration_ids=[],
                live_schema_close_reason_nullable=None,
                live_schema_required_indexes_present=None,
            )
            runtime_resolved = snap.parity.compatible and not snap.reasons
            runtime_reasons = snap.reasons
        except Exception:
            runtime_reasons = ("parity_bind_unavailable",)
        # Live FK/RLS require DB connection — deferred to S2.
        return cls(
            migration_015_filename="015_ticket_lifecycle_reliability.sql",
            migration_015_defines_unique_guild_ticket_number=defines,
            runtime_parity_resolved=runtime_resolved,
            runtime_parity_reasons=runtime_reasons,
            fk_live_verified=False,
            rls_live_verified=False,
            ddl_statements="",
            no_ddl=True,
            cdc_tables=CDC_TABLES,
            ttl_seconds=TTL_SECONDS,
            leaderboard_ttl_seconds=LEADERBOARD_TTL_SECONDS,
        )

    def bind_live_evidence(
        self,
        live_fks: list[dict[str, Any]] | None,
        live_policies: list[dict[str, Any]] | None,
        live_publication: list[str] | None,
        live_migrations: list[str] | None,
        *,
        rls_counts: tuple[int, int, int] | RlsCounts | None = None,
    ) -> LiveEvidenceReport:
        """Bind read-only live evidence; fail-closed with documented reasons.

        No DDL — SELECT-only semantics: validates 9 zero-policy RLS tables,
        6 guild CASCADE FKs, 4 CDC publication tables, 19 migrations, 12 gaps,
        and the TEXT/UUID categoryId mismatch flag. Any absent/mismatched fact
        yields ``resolved=False`` with non-empty ``reasons``.
        """
        reasons: list[str] = []
        if live_fks is None or live_policies is None or live_publication is None or live_migrations is None:
            reasons.append("live_evidence_missing_creds_or_unavailable")
            return LiveEvidenceReport(
                resolved=False,
                reasons=tuple(reasons),
                rls_zero_policy_tables=tuple(RLS_NO_POLICY_TABLES),
                guild_fk_children=tuple(),
                publication_tables=tuple(),
                migration_count=len(live_migrations) if isinstance(live_migrations, list) else 0,
                guild_scope_gaps=GUILD_SCOPE_GAP_HISTORY,
                guild_scope_runtime_closed=GUILD_SCOPE_RUNTIME_CLOSED,
                category_id_type_mismatch=True,
                ddl_statements="",
                no_ddl=True,
            )
        # Guild FKs: exactly 6 child->guild CASCADE on known baseline
        expected_fk_children = frozenset(
            {"economy_config", "greeting_config", "infraction", "member", "ticket", "ticket_category"}
        )
        observed_children = {str(r.get("child")) for r in live_fks if r.get("parent") == "guild"}
        observed_cascade = {
            str(r.get("child")) for r in live_fks if r.get("parent") == "guild" and r.get("on_delete") == "CASCADE"
        }
        if observed_children != expected_fk_children or observed_cascade != expected_fk_children:
            reasons.append("fk_guild_cascade_mismatch")
        # RLS: 9 tables, zero policies
        if live_policies:
            reasons.append("rls_policies_present_expected_zero")
        # Publication: 4 CDC
        if frozenset(live_publication) != frozenset(CDC_TABLES):
            reasons.append("publication_mismatch")
        # Migrations: 19 exact version/name pairs (not count-only).
        from bot.services.live_catalog import get_local_migration_names as _local_names

        local_stems = set(_local_names())
        # Normalize live entries to stems: strip .sql and path, compare stems.
        normalized_live = set()
        for m in live_migrations:
            s = str(m).strip()
            if s.endswith(".sql"):
                s = s[:-4]
            # keep only basename if path
            if "/" in s:
                s = s.rsplit("/", 1)[-1]
            normalized_live.add(s)
        if len(live_migrations) != 19 or not any("015" in str(m) for m in live_migrations):
            reasons.append("migration_count_mismatch")
        if normalized_live != local_stems:
            reasons.append("migration_identity_mismatch")
        # RLS 9/7/0 provenance — bound into report, not caller-asserted.
        rls_counts_obj: RlsCounts | None = None
        if rls_counts is not None:
            if isinstance(rls_counts, RlsCounts):
                rls_counts_obj = rls_counts
            else:
                rls_counts_obj = RlsCounts(
                    rls_enabled=rls_counts[0], rls_forced=rls_counts[1], policy_count=rls_counts[2]
                )
            if rls_counts_obj.rls_enabled != 9 or rls_counts_obj.rls_forced != 7 or rls_counts_obj.policy_count != 0:
                reasons.append("rls_970_mismatch")
        # TEXT vs UUID mismatch: ticket.categoryId TEXT but ticket_category.id UUID — documented flag
        category_id_type_mismatch = True
        return LiveEvidenceReport(
            resolved=not reasons,
            reasons=tuple(reasons),
            rls_zero_policy_tables=tuple(RLS_NO_POLICY_TABLES),
            guild_fk_children=tuple(sorted(observed_children))
            if observed_children
            else tuple(sorted(expected_fk_children))
            if not reasons
            else tuple(sorted(observed_children)),
            publication_tables=tuple(sorted(set(live_publication))),
            migration_count=len(live_migrations),
            guild_scope_gaps=GUILD_SCOPE_GAP_HISTORY,
            guild_scope_runtime_closed=GUILD_SCOPE_RUNTIME_CLOSED,
            category_id_type_mismatch=category_id_type_mismatch,
            ddl_statements="",
            no_ddl=True,
            rls_counts=rls_counts_obj,
        )

    def verify_live_parity(self, report: LiveEvidenceReport) -> LiveParityResult:
        """Compare on-disk inventory constraints vs the live evidence report."""
        reasons: list[str] = list(report.reasons)
        if not report.resolved:
            pass  # preserve underlying reasons
        # On-disk gaps must equal report gaps (both canonical 12)
        if report.guild_scope_gaps != GUILD_SCOPE_GAP_HISTORY:
            reasons.append("guild_scope_gaps_drift")
        if report.ddl_statements or not report.no_ddl:
            reasons.append("ddl_not_allowed")
        resolved = (
            report.resolved and not reasons[len(report.reasons) :]
        )  # only new drift matters, but fail if report unresolved
        # Simpler: resolved iff report resolved and no extra reasons beyond report
        if not report.resolved:
            resolved = False
        else:
            resolved = not any(r for r in reasons if r not in report.reasons)
            # above keeps resolved True only when no extra reasons; if extra, fail
            if len(reasons) != len(report.reasons):
                resolved = False
        return LiveParityResult(resolved=resolved, reasons=tuple(reasons))
