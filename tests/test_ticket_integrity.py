"""Focused tests for read-only ticket integrity preflight contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bot.config import INTEGRITY_BACKOFF_SECONDS, INTEGRITY_BATCH_SIZE, INTEGRITY_MAX_BACKOFF_SECONDS
from bot.models.ticket import RepairResult
from bot.services.integrity_report import MigrationParityEvidence, evaluate_preflight


def _compatible_parity() -> MigrationParityEvidence:
    """Return fresh-looking parity evidence for the resolved scenario."""
    return MigrationParityEvidence(
        filename_matches=True,
        schema_objects_match=True,
        applied=True,
    )


def test_preflight_resolves_only_with_complete_fresh_evidence() -> None:
    """Compatible parity, mode, drift, and persisted evidence resolve G.2."""
    result = evaluate_preflight(
        migration=_compatible_parity(),
        deployment_mode="supabase_transaction",
        schema_drift_detected=False,
        evidence_persisted=True,
    )

    assert result.status == "resolved"
    assert result.repair_activation_allowed is True
    assert result.reasons == ()


def test_migration_parity_reports_compatible_or_incompatible() -> None:
    """Parity evidence exposes the database contract's explicit status."""
    assert _compatible_parity().status == "compatible"
    assert MigrationParityEvidence(False, True, True).status == "incompatible"


@pytest.mark.parametrize(
    ("migration", "deployment_mode", "schema_drift_detected", "evidence_persisted"),
    [
        (MigrationParityEvidence(False, True, True), "supabase_transaction", False, True),
        (MigrationParityEvidence(True, False, True), "supabase_transaction", False, True),
        (MigrationParityEvidence(True, True, False), "supabase_transaction", False, True),
        (_compatible_parity(), "unsupported", False, True),
        (_compatible_parity(), "supabase_transaction", True, True),
        (_compatible_parity(), "supabase_transaction", False, False),
    ],
)
def test_preflight_keeps_gate_unresolved_for_incomplete_evidence(
    migration: MigrationParityEvidence,
    deployment_mode: str,
    schema_drift_detected: bool,
    evidence_persisted: bool,
) -> None:
    """Any missing/incompatible prerequisite blocks repair activation."""
    result = evaluate_preflight(
        migration=migration,
        deployment_mode=deployment_mode,
        schema_drift_detected=schema_drift_detected,
        evidence_persisted=evidence_persisted,
    )

    assert result.status == "gate_unresolved"
    assert result.repair_activation_allowed is False
    assert result.reasons


def test_preflight_is_read_only_and_reports_all_failed_prerequisites() -> None:
    """Preflight produces evidence only and does not mutate supplied parity."""
    parity = MigrationParityEvidence(False, False, False)
    result = evaluate_preflight(
        migration=parity,
        deployment_mode="unsupported",
        schema_drift_detected=True,
        evidence_persisted=False,
    )

    assert parity == MigrationParityEvidence(False, False, False)
    assert result.reasons == (
        "migration_filename_mismatch",
        "migration_schema_mismatch",
        "migration_not_applied",
        "unsupported_deployment_mode",
        "schema_drift_detected",
        "fresh_evidence_missing",
    )


def test_integrity_bounds_are_finite_and_non_negative() -> None:
    """Only bounded sweep constants are exposed for later work units."""
    assert 0 < INTEGRITY_BATCH_SIZE <= 50
    assert 0 <= INTEGRITY_BACKOFF_SECONDS <= INTEGRITY_MAX_BACKOFF_SECONDS
    assert 0 <= INTEGRITY_MAX_BACKOFF_SECONDS <= 60


def test_repair_result_rejects_invalid_combinations_or_missing_evidence() -> None:
    for value in ("close/already_closed", "close/skipped", "close/error", "no_op/repaired", "close/repaired"):
        with pytest.raises(ValueError):
            action, outcome = value.split("/")
            RepairResult("t1", "g1", action, outcome, None, None, datetime(2026, 7, 17, tzinfo=UTC))
