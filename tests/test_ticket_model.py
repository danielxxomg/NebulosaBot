"""Unit tests for bot.models.ticket.Ticket and bot.models.ticket_note.TicketNote.

Covers the ``ticket-model`` spec scenarios for the tickets-subsidiados change:

    - Ticket.from_db_row maps ``parentId`` -> ``parent_id`` (populated + null)
    - Ticket.to_db_dict includes ``"parentId"`` (populated + null)
    - TicketNote.from_db_row maps camelCase DB keys -> snake_case attrs
    - TicketNote.to_db_dict converts back to camelCase keys
    - Round-trip preservation for both dataclasses
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.models.ticket import Ticket

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
# Ticket — parent_id serialization
# ===========================================================================


# ---------------------------------------------------------------------------
# from_db_row — parentId -> parent_id
# ---------------------------------------------------------------------------


def test_from_db_row_maps_populated_parent_id() -> None:
    """from_db_row MUST map row['parentId'] -> ticket.parent_id when populated."""
    row = _ticket_row(parentId="parent-uuid-123")

    ticket = Ticket.from_db_row(row)

    assert ticket.parent_id == "parent-uuid-123"


def test_from_db_row_maps_null_parent_id() -> None:
    """from_db_row MUST set parent_id=None when the row's parentId is null."""
    row = _ticket_row(parentId=None)

    ticket = Ticket.from_db_row(row)

    assert ticket.parent_id is None


def test_from_db_row_parent_id_defaults_none_when_missing() -> None:
    """from_db_row MUST set parent_id=None when the row omits parentId entirely."""
    row = _ticket_row()
    row.pop("parentId")  # simulate an older row written before Migration 003

    ticket = Ticket.from_db_row(row)

    assert ticket.parent_id is None


# ---------------------------------------------------------------------------
# to_db_dict — parent_id -> "parentId"
# ---------------------------------------------------------------------------


def test_to_db_dict_includes_populated_parent_id() -> None:
    """to_db_dict MUST emit 'parentId' with the parent_id value when set."""
    ticket = Ticket(
        id="t-0001",
        ticket_number=7,
        guild_id="123456789",
        author_id="111111111",
        channel_id="888888888",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        parent_id="parent-uuid-123",
    )

    result = ticket.to_db_dict()

    assert result["parentId"] == "parent-uuid-123"


def test_to_db_dict_includes_null_parent_id() -> None:
    """to_db_dict MUST emit 'parentId': None when parent_id is unset."""
    ticket = Ticket(
        id="t-0002",
        ticket_number=8,
        guild_id="123456789",
        author_id="111111111",
        channel_id="888888889",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        parent_id=None,
    )

    result = ticket.to_db_dict()

    assert "parentId" in result
    assert result["parentId"] is None


# ---------------------------------------------------------------------------
# Round-trip — parent_id survives from_db_row(to_db_dict(x))
# ---------------------------------------------------------------------------


def test_ticket_parent_id_round_trip_populated() -> None:
    """A populated parent_id MUST survive a to_db_dict -> from_db_row round-trip."""
    ticket = Ticket(
        id="t-rt",
        ticket_number=9,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        parent_id="parent-rt-uuid",
    )

    rebuilt = Ticket.from_db_row(ticket.to_db_dict())

    assert rebuilt.parent_id == "parent-rt-uuid"
    assert rebuilt.id == ticket.id


def test_ticket_parent_id_round_trip_none() -> None:
    """A null parent_id MUST survive a to_db_dict -> from_db_row round-trip."""
    ticket = Ticket(
        id="t-rt-none",
        ticket_number=10,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        parent_id=None,
    )

    rebuilt = Ticket.from_db_row(ticket.to_db_dict())

    assert rebuilt.parent_id is None


# ===========================================================================
# Ticket — subject / description serialization
# ===========================================================================


# ---------------------------------------------------------------------------
# from_db_row — subject / description
# ---------------------------------------------------------------------------


def test_from_db_row_maps_populated_subject_and_description() -> None:
    """from_db_row MUST map row['subject'] and row['description'] when populated."""
    row = _ticket_row(subject="Login broken", description="Cannot access since Monday")

    ticket = Ticket.from_db_row(row)

    assert ticket.subject == "Login broken"
    assert ticket.description == "Cannot access since Monday"


def test_from_db_row_maps_null_subject_and_description() -> None:
    """from_db_row MUST set subject=None and description=None when null."""
    row = _ticket_row(subject=None, description=None)

    ticket = Ticket.from_db_row(row)

    assert ticket.subject is None
    assert ticket.description is None


def test_from_db_row_subject_description_defaults_none_when_missing() -> None:
    """from_db_row MUST default subject/description to None when keys absent."""
    row = _ticket_row()
    row.pop("subject")
    row.pop("description")

    ticket = Ticket.from_db_row(row)

    assert ticket.subject is None
    assert ticket.description is None


# ---------------------------------------------------------------------------
# to_db_dict — subject / description
# ---------------------------------------------------------------------------


def test_to_db_dict_includes_populated_subject_and_description() -> None:
    """to_db_dict MUST emit 'subject' and 'description' when set."""
    ticket = Ticket(
        id="t-subject",
        ticket_number=11,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        subject="Bug",
        description="Details",
    )

    result = ticket.to_db_dict()

    assert result["subject"] == "Bug"
    assert result["description"] == "Details"


