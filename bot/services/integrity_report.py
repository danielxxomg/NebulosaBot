"""Read-only deployment and migration evidence for ticket integrity repair."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_DEPLOYMENT_MODES = frozenset(
    {
        "postgres",
        "postgres_direct",
        "supabase",
        "supabase_session",
        "supabase_transaction",
    }
)


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

__all__ = [
    "SUPPORTED_DEPLOYMENT_MODES",
    "IntegrityPreflight",
    "MigrationParityEvidence",
    "evaluate_preflight",
    "run_integrity_preflight",
]
