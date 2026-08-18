"""RED: repair coordinator contract — single eligibility, stale/missing/future-date fails closed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.models.ticket import IntegrityEvidence


def test_evaluate_repair_eligibility_single_path() -> None:
    """All repair entry points MUST share one fail-closed eligibility function."""
    from bot.services import ticket_service as svc
    from bot.services.ticket_repair import evaluate_repair_eligibility

    # Canonical import must be the single source; TicketService must re-export same object.
    assert evaluate_repair_eligibility is svc.evaluate_repair_eligibility


def test_integrity_evidence_stale_fails_closed() -> None:
    """Stale channel-absent observation MUST NOT corroborate (fail closed)."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    stale = datetime(2020, 1, 1, tzinfo=UTC)
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=stale,
    )
    assert evidence.corroborated is None
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=evidence.corroborated) == (
        "skipped",
        "evidence_unresolved",
    )


def test_integrity_evidence_missing_fails_closed() -> None:
    """Missing channel existence (None) MUST be unresolved, never corroborated."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=None,
    )
    assert evidence.corroborated is None
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=evidence.corroborated) == (
        "skipped",
        "evidence_unresolved",
    )


def test_integrity_evidence_future_date_fails_closed() -> None:
    """Future-dated observation MUST be unresolved (fail closed)."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    future = datetime.now(UTC) + timedelta(days=1)
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=future,
    )
    assert evidence.corroborated is None
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=evidence.corroborated) == (
        "skipped",
        "evidence_unresolved",
    )


def test_evaluate_repair_eligibility_gate_unresolved() -> None:
    """Unresolved preflight MUST fail closed with gate_unresolved."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    fresh = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
    )
    assert fresh.corroborated is True
    assert evaluate_repair_eligibility(preflight_allows=False, corroborated=fresh.corroborated) == (
        "skipped",
        "gate_unresolved",
    )


def test_evaluate_repair_eligibility_corroborated_allows_mutation() -> None:
    """Corroborated evidence with resolved preflight MUST allow mutation (None)."""
    from bot.services.ticket_repair import evaluate_repair_eligibility

    fresh = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
    )
    assert fresh.corroborated is True
    assert evaluate_repair_eligibility(preflight_allows=True, corroborated=fresh.corroborated) is None