def test_to_db_dict_includes_null_subject_and_description() -> None:
    """to_db_dict MUST emit subject=None and description=None when unset."""
    ticket = Ticket(
        id="t-subject-null",
        ticket_number=12,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        subject=None,
        description=None,
    )

    result = ticket.to_db_dict()

    assert "subject" in result
    assert result["subject"] is None
    assert "description" in result
    assert result["description"] is None


# ---------------------------------------------------------------------------
# Round-trip — subject / description survive from_db_row(to_db_dict(x))
# ---------------------------------------------------------------------------


def test_ticket_subject_description_round_trip_populated() -> None:
    """Populated subject/description MUST survive a to_db_dict -> from_db_row round-trip."""
    ticket = Ticket(
        id="t-rt-subj",
        ticket_number=13,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        subject="Login broken",
        description="Cannot access since Monday",
    )

    rebuilt = Ticket.from_db_row(ticket.to_db_dict())

    assert rebuilt.subject == "Login broken"
    assert rebuilt.description == "Cannot access since Monday"


def test_ticket_subject_description_round_trip_none() -> None:
    """Null subject/description MUST survive a to_db_dict -> from_db_row round-trip."""
    ticket = Ticket(
        id="t-rt-subj-none",
        ticket_number=14,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        subject=None,
        description=None,
    )

    rebuilt = Ticket.from_db_row(ticket.to_db_dict())

    assert rebuilt.subject is None
    assert rebuilt.description is None


# ===========================================================================
# Ticket — custom_fields serialization (JSONB object)
# ===========================================================================


# ---------------------------------------------------------------------------
# from_db_row — customFields -> custom_fields
# ---------------------------------------------------------------------------


def test_from_db_row_maps_populated_custom_fields() -> None:
    """from_db_row MUST map row['customFields'] -> ticket.custom_fields when populated."""
    row = _ticket_row(customFields={"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"})

    ticket = Ticket.from_db_row(row)

    assert ticket.custom_fields == {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}


def test_from_db_row_maps_null_custom_fields_to_none() -> None:
    """from_db_row MUST set custom_fields=None when the row's customFields is null."""
    row = _ticket_row(customFields=None)

    ticket = Ticket.from_db_row(row)

    assert ticket.custom_fields is None


def test_from_db_row_custom_fields_defaults_none_when_missing() -> None:
    """from_db_row MUST set custom_fields=None when the row omits customFields entirely."""
    row = _ticket_row()
    row.pop("customFields", None)

    ticket = Ticket.from_db_row(row)

    assert ticket.custom_fields is None


# ---------------------------------------------------------------------------
# to_db_dict — custom_fields -> "customFields"
# ---------------------------------------------------------------------------


def test_to_db_dict_includes_populated_custom_fields() -> None:
    """to_db_dict MUST emit 'customFields' with the custom_fields value when set."""
    ticket = Ticket(
        id="t-cf-01",
        ticket_number=20,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        custom_fields={"player_nick": "DarkSlayer42"},
    )

    result = ticket.to_db_dict()

    assert result["customFields"] == {"player_nick": "DarkSlayer42"}


def test_to_db_dict_includes_null_custom_fields() -> None:
    """to_db_dict MUST emit 'customFields': None when custom_fields is unset."""
    ticket = Ticket(
        id="t-cf-02",
        ticket_number=21,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        custom_fields=None,
    )

    result = ticket.to_db_dict()

    assert "customFields" in result
    assert result["customFields"] is None


# ---------------------------------------------------------------------------
# Round-trip — custom_fields survives from_db_row(to_db_dict(x))
# ---------------------------------------------------------------------------


def test_ticket_custom_fields_round_trip_populated() -> None:
    """A populated custom_fields MUST survive a to_db_dict -> from_db_row round-trip."""
    fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}
    ticket = Ticket(
        id="t-rt-cf",
        ticket_number=22,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        custom_fields=fields,
    )

    rebuilt = Ticket.from_db_row(ticket.to_db_dict())

    assert rebuilt.custom_fields == fields


def test_ticket_custom_fields_round_trip_none() -> None:
    """A null custom_fields MUST survive a to_db_dict -> from_db_row round-trip."""
    ticket = Ticket(
        id="t-rt-cf-none",
        ticket_number=23,
        guild_id="g1",
        author_id="a1",
        channel_id="c1",
        status="open",
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_activity=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        custom_fields=None,
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
    from bot.models.ticket_note import TicketNote

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
    from bot.models.ticket_note import TicketNote

    note = TicketNote.from_db_row(_note_row(createdAt="2026-07-04T09:15:00+00:00"))

    assert note.created_at == "2026-07-04T09:15:00+00:00"


def test_ticket_note_from_db_row_handles_missing_created_at() -> None:
    """TicketNote.from_db_row MUST default created_at to None when absent."""
    from bot.models.ticket_note import TicketNote

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
    from bot.models.ticket_note import TicketNote

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
    from bot.models.ticket_note import TicketNote

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
    from bot.models.ticket_note import TicketNote

    original = TicketNote(
        id="n-rt",
        ticket_id="t-rt",
        author_id="staff-rt",
        content="Round-trip note.",
        created_at=None,
    )

    rebuilt = TicketNote.from_db_row(original.to_db_dict())

    assert rebuilt == original
