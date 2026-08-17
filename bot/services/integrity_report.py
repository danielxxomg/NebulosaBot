"""Read-only deployment and migration evidence for ticket integrity repair."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bot.config import INTEGRITY_EVIDENCE_FRESHNESS_SECONDS

SUPPORTED_DEPLOYMENT_MODES = frozenset(
    {
        "postgres",
        "postgres_direct",
        "supabase",
        "supabase_session",
        "supabase_transaction",
    }
)

# Realtime publication tables verified in the live 2026-08-11 read-only probe.
REQUIRED_REALTIME_PUBLICATION = frozenset({"guild", "greeting_config", "ticket", "ticket_note"})


@dataclass(frozen=True, slots=True)
class MigrationParityEvidence:
    """Immutable parity facts collected from disk and production evidence."""

    filename_matches: bool
    schema_objects_match: bool
    applied: bool

    @property
    def compatible(self) -> bool:
        """Return whether migration 015 can be relied on by later work."""
        return self.filename_matches and self.schema_objects_match and self.applied

    @property
    def status(self) -> str:
        """Return the parity gate value required by the migration contract."""
        return "compatible" if self.compatible else "incompatible"


@dataclass(frozen=True, slots=True)
class IntegrityPreflight:
    """Read-only G.2 gate result; it never performs ticket mutations."""

    status: str
    migration: MigrationParityEvidence
    deployment_mode: str | None
    schema_drift_detected: bool | None
    evidence_persisted: bool
    reasons: tuple[str, ...]

    @property
    def repair_activation_allowed(self) -> bool:
        """Return whether a later repair unit may activate its mutation gate."""
        return self.status == "resolved" and self.evidence_persisted


def evaluate_preflight(
    *,
    migration: MigrationParityEvidence,
    deployment_mode: str | None,
    schema_drift_detected: bool | None,
    evidence_persisted: bool = False,
) -> IntegrityPreflight:
    """Evaluate G.2 prerequisites without reading or mutating ticket rows.

    Fresh evidence must be explicitly persisted before this function can
    return a resolved activation gate. Missing evidence therefore defaults to
    ``gate_unresolved`` even when the other prerequisites are compatible.
    """
    reasons: list[str] = []
    if not migration.filename_matches:
        reasons.append("migration_filename_mismatch")
    if not migration.schema_objects_match:
        reasons.append("migration_schema_mismatch")
    if not migration.applied:
        reasons.append("migration_not_applied")
    if deployment_mode not in SUPPORTED_DEPLOYMENT_MODES:
        reasons.append("unsupported_deployment_mode")
    if schema_drift_detected is not False:
        reasons.append("schema_drift_detected")
    if not evidence_persisted:
        reasons.append("fresh_evidence_missing")

    return IntegrityPreflight(
        status="resolved" if not reasons else "gate_unresolved",
        migration=migration,
        deployment_mode=deployment_mode,
        schema_drift_detected=schema_drift_detected,
        evidence_persisted=evidence_persisted,
        reasons=tuple(reasons),
    )


run_integrity_preflight = evaluate_preflight


@dataclass(frozen=True, slots=True)
class LivePreflightResult:
    """Read-only result of the live schema/deployment preflight half.

    Resolves only from verified, fresh, read-only live evidence (project
    status, migration 015 applied, required indexes, Realtime publication).
    The optional ``active_rows_channel_id_non_null`` diagnostic is
    informational only and does NOT participate in readiness.
    ``schema_ready`` proves schema readiness ONLY — it never proves Discord
    channels exist and never mutates tickets.
    """

    status: str
    schema_ready: bool
    reasons: tuple[str, ...]

    @property
    def repair_activation_allowed(self) -> bool:
        """Return whether the schema half of the repair gate is open."""
        return self.status == "resolved" and self.schema_ready


def evaluate_live_preflight(**evidence: object) -> LivePreflightResult:
    """Evaluate verified read-only live evidence without mutating tickets.

    Accepts the schema/deployment facts recovered on 2026-08-11. Missing or
    stale facts fail closed to ``gate_unresolved``. Security-advisor WARN and
    INFO findings are explicit non-goals and never block schema readiness.

    Args:
        **evidence: Verified live facts; ``observed_at`` drives freshness.

    Returns:
        A :class:`LivePreflightResult`; never a mutation.
    """
    reasons: list[str] = []
    observed_at = evidence.get("observed_at")
    if isinstance(observed_at, str):
        try:
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError:
            observed_at = None
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        reasons.append("fresh_evidence_missing")
    elif datetime.now(UTC) - observed_at > timedelta(seconds=INTEGRITY_EVIDENCE_FRESHNESS_SECONDS):
        reasons.append("stale_evidence")
    elif datetime.now(UTC) - observed_at < timedelta(0):
        # Future-dated observation fails closed on the same freshness boundary
        # as per-ticket evidence (never trusted as fresh).
        reasons.append("future_evidence")

    if evidence.get("project_status") != "ACTIVE_HEALTHY":
        reasons.append("project_not_healthy")
    if evidence.get("migration_015_applied") is not True:
        reasons.append("migration_015_not_applied")
    if evidence.get("close_reason_nullable") is not True:
        reasons.append("close_reason_not_nullable")
    if evidence.get("required_indexes_present") is not True:
        reasons.append("required_indexes_missing")

    realtime_covers = evidence.get("realtime_publication_covers") or ()
    if not isinstance(realtime_covers, (list, tuple, set, frozenset)):
        realtime_covers = ()
    if not REQUIRED_REALTIME_PUBLICATION.issubset(set(realtime_covers)):
        reasons.append("realtime_publication_incomplete")
    # ``active_rows_channel_id_non_null`` is informational diagnostic context
    # ONLY: it MAY be reported alongside the schema facts but MUST NOT gate
    # readiness or authorize repair (spec database-layer). It is intentionally
    # not consumed here, so any value (None, 0, 1, 3, …) leaves readiness
    # determined solely by the required schema/deployment facts above.

    return LivePreflightResult(
        status="resolved" if not reasons else "gate_unresolved",
        schema_ready=not reasons,
        reasons=tuple(reasons),
    )


__all__ = [
    "REQUIRED_REALTIME_PUBLICATION",
    "SUPPORTED_DEPLOYMENT_MODES",
    "IntegrityPreflight",
    "LivePreflightResult",
    "MigrationParityEvidence",
    "evaluate_live_preflight",
    "evaluate_preflight",
    "run_integrity_preflight",
]
