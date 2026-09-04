"""Unit tests for bot.models.ticket.Ticket and bot.models.ticket_note.TicketNote.

Covers the ``ticket-model`` spec scenarios for the tickets-subsidiados change:

    - Ticket.from_db_row maps ``parentId`` -> ``parent_id`` (populated + null)
    - Ticket.to_db_dict includes ``"parentId"`` (populated + null)
    - TicketNote.from_db_row maps camelCase DB keys -> snake_case attrs
    - TicketNote.to_db_dict converts back to camelCase keys
    - Round-trip preservation for both dataclasses
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from bot.models.ticket import CloseResult, IntegrityEvidence, RepairResult, Ticket
from bot.models.ticket_note import TicketNote

# ---------------------------------------------------------------------------
# Shared row builder — a valid camelCase Supabase ticket row
# ---------------------------------------------------------------------------


def _ticket_row(**overrides: object) -> dict:
    """Return a minimal valid ticket DB row, applying optional overrides."""
    row: dict = {
        "id": "t-0001",
        "ticketNumber": 7,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-07-01T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-07-01T10:00:00+00:00",
        "parentId": None,
        "subject": None,
        "description": None,
    }
    row.update(overrides)
    return row


# ===========================================================================
# Ticket — field serialization triplets (flat parametrization)
#
# The 21 per-field triplet functions (parent_id / subject+description /
# custom_fields x from_db_row / to_db_dict / round-trip) are consolidated
# into 3 flat parametrized tests. Each pytest.param reproduces its original
# case 1:1 — same construction data, asserts verbatim — with an explicit id;
# the collected count is unchanged (48 → 48).
# ===========================================================================


def _ticket(**overrides: object) -> Ticket:
    """Return a base valid Ticket matching ``_ticket_row`` defaults, with overrides."""
    kwargs: dict = {
        "id": "t-0001",
        "ticket_number": 7,
        "guild_id": "123456789",
        "author_id": "111111111",
        "channel_id": "888888888",
        "status": "open",
        "created_at": datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        "last_activity": datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return Ticket(**kwargs)


# from_db_row: populated rows map camelCase keys; null and missing keys both
# yield None ("missing" = an older row written before Migration 003).
_FROM_DB_ROW_CASES = [
    pytest.param("parent_id", "populated", {"parentId": "parent-uuid-123"}, (), id="parent_id-populated"),
    pytest.param("parent_id", "null", {"parentId": None}, (), id="parent_id-null"),
    pytest.param("parent_id", "missing", {}, ("parentId",), id="parent_id-missing"),
    pytest.param(
        "subject_description",
        "populated",
        {"subject": "Login broken", "description": "Cannot access since Monday"},
        (),
        id="subject_description-populated",
    ),
    pytest.param(
        "subject_description",
        "null",
        {"subject": None, "description": None},
        (),
        id="subject_description-null",
    ),
    pytest.param(
        "subject_description",
        "missing",
        {},
        ("subject", "description"),
        id="subject_description-missing",
    ),
    pytest.param(
        "custom_fields",
        "populated",
        {"customFields": {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}},
        (),
        id="custom_fields-populated",
    ),
    pytest.param("custom_fields", "null", {"customFields": None}, (), id="custom_fields-null"),
    pytest.param("custom_fields", "missing", {}, ("customFields",), id="custom_fields-missing"),
]


@pytest.mark.parametrize(("field", "case", "overrides", "missing_keys"), _FROM_DB_ROW_CASES)
def test_from_db_row_serialization_cases(field: str, case: str, overrides: dict, missing_keys: tuple) -> None:
    """from_db_row MUST map camelCase fields for populated/null/missing rows (asserts verbatim per case)."""
    row = _ticket_row(**overrides)
    for key in missing_keys:
        row.pop(key, None)

    ticket = Ticket.from_db_row(row)

    match field, case:
        case "parent_id", "populated":
            assert ticket.parent_id == "parent-uuid-123"
        case "parent_id", _:
            assert ticket.parent_id is None
        case "subject_description", "populated":
            assert ticket.subject == "Login broken"
            assert ticket.description == "Cannot access since Monday"
        case "subject_description", _:
            assert ticket.subject is None
            assert ticket.description is None
        case "custom_fields", "populated":
            assert ticket.custom_fields == {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}
        case _:
            assert ticket.custom_fields is None


# to_db_dict: populated values serialize to camelCase; None survives as None.
_TO_DB_DICT_CASES = [
    pytest.param("parent_id", "populated", id="parent_id-populated"),
    pytest.param("parent_id", "null", id="parent_id-null"),
    pytest.param("subject_description", "populated", id="subject_description-populated"),
    pytest.param("subject_description", "null", id="subject_description-null"),
    pytest.param("custom_fields", "populated", id="custom_fields-populated"),
    pytest.param("custom_fields", "null", id="custom_fields-null"),
]


@pytest.mark.parametrize(("field", "case"), _TO_DB_DICT_CASES)
def test_to_db_dict_cases(field: str, case: str) -> None:
    """to_db_dict MUST emit camelCase keys with correct values (asserts verbatim per case)."""
    match field, case:
        case "parent_id", "populated":
            ticket = _ticket(id="t-0001", ticket_number=7, channel_id="888888888", parent_id="parent-uuid-123")
            result = ticket.to_db_dict()
            assert result["parentId"] == "parent-uuid-123"
        case "parent_id", _:
            ticket = _ticket(id="t-0002", ticket_number=8, channel_id="888888889", parent_id=None)
            result = ticket.to_db_dict()
            assert "parentId" in result
            assert result["parentId"] is None
        case "subject_description", "populated":
            ticket = _ticket(
                id="t-subject",
                ticket_number=11,
                guild_id="g1",
                author_id="a1",
                channel_id="c1",
                subject="Bug",
                description="Details",
            )
            result = ticket.to_db_dict()
            assert result["subject"] == "Bug"
            assert result["description"] == "Details"
        case "subject_description", _:
            ticket = _ticket(
                id="t-subject-null",
                ticket_number=12,
                guild_id="g1",
                author_id="a1",
                channel_id="c1",
                subject=None,
                description=None,
            )
            result = ticket.to_db_dict()
            assert "subject" in result
            assert result["subject"] is None
            assert "description" in result
            assert result["description"] is None
        case "custom_fields", "populated":
            ticket = _ticket(
                id="t-cf-01",
                ticket_number=20,
                guild_id="g1",
                author_id="a1",
                channel_id="c1",
                custom_fields={"player_nick": "DarkSlayer42"},
            )
            result = ticket.to_db_dict()
            assert result["customFields"] == {"player_nick": "DarkSlayer42"}
        case _:
            ticket = _ticket(
                id="t-cf-02", ticket_number=21, guild_id="g1", author_id="a1", channel_id="c1", custom_fields=None
            )
            result = ticket.to_db_dict()
            assert "customFields" in result
            assert result["customFields"] is None


# Round-trip: values survive from_db_row(to_db_dict(x)); None stays None.
_ROUND_TRIP_CASES = [
    pytest.param("parent_id", "populated", id="parent_id-populated"),
    pytest.param("parent_id", "none", id="parent_id-none"),
    pytest.param("subject_description", "populated", id="subject_description-populated"),
    pytest.param("subject_description", "none", id="subject_description-none"),
    pytest.param("custom_fields", "populated", id="custom_fields-populated"),
    pytest.param("custom_fields", "none", id="custom_fields-none"),
]


@pytest.mark.parametrize(("field", "case"), _ROUND_TRIP_CASES)
def test_ticket_round_trip_cases(field: str, case: str) -> None:
    """Values MUST survive a to_db_dict -> from_db_row round-trip (asserts verbatim per case)."""
    match field, case:
        case "parent_id", "populated":
            ticket = _ticket(
                id="t-rt", ticket_number=9, guild_id="g1", author_id="a1", channel_id="c1", parent_id="parent-rt-uuid"
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.parent_id == "parent-rt-uuid"
            assert rebuilt.id == ticket.id
        case "parent_id", _:
            ticket = _ticket(
                id="t-rt-none", ticket_number=10, guild_id="g1", author_id="a1", channel_id="c1", parent_id=None
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.parent_id is None
        case "subject_description", "populated":
            ticket = _ticket(
                id="t-rt-subj",
                ticket_number=13,
                guild_id="g1",
                author_id="a1",
                channel_id="c1",
                subject="Login broken",
                description="Cannot access since Monday",
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.subject == "Login broken"
            assert rebuilt.description == "Cannot access since Monday"
        case "subject_description", _:
            ticket = _ticket(
                id="t-rt-subj-none",
                ticket_number=14,
                guild_id="g1",
                author_id="a1",
                channel_id="c1",
                subject=None,
                description=None,
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.subject is None
            assert rebuilt.description is None
        case "custom_fields", "populated":
            fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}
            ticket = _ticket(
                id="t-rt-cf", ticket_number=22, guild_id="g1", author_id="a1", channel_id="c1", custom_fields=fields
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.custom_fields == fields
        case _:
            ticket = _ticket(
                id="t-rt-cf-none", ticket_number=23, guild_id="g1", author_id="a1", channel_id="c1", custom_fields=None
            )
            rebuilt = Ticket.from_db_row(ticket.to_db_dict())
            assert rebuilt.custom_fields is None


# ===========================================================================
# TicketNote — camelCase <-> snake_case serialization
#
# TicketNote is imported lazily inside each test so the Ticket tests above
# stay green and the RED signal points precisely at the missing module.
# ===========================================================================


def _note_row(**overrides: object) -> dict:
    """Return a valid camelCase ticket_note DB row with optional overrides."""
    row: dict = {
        "id": "n-0001",
        "ticketId": "t-0001",
        "authorId": "staff-001",
        "content": "Escalated to senior staff.",
        "createdAt": "2026-07-01T12:30:00+00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# from_db_row — camelCase DB keys -> snake_case attrs
# ---------------------------------------------------------------------------


def test_ticket_note_from_db_row_maps_camelcase() -> None:
    """TicketNote.from_db_row MUST map camelCase DB keys to snake_case attrs."""
    note = TicketNote.from_db_row(_note_row())

    assert note.id == "n-0001"
    assert note.ticket_id == "t-0001"
    assert note.author_id == "staff-001"
    assert note.content == "Escalated to senior staff."


def test_ticket_note_from_db_row_preserves_created_at() -> None:
    """TicketNote.from_db_row MUST pass createdAt through to created_at.

    Mirrors the project convention (Ticket/TicketCategory keep the raw DB
    timestamp value rather than parsing it back to a datetime).
    """
    note = TicketNote.from_db_row(_note_row(createdAt="2026-07-04T09:15:00+00:00"))

    assert note.created_at == "2026-07-04T09:15:00+00:00"


def test_ticket_note_from_db_row_handles_missing_created_at() -> None:
    """TicketNote.from_db_row MUST default created_at to None when absent."""
    row = _note_row()
    row.pop("createdAt")

    note = TicketNote.from_db_row(row)

    assert note.created_at is None
    assert note.id == "n-0001"  # other fields still mapped


# ---------------------------------------------------------------------------
# to_db_dict — snake_case attrs -> camelCase keys
# ---------------------------------------------------------------------------


def test_ticket_note_to_db_dict_uses_camelcase_keys() -> None:
    """TicketNote.to_db_dict MUST emit camelCase keys with correct values."""
    note = TicketNote(
        id="n-0002",
        ticket_id="t-0001",
        author_id="staff-002",
        content="Following up.",
        created_at=datetime(2026, 7, 2, 8, 0, tzinfo=UTC),
    )

    result = note.to_db_dict()

    assert result["id"] == "n-0002"
    assert result["ticketId"] == "t-0001"
    assert result["authorId"] == "staff-002"
    assert result["content"] == "Following up."
    assert result["createdAt"] == datetime(2026, 7, 2, 8, 0, tzinfo=UTC).isoformat()


def test_ticket_note_to_db_dict_none_created_at() -> None:
    """TicketNote.to_db_dict MUST emit 'createdAt': None when created_at is unset."""
    note = TicketNote(
        id="n-0003",
        ticket_id="t-0001",
        author_id="staff-003",
        content="Quick note.",
        created_at=None,
    )

    result = note.to_db_dict()

    assert "createdAt" in result
    assert result["createdAt"] is None


# ---------------------------------------------------------------------------
# Round-trip — TicketNote survives from_db_row(to_db_dict(x))
# ---------------------------------------------------------------------------


def test_ticket_note_round_trip() -> None:
    """A TicketNote MUST survive a to_db_dict -> from_db_row round-trip.

    created_at is held as None to avoid the datetime <-> string mismatch
    (from_db_row does not parse ISO strings back to datetime), matching the
    TicketCategory round-trip convention.
    """
    original = TicketNote(
        id="n-rt",
        ticket_id="t-rt",
        author_id="staff-rt",
        content="Round-trip note.",
        created_at=None,
    )

    rebuilt = TicketNote.from_db_row(original.to_db_dict())

    assert rebuilt == original


# ==========================================================================
# IntegrityEvidence and RepairResult contracts
# ==========================================================================


def test_integrity_evidence_derives_corrobated_zombie_from_active_missing_channel() -> None:
    """Active tickets with a completed missing-channel check are corroborated."""
    evidence = IntegrityEvidence.from_db_row(
        {
            "ticketId": "t1",
            "guildId": "g1",
            "channelId": "c1",
            "status": "open",
        },
        channel_exists=False,
    )

    now = datetime.now(UTC)
    evidence = IntegrityEvidence.from_db_row(
        {
            "ticketId": "t1",
            "guildId": "g1",
            "channelId": "c1",
            "status": "open",
            "observedAt": now.isoformat(),
        },
        channel_exists=False,
    )

    assert evidence == IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=now,
        evidence_id=evidence.evidence_id,
    )
    assert evidence.corroborated is True


def test_integrity_evidence_does_not_corrobate_live_or_closed_ticket() -> None:
    """A live channel and a closed ticket are both safe no-op evidence."""
    live = IntegrityEvidence.from_db_row(
        {"ticketId": "t2", "guildId": "g1", "channelId": "c2", "status": "open"},
        channel_exists=True,
    )
    closed = IntegrityEvidence.from_db_row(
        {"ticketId": "t3", "guildId": "g1", "channelId": "c3", "status": "closed"},
        channel_exists=False,
    )

    assert live.corroborated is False
    assert closed.corroborated is False  # closed ticket never corroborates


def test_integrity_evidence_serializes_camelcase_without_mutating_input() -> None:
    """Evidence serialization preserves identifiers and does not alter the row."""
    row = {"ticketId": "t4", "guildId": "g2", "channelId": None, "status": "claimed"}
    original = row.copy()

    evidence = IntegrityEvidence.from_db_row(row, channel_exists=False)

    assert evidence.to_db_dict() == {
        "ticketId": "t4",
        "guildId": "g2",
        "channelId": None,
        "status": "claimed",
        "channelExists": False,
        "observedAt": evidence.observed_at.isoformat(),
        "evidenceId": evidence.evidence_id,
        "source": None,
        "corroborated": True,
    }
    assert row == original


def test_repair_result_accepts_each_deterministic_contract_outcome() -> None:
    """Repair results expose only the documented action/outcome combinations."""
    timestamp = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    results = (
        RepairResult("t1", "g1", "close", "repaired", None, "e1", timestamp),
        RepairResult("t1", "g1", "no_op", "already_closed", None, None, timestamp),
        RepairResult("t2", "g1", "no_op", "skipped", "channel_exists", None, timestamp),
        RepairResult("t3", "g1", "no_op", "error", "HTTPException", None, timestamp),
    )

    assert [result.outcome for result in results] == ["repaired", "already_closed", "skipped", "error"]
    assert results[0].evidence_id == "e1"
    assert results[1].action == "no_op"


def test_repair_result_round_trips_camelcase_fields() -> None:
    """Repair results serialize and deserialize without losing audit data."""
    result = RepairResult("t1", "g1", "close", "repaired", "done", "e1", datetime(2026, 7, 17, tzinfo=UTC))

    assert RepairResult.from_db_row(result.to_db_dict()) == result


def test_repair_result_quarantined_requires_non_empty_reason() -> None:
    """Quarantined is no longer a valid outcome per spec; it must be rejected as invalid combination."""
    timestamp = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="Invalid"):
        RepairResult("t1", "g1", "no_op", "quarantined", "reason", None, timestamp)
    with pytest.raises(ValueError, match="Invalid"):
        RepairResult("t1", "g1", "no_op", "quarantined", None, None, timestamp)


def test_repair_result_error_requires_non_empty_reason() -> None:
    """An error result MUST carry a non-empty reason (never a silent failure)."""
    timestamp = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="reason"):
        RepairResult("t1", "g1", "no_op", "error", None, None, timestamp)


def test_repair_result_close_error_is_valid_combination() -> None:
    """A transition that executed but whose audit could not persist MUST be
    representable as ``close/error`` (mutation happened, success NOT claimed)."""
    timestamp = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    result = RepairResult("t1", "g1", "close", "error", "audit_persistence_failed", None, timestamp)
    assert result.action == "close"
    assert result.outcome == "error"
    assert result.evidence_id is None


# ==========================================================================
# IntegrityEvidence tri-state + freshness (product-artifact-audit PR1)
# ==========================================================================


def test_integrity_evidence_channel_exists_none_is_unresolved_not_false() -> None:
    """channel_exists=None MUST yield corroborated=None (tri-state), never False."""
    evidence = IntegrityEvidence.from_db_row(
        {"ticketId": "t-unk", "guildId": "g1", "channelId": "c1", "status": "open"},
        channel_exists=None,
    )

    assert evidence.channel_exists is None
    assert evidence.corroborated is None
    # Serialization preserves the tri-state without coercion.
    assert evidence.to_db_dict()["channelExists"] is None


def test_integrity_evidence_corroborated_requires_fresh_active_absence() -> None:
    """corroborated is True only for an active ticket, False channel, fresh window."""
    fresh = datetime.now(UTC)
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=fresh,
    )

    assert evidence.corroborated is True


def test_integrity_evidence_stale_absence_is_unresolved() -> None:
    """A stale channel-absent observation MUST NOT corroborate (fail closed)."""
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


def test_integrity_evidence_evidence_id_round_trips() -> None:
    """A stable evidence_id MUST survive the camelCase round-trip."""
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
    )

    rebuilt = IntegrityEvidence.from_db_row(evidence.to_db_dict())

    assert rebuilt.evidence_id == evidence.evidence_id
    assert evidence.evidence_id  # non-empty


def test_integrity_evidence_future_dated_observation_fails_closed() -> None:
    """A future-dated observation MUST NOT corroborate (fail closed to unresolved)."""
    future = datetime.now(UTC) + timedelta(days=2)
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=future,
    )

    assert evidence.corroborated is None


def test_integrity_evidence_future_dated_margin_rejected() -> None:
    """Even a barely-future observation (1 minute) MUST fail closed."""
    future = datetime.now(UTC) + timedelta(minutes=1)
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=future,
    )

    assert evidence.corroborated is None


def test_integrity_evidence_has_source_provenance() -> None:
    """IntegrityEvidence MUST carry an immutable ``source`` provenance field."""
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
        source="channel_delete",
    )

    assert evidence.source == "channel_delete"


def test_integrity_evidence_source_serializes_camelcase() -> None:
    """The source field MUST serialize to ``source`` in to_db_dict."""
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
        source="sweep",
    )

    assert evidence.to_db_dict()["source"] == "sweep"


def test_integrity_evidence_source_from_db_row() -> None:
    """from_db_row MUST map the ``source`` key back to ``source``."""
    evidence = IntegrityEvidence.from_db_row(
        {
            "ticketId": "t1",
            "guildId": "g1",
            "channelId": "c1",
            "status": "open",
            "source": "manual",
        },
        channel_exists=False,
    )

    assert evidence.source == "manual"


def test_integrity_evidence_source_defaults_none() -> None:
    """When no source is supplied, it defaults to None without breaking corroboration."""
    evidence = IntegrityEvidence(
        ticket_id="t1",
        guild_id="g1",
        channel_id="c1",
        status="open",
        channel_exists=False,
        observed_at=datetime.now(UTC),
    )

    assert evidence.source is None
    assert evidence.corroborated is True


# ==========================================================================
# CloseResult contract (product-artifact-audit PR1 — ported from reconciliation)
# ==========================================================================


def test_close_result_success_contract() -> None:
    """A successful close result carries reason, transcript URL, and evidence."""
    result = CloseResult(
        ticket_id="t1",
        outcome="success",
        close_reason="manual",
        transcript_url="https://transcripts.example/t1",
        evidence_id=None,
    )

    assert result.outcome == "success"
    assert result.close_reason == "manual"
    assert result.transcript_url == "https://transcripts.example/t1"
    assert result.evidence_id is None


def test_close_result_denied_and_error_are_distinct() -> None:
    """Denied and error outcomes MUST be distinguishable from success."""
    denied = CloseResult("t2", "denied", "already_closed", None, None)
    errored = CloseResult("t3", "error", "HTTPException", None, None)

    assert denied.outcome == "denied"
    assert errored.outcome == "error"
    assert denied.outcome != "success"
    assert errored.outcome != "success"
    assert denied.close_reason == "already_closed"
    assert errored.close_reason == "HTTPException"


def test_close_result_is_immutable_and_serializable() -> None:
    """CloseResult MUST be frozen and round-trip its fields."""
    result = CloseResult(
        ticket_id="t1",
        outcome="success",
        close_reason="zombie:repair",
        transcript_url=None,
        evidence_id="e1",
    )

    with pytest.raises(FrozenInstanceError):
        result.outcome = "denied"  # type: ignore[misc]

    assert result.evidence_id == "e1"
    assert result.ticket_id == "t1"
