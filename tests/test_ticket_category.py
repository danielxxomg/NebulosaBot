"""Unit tests for bot.models.ticket_category.TicketCategory.

Covers:
    - from_db_row() — builds correct dataclass from Supabase row (camelCase keys)
    - to_db_dict() — produces correct camelCase dict for Supabase
    - Round-trip — from_db_row(to_db_dict(x)) preserves all fields
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.models.ticket_category import TicketCategory

# ---------------------------------------------------------------------------
# from_db_row
# ---------------------------------------------------------------------------


def test_from_db_row_basic() -> None:
    """from_db_row MUST build a TicketCategory with all fields mapped correctly."""
    row = {
        "id": "cat-001",
        "guildId": "123456789",
        "name": "Support",
        "emoji": "🎫",
        "description": "General support tickets",
        "position": 3,
        "active": True,
        "createdAt": "2026-06-16T10:00:00+00:00",
    }

    cat = TicketCategory.from_db_row(row)

    assert cat.id == "cat-001"
    assert cat.guild_id == "123456789"
    assert cat.name == "Support"
    assert cat.emoji == "🎫"
    assert cat.description == "General support tickets"
    assert cat.position == 3
    assert cat.active is True
    assert cat.created_at == "2026-06-16T10:00:00+00:00"


def test_from_db_row_minimal() -> None:
    """from_db_row MUST handle missing optional fields (None defaults)."""
    row = {
        "id": "cat-002",
        "guildId": "987654321",
        "name": "Bug Report",
        "position": 0,
    }

    cat = TicketCategory.from_db_row(row)

    assert cat.id == "cat-002"
    assert cat.guild_id == "987654321"
    assert cat.name == "Bug Report"
    assert cat.emoji is None
    assert cat.description is None
    assert cat.position == 0
    assert cat.active is True  # default from .get("active", True)
    assert cat.created_at is None


# ---------------------------------------------------------------------------
# to_db_dict
# ---------------------------------------------------------------------------


def test_to_db_dict_full() -> None:
    """to_db_dict MUST produce a camelCase dict with all fields."""
    now = datetime(2026, 6, 16, 15, 30, 0, tzinfo=UTC)
    cat = TicketCategory(
        id="cat-003",
        guild_id="111222333",
        name="Feedback",
        emoji="💬",
        description="User feedback",
        position=5,
        active=True,
        created_at=now,
    )

    result = cat.to_db_dict()

    assert result["id"] == "cat-003"
    assert result["guildId"] == "111222333"
    assert result["name"] == "Feedback"
    assert result["emoji"] == "💬"
    assert result["description"] == "User feedback"
    assert result["position"] == 5
    assert result["active"] is True
    assert result["createdAt"] == now.isoformat()


def test_to_db_dict_none_fields() -> None:
    """to_db_dict MUST emit None for optional fields that are unset."""
    cat = TicketCategory(
        id="cat-004",
        guild_id="444555666",
        name="Other",
    )

    result = cat.to_db_dict()

    assert result["id"] == "cat-004"
    assert result["guildId"] == "444555666"
    assert result["name"] == "Other"
    assert result["emoji"] is None
    assert result["description"] is None
    assert result["position"] == 0
    assert result["active"] is True
    assert result["createdAt"] is None


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip() -> None:
    """from_db_row(to_db_dict(x)) MUST round-trip cleanly.

    Note: created_at is kept as None to avoid datetime ↔ string mismatch
    — from_db_row does not parse ISO strings back into datetime objects.
    """
    original = TicketCategory(
        id="cat-roundtrip",
        guild_id="999888777",
        name="Round-Trip",
        emoji="🔄",
        description="Testing round-trip conversion",
        position=7,
        active=True,
        created_at=None,
    )

    db_dict = original.to_db_dict()
    round_tripped = TicketCategory.from_db_row(db_dict)

    assert round_tripped == original


# ---------------------------------------------------------------------------
# from_db_row — field_definitions (JSONB array)
# ---------------------------------------------------------------------------


def test_from_db_row_with_field_definitions() -> None:
    """from_db_row MUST map row['fieldDefinitions'] to field_definitions list."""
    row = {
        "id": "cat-fd-01",
        "guildId": "g1",
        "name": "Reportes",
        "position": 0,
        "fieldDefinitions": [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True},
            {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False},
        ],
    }

    cat = TicketCategory.from_db_row(row)

    assert len(cat.field_definitions) == 2
    assert cat.field_definitions[0]["key"] == "player_nick"
    assert cat.field_definitions[0]["required"] is True
    assert cat.field_definitions[1]["key"] == "evidence_url"
    assert cat.field_definitions[1]["required"] is False


def test_from_db_row_without_field_definitions_defaults_empty() -> None:
    """from_db_row MUST default field_definitions to [] when key is missing."""
    row = {
        "id": "cat-fd-02",
        "guildId": "g1",
        "name": "Support",
        "position": 0,
    }

    cat = TicketCategory.from_db_row(row)

    assert cat.field_definitions == []


def test_from_db_row_with_null_field_definitions_defaults_empty() -> None:
    """from_db_row MUST default field_definitions to [] when key is null."""
    row = {
        "id": "cat-fd-03",
        "guildId": "g1",
        "name": "Support",
        "position": 0,
        "fieldDefinitions": None,
    }

    cat = TicketCategory.from_db_row(row)

    assert cat.field_definitions == []


# ---------------------------------------------------------------------------
# to_db_dict — field_definitions
# ---------------------------------------------------------------------------


def test_to_db_dict_includes_field_definitions() -> None:
    """to_db_dict MUST include 'fieldDefinitions' when populated."""
    cat = TicketCategory(
        id="cat-fd-04",
        guild_id="g1",
        name="Reportes",
        field_definitions=[
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True},
        ],
    )

    result = cat.to_db_dict()

    assert result["fieldDefinitions"] == [
        {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True},
    ]


def test_to_db_dict_includes_empty_field_definitions() -> None:
    """to_db_dict MUST include 'fieldDefinitions': [] when empty."""
    cat = TicketCategory(
        id="cat-fd-05",
        guild_id="g1",
        name="Support",
    )

    result = cat.to_db_dict()

    assert result["fieldDefinitions"] == []


# ---------------------------------------------------------------------------
# Round-trip — field_definitions
# ---------------------------------------------------------------------------


def test_round_trip_with_field_definitions() -> None:
    """field_definitions MUST survive from_db_row(to_db_dict(x)) round-trip."""
    definitions = [
        {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True},
        {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False},
    ]
    original = TicketCategory(
        id="cat-rt-fd",
        guild_id="g1",
        name="Reportes",
        field_definitions=definitions,
        created_at=None,
    )

    rebuilt = TicketCategory.from_db_row(original.to_db_dict())

    assert rebuilt.field_definitions == definitions
    assert rebuilt == original
