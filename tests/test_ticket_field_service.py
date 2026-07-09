"""Unit tests for bot.services.ticket_field_service.

Covers the ticket-custom-fields spec scenarios for field definition validation:
    - Valid field definitions accepted
    - Max 3 fields enforced
    - Missing required keys rejected
    - Key format validation (^[a-z][a-z0-9_]{0,31}$)
    - Duplicate keys rejected
    - Label/placeholder length limits
    - Style defaults and validation
    - Required value validation for submitted custom_fields
"""

from __future__ import annotations

import pytest

from bot.services.ticket_field_service import (
    validate_field_definitions,
    validate_custom_fields,
)

# ---------------------------------------------------------------------------
# validate_field_definitions — happy path
# ---------------------------------------------------------------------------


class TestValidateFieldDefinitions:
    """Verify validate_field_definitions() accepts valid definitions and rejects invalid ones."""

    def test_empty_list_accepted(self) -> None:
        """An empty field definitions list MUST be accepted."""
        result = validate_field_definitions([])
        assert result == []

    def test_single_valid_field(self) -> None:
        """A single valid short field MUST be accepted and normalized."""
        defs = [{"key": "player_nick", "label": "Player Nickname"}]
        result = validate_field_definitions(defs)
        assert len(result) == 1
        assert result[0]["key"] == "player_nick"
        assert result[0]["label"] == "Player Nickname"
        assert result[0]["style"] == "short"
        assert result[0]["required"] is False
        assert result[0]["max_length"] == 100

    def test_two_valid_fields(self) -> None:
        """Two valid fields with mixed options MUST be accepted."""
        defs = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True},
            {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False},
        ]
        result = validate_field_definitions(defs)
        assert len(result) == 2
        assert result[0]["required"] is True
        assert result[1]["required"] is False

    def test_three_valid_fields_max(self) -> None:
        """Three fields (the maximum) MUST be accepted."""
        defs = [
            {"key": "field_a", "label": "Field A"},
            {"key": "field_b", "label": "Field B"},
            {"key": "field_c", "label": "Field C"},
        ]
        result = validate_field_definitions(defs)
        assert len(result) == 3

    def test_paragraph_style_accepted(self) -> None:
        """A field with style='paragraph' MUST be accepted with max_length=2000."""
        defs = [{"key": "details", "label": "Details", "style": "paragraph"}]
        result = validate_field_definitions(defs)
        assert result[0]["style"] == "paragraph"
        assert result[0]["max_length"] == 2000

    def test_custom_max_length_within_range(self) -> None:
        """A custom max_length between 1 and 1000 MUST be accepted for short fields."""
        defs = [{"key": "code", "label": "Code", "max_length": 50}]
        result = validate_field_definitions(defs)
        assert result[0]["max_length"] == 50

    def test_placeholder_preserved(self) -> None:
        """An optional placeholder MUST be preserved in the normalized output."""
        defs = [{"key": "player_nick", "label": "Player Nickname", "placeholder": "In-game name"}]
        result = validate_field_definitions(defs)
        assert result[0]["placeholder"] == "In-game name"

    def test_unknown_keys_stripped(self) -> None:
        """Unknown keys in a field definition MUST be stripped from the output."""
        defs = [{"key": "player_nick", "label": "Nick", "bogus_key": "remove me"}]
        result = validate_field_definitions(defs)
        assert "bogus_key" not in result[0]


# ---------------------------------------------------------------------------
# validate_field_definitions — rejection cases
# ---------------------------------------------------------------------------


