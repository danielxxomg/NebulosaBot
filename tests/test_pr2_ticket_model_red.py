"""RED for PR2 2.4 Ticket model scheduled_close_at/by."""

from datetime import UTC, datetime


def test_ticket_model_has_scheduled_fields():
    import inspect

    from bot.models.ticket import Ticket

    sig = inspect.signature(Ticket)
    assert "scheduled_close_at" in sig.parameters
    assert "scheduled_close_by" in sig.parameters


def test_ticket_from_db_row_scheduled_non_null():
    from bot.models.ticket import Ticket

    now = datetime.now(UTC)
    row = {
        "id": "uuid-1",
        "ticketNumber": 1,
        "guildId": "g1",
        "authorId": "a1",
        "channelId": "c1",
        "status": "open",
        "createdAt": now,
        "lastActivity": now,
        "scheduledCloseAt": now,
        "scheduledCloseBy": "mod1",
    }
    t = Ticket.from_db_row(row)
    assert t.scheduled_close_at == now
    assert t.scheduled_close_by == "mod1"


def test_ticket_from_db_row_scheduled_null():
    from bot.models.ticket import Ticket

    now = datetime.now(UTC)
    row = {
        "id": "uuid-2",
        "ticketNumber": 2,
        "guildId": "g1",
        "authorId": "a1",
        "channelId": "c2",
        "status": "open",
        "createdAt": now,
        "lastActivity": now,
    }
    t = Ticket.from_db_row(row)
    assert t.scheduled_close_at is None
    assert t.scheduled_close_by is None


def test_ticket_to_db_dict_scheduled_roundtrip():
    from bot.models.ticket import Ticket

    now = datetime.now(UTC)
    t = Ticket(
        id="uuid-3",
        ticket_number=3,
        guild_id="g1",
        author_id="a1",
        channel_id="c3",
        status="open",
        created_at=now,
        last_activity=now,
        scheduled_close_at=now,
        scheduled_close_by="mod2",
    )
    d = t.to_db_dict()
    assert "scheduledCloseAt" in d and "scheduledCloseBy" in d
    # ISO-8601 for timestamp when set
    assert isinstance(d["scheduledCloseAt"], str)
    assert d["scheduledCloseBy"] == "mod2"
    # null round-trip
    t2 = Ticket(
        id="uuid-4",
        ticket_number=4,
        guild_id="g1",
        author_id="a1",
        channel_id="c4",
        status="open",
        created_at=now,
        last_activity=now,
    )
    d2 = t2.to_db_dict()
    assert d2["scheduledCloseAt"] is None
    assert d2["scheduledCloseBy"] is None
