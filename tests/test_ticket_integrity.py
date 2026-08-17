"""Focused tests for read-only ticket integrity preflight contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


# ==========================================================================
# Live evidence preflight (product-artifact-audit PR1, task 1.4)
# ==========================================================================


def _live_schema_evidence() -> dict:
    """Return the verified 2026-08-11 read-only schema/deployment facts.

    ``observed_at`` is a fresh observation time so the schema facts can be
    validated against the configured freshness window; the stale/missing
    scenarios override it explicitly.
    """
    return {
        "project_status": "ACTIVE_HEALTHY",
        "migration_015_applied": True,
        "close_reason_nullable": True,
        "required_indexes_present": True,
        "realtime_publication_covers": ["guild", "greeting_config", "ticket", "ticket_note"],
        "active_rows_channel_id_non_null": 3,
        "evidence_verified_at": "2026-08-11T00:00:00+00:00",
        "observed_at": datetime.now(UTC).isoformat(),
    }


def test_live_schema_evidence_resolves_preflight_half() -> None:
    """Verified fresh live evidence MUST resolve the schema/deployment half."""
    from bot.services.integrity_report import evaluate_live_preflight

    result = evaluate_live_preflight(**_live_schema_evidence())

    assert result.status == "resolved"
    assert result.schema_ready is True
    assert result.reasons == ()


def test_stale_live_evidence_fails_closed() -> None:
    """Stale or missing live evidence MUST keep the preflight unresolved."""
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    evidence["observed_at"] = "2020-01-01T00:00:00+00:00"

    result = evaluate_live_preflight(**evidence)

    assert result.status == "gate_unresolved"
    assert result.schema_ready is False
    assert result.reasons


def test_future_dated_live_evidence_fails_closed() -> None:
    """Future-dated live preflight evidence MUST fail closed (never trusted fresh)."""
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    future = datetime.now(UTC) + timedelta(days=2)
    evidence["observed_at"] = future.isoformat()

    result = evaluate_live_preflight(**evidence)

    assert result.status == "gate_unresolved"
    assert result.schema_ready is False
    assert "future_evidence" in result.reasons


def test_missing_live_evidence_fails_closed() -> None:
    """Missing project or migration evidence MUST fail closed."""
    from bot.services.integrity_report import evaluate_live_preflight

    result = evaluate_live_preflight()

    assert result.status == "gate_unresolved"
    assert result.schema_ready is False


def test_advisor_findings_do_not_authorize_repair() -> None:
    """Advisor WARN/INFO findings are non-goals and never authorize repair."""
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    evidence["advisor_warns"] = 1
    evidence["advisor_infos"] = 9

    result = evaluate_live_preflight(**evidence)

    assert result.status == "resolved"  # advisor findings do not block schema readiness
    assert result.schema_ready is True


def test_preflight_is_read_only_no_ticket_mutation() -> None:
    """Preflight never writes ticket rows; it only reports schema readiness."""
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    before = dict(evidence)

    result = evaluate_live_preflight(**evidence)

    assert dict(evidence) == before
    assert result.schema_ready is True


@pytest.mark.parametrize("diagnostic_value", [0, 1, 2, 4, 5, 10])
def test_active_rows_diagnostic_value_is_informational_only(diagnostic_value: int) -> None:
    """The optional active-row channel-ID count MUST NOT gate preflight readiness.

    ``active_rows_channel_id_non_null`` is reportable diagnostic context only:
    schema readiness and repair activation MUST be identical whether the count
    is 0, 1, non-3, or the verified 3 — it never blocks (or uniquely permits)
    the gate. A non-3 value resolves exactly like the verified 3 evidence.
    """
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    evidence["active_rows_channel_id_non_null"] = diagnostic_value

    result = evaluate_live_preflight(**evidence)

    assert result.status == "resolved"
    assert result.schema_ready is True
    assert result.reasons == ()
    assert result.repair_activation_allowed is True


def test_active_rows_diagnostic_none_is_informational_only() -> None:
    """A missing/None diagnostic count is also informational: the schema facts
    still resolve readiness without it (it is NOT a required gate input)."""
    from bot.services.integrity_report import evaluate_live_preflight

    evidence = _live_schema_evidence()
    evidence["active_rows_channel_id_non_null"] = None

    result = evaluate_live_preflight(**evidence)

    assert result.status == "resolved"
    assert result.schema_ready is True
    assert result.reasons == ()
    assert result.repair_activation_allowed is True