class TestValidateFieldDefinitionsRejection:
    """Verify validate_field_definitions() rejects invalid inputs."""

    def test_more_than_three_fields_rejected(self) -> None:
        """A list with 4+ fields MUST be rejected."""
        defs = [
            {"key": "f1", "label": "F1"},
            {"key": "f2", "label": "F2"},
            {"key": "f3", "label": "F3"},
            {"key": "f4", "label": "F4"},
        ]
        with pytest.raises(ValueError, match="at most 3"):
            validate_field_definitions(defs)

    def test_missing_key_rejected(self) -> None:
        """A field definition without 'key' MUST be rejected."""
        defs = [{"label": "No Key"}]
        with pytest.raises(ValueError, match="key"):
            validate_field_definitions(defs)

    def test_missing_label_rejected(self) -> None:
        """A field definition without 'label' MUST be rejected."""
        defs = [{"key": "no_label"}]
        with pytest.raises(ValueError, match="label"):
            validate_field_definitions(defs)

    def test_blank_label_rejected(self) -> None:
        """A field definition with an empty label MUST be rejected."""
        defs = [{"key": "x", "label": ""}]
        with pytest.raises(ValueError, match="label"):
            validate_field_definitions(defs)

    def test_label_too_long_rejected(self) -> None:
        """A label longer than 45 characters MUST be rejected."""
        defs = [{"key": "x", "label": "A" * 46}]
        with pytest.raises(ValueError, match="label"):
            validate_field_definitions(defs)

    def test_invalid_key_format_uppercase_rejected(self) -> None:
        """A key with uppercase letters MUST be rejected."""
        defs = [{"key": "Player_Nick", "label": "Nick"}]
        with pytest.raises(ValueError, match="key"):
            validate_field_definitions(defs)

    def test_invalid_key_format_starts_with_number_rejected(self) -> None:
        """A key starting with a number MUST be rejected."""
        defs = [{"key": "1player", "label": "Player"}]
        with pytest.raises(ValueError, match="key"):
            validate_field_definitions(defs)

    def test_invalid_key_format_too_long_rejected(self) -> None:
        """A key longer than 32 characters MUST be rejected."""
        defs = [{"key": "a" * 33, "label": "Long"}]
        with pytest.raises(ValueError, match="key"):
            validate_field_definitions(defs)

    def test_duplicate_keys_rejected(self) -> None:
        """Two fields with the same key MUST be rejected."""
        defs = [
            {"key": "player_nick", "label": "Nick 1"},
            {"key": "player_nick", "label": "Nick 2"},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            validate_field_definitions(defs)

    def test_invalid_style_rejected(self) -> None:
        """A field with style other than 'short' or 'paragraph' MUST be rejected."""
        defs = [{"key": "x", "label": "X", "style": "long"}]
        with pytest.raises(ValueError, match="style"):
            validate_field_definitions(defs)

    def test_max_length_zero_rejected(self) -> None:
        """A max_length of 0 MUST be rejected (minimum is 1)."""
        defs = [{"key": "x", "label": "X", "max_length": 0}]
        with pytest.raises(ValueError, match="max_length"):
            validate_field_definitions(defs)

    def test_max_length_over_1000_for_short_rejected(self) -> None:
        """A max_length over 1000 for short style MUST be rejected."""
        defs = [{"key": "x", "label": "X", "style": "short", "max_length": 1001}]
        with pytest.raises(ValueError, match="max_length"):
            validate_field_definitions(defs)

    def test_max_length_over_2000_for_paragraph_rejected(self) -> None:
        """A max_length over 2000 for paragraph style MUST be rejected."""
        defs = [{"key": "x", "label": "X", "style": "paragraph", "max_length": 2001}]
        with pytest.raises(ValueError, match="max_length"):
            validate_field_definitions(defs)

    def test_placeholder_too_long_rejected(self) -> None:
        """A placeholder longer than 100 characters MUST be rejected."""
        defs = [{"key": "x", "label": "X", "placeholder": "P" * 101}]
        with pytest.raises(ValueError, match="placeholder"):
            validate_field_definitions(defs)

    def test_not_a_list_rejected(self) -> None:
        """A non-list input MUST be rejected."""
        with pytest.raises(ValueError, match="list"):
            validate_field_definitions("not a list")  # type: ignore[arg-type]

    def test_non_dict_item_rejected(self) -> None:
        """A non-dict item in the list MUST be rejected."""
        with pytest.raises(ValueError, match="dict"):
            validate_field_definitions(["not a dict"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# validate_custom_fields — happy path
# ---------------------------------------------------------------------------


class TestValidateCustomFields:
    """Verify validate_custom_fields() validates submitted values against definitions."""

    def test_empty_fields_for_no_definitions(self) -> None:
        """Empty custom_fields with empty definitions MUST be accepted."""
        result = validate_custom_fields({}, [])
        assert result == {}

    def test_valid_required_field_submitted(self) -> None:
        """A required field with a value MUST be accepted."""
        defs = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100}]
        result = validate_custom_fields({"player_nick": "DarkSlayer42"}, defs)
        assert result == {"player_nick": "DarkSlayer42"}

    def test_optional_field_blank_omitted(self) -> None:
        """A blank optional field MUST be omitted from the result."""
        defs = [{"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False, "max_length": 100}]
        result = validate_custom_fields({"evidence_url": "  "}, defs)
        assert result == {}

    def test_optional_field_absent_ok(self) -> None:
        """An absent optional field MUST be accepted."""
        defs = [{"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False, "max_length": 100}]
        result = validate_custom_fields({}, defs)
        assert result == {}

    def test_values_trimmed(self) -> None:
        """Field values MUST be trimmed of leading/trailing whitespace."""
        defs = [{"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}]
        result = validate_custom_fields({"player_nick": "  DarkSlayer42  "}, defs)
        assert result == {"player_nick": "DarkSlayer42"}

    def test_value_exceeding_max_length_truncated(self) -> None:
        """A value exceeding max_length MUST be truncated."""
        defs = [{"key": "code", "label": "Code", "style": "short", "required": False, "max_length": 5}]
        result = validate_custom_fields({"code": "abcdefgh"}, defs)
        assert result == {"code": "abcde"}

    def test_extra_keys_ignored(self) -> None:
        """Keys not in the definitions MUST be ignored."""
        defs = [{"key": "player_nick", "label": "Nick", "style": "short", "required": False, "max_length": 100}]
        result = validate_custom_fields({"player_nick": "Dark", "bogus": "value"}, defs)
        assert result == {"player_nick": "Dark"}


# ---------------------------------------------------------------------------
# validate_custom_fields — rejection cases
# ---------------------------------------------------------------------------


class TestValidateCustomFieldsRejection:
    """Verify validate_custom_fields() rejects invalid submissions."""

    def test_missing_required_field_rejected(self) -> None:
        """A missing required field MUST be rejected."""
        defs = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100}]
        with pytest.raises(ValueError, match="required"):
            validate_custom_fields({}, defs)

    def test_blank_required_field_rejected(self) -> None:
        """A blank required field MUST be rejected."""
        defs = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100}]
        with pytest.raises(ValueError, match="required"):
            validate_custom_fields({"player_nick": "  "}, defs)

    def test_non_string_value_rejected(self) -> None:
        """A non-string value MUST be rejected."""
        defs = [{"key": "count", "label": "Count", "style": "short", "required": False, "max_length": 100}]
        with pytest.raises(ValueError, match="string"):
            validate_custom_fields({"count": 42}, defs)  # type: ignore[dict-item]
