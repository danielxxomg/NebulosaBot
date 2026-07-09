"""ticket_field_service — pure validation for ticket category field definitions.

All functions are pure: no I/O, no side effects, no Discord or DB calls.
Called by the cog (configure_fields command) and the modal (intake validation).
"""

from __future__ import annotations

import re
from typing import Any

# Allowed field definition keys and their types.
_VALID_STYLES = ("short", "paragraph")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_MAX_FIELDS = 3
_MAX_LABEL_LEN = 45
_MAX_PLACEHOLDER_LEN = 100
_MAX_MAX_LENGTH_SHORT = 1000
_MAX_MAX_LENGTH_PARAGRAPH = 2000
_DEFAULT_MAX_LENGTH_SHORT = 100
_DEFAULT_MAX_LENGTH_PARAGRAPH = 2000

_ALLOWED_KEYS = frozenset({"key", "label", "style", "required", "max_length", "placeholder"})


def validate_field_definitions(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalize a list of field definitions.

    Args:
        raw: The raw input — expected to be a list of dicts.

    Returns:
        Normalized list of field definitions with defaults applied.

    Raises:
        ValueError: If the input violates any constraint.
    """
    if not isinstance(raw, list):
        raise ValueError("field_definitions must be a list")

    if len(raw) > _MAX_FIELDS:
        raise ValueError(f"field_definitions allows at most {_MAX_FIELDS} fields, got {len(raw)}")

    seen_keys: set[str] = set()
    result: list[dict[str, Any]] = []

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"field_definitions[{i}] must be a dict")

        # --- key (required) ---
        key = item.get("key")
        if not key or not isinstance(key, str):
            raise ValueError(f"field_definitions[{i}].key is required and must be a non-empty string")
        if not _KEY_RE.match(key):
            raise ValueError(
                f"field_definitions[{i}].key must match ^[a-z][a-z0-9_]{{0,31}}$, got {key!r}"
            )
        if key in seen_keys:
            raise ValueError(f"field_definitions has duplicate key: {key!r}")
        seen_keys.add(key)

        # --- label (required) ---
        label = item.get("label")
        if not label or not isinstance(label, str):
            raise ValueError(f"field_definitions[{i}].label is required and must be a non-empty string")
        if len(label) > _MAX_LABEL_LEN:
            raise ValueError(
                f"field_definitions[{i}].label must be at most {_MAX_LABEL_LEN} characters, got {len(label)}"
            )

        # --- style (optional, default 'short') ---
        style = item.get("style", "short")
        if style not in _VALID_STYLES:
            raise ValueError(f"field_definitions[{i}].style must be one of {_VALID_STYLES}, got {style!r}")

        # --- required (optional, default False) ---
        required = bool(item.get("required", False))

        # --- max_length (optional, default depends on style) ---
        default_max = _DEFAULT_MAX_LENGTH_SHORT if style == "short" else _DEFAULT_MAX_LENGTH_PARAGRAPH
        hard_max = _MAX_MAX_LENGTH_SHORT if style == "short" else _MAX_MAX_LENGTH_PARAGRAPH
        max_length = item.get("max_length", default_max)
        if not isinstance(max_length, int) or max_length < 1 or max_length > hard_max:
            raise ValueError(
                f"field_definitions[{i}].max_length must be between 1 and {hard_max}, got {max_length!r}"
            )

        # --- placeholder (optional) ---
        placeholder = item.get("placeholder")
        if placeholder is not None:
            if not isinstance(placeholder, str) or len(placeholder) > _MAX_PLACEHOLDER_LEN:
                raise ValueError(
                    f"field_definitions[{i}].placeholder must be a string of at most {_MAX_PLACEHOLDER_LEN} characters"
                )

        # Build normalized entry — strip unknown keys.
        entry: dict[str, Any] = {
            "key": key,
            "label": label,
            "style": style,
            "required": required,
            "max_length": max_length,
        }
        if placeholder is not None:
            entry["placeholder"] = placeholder

        result.append(entry)

    return result


def validate_custom_fields(
    submitted: dict[str, Any],
    definitions: list[dict[str, Any]],
) -> dict[str, str]:
    """Validate submitted custom field values against the category's field definitions.

    Args:
        submitted: The raw submitted values (key -> value).
        definitions: The normalized field definitions from validate_field_definitions().

    Returns:
        Cleaned dict of key -> trimmed string value (blank optionals omitted).

    Raises:
        ValueError: If a required field is missing/blank or a value is not a string.
    """
    if not isinstance(submitted, dict):
        raise ValueError("custom_fields must be a dict")

    def_map = {d["key"]: d for d in definitions}
    result: dict[str, str] = {}

    for defn in definitions:
        key = defn["key"]
        raw_val = submitted.get(key)

        if raw_val is None:
            if defn["required"]:
                raise ValueError(f"custom_fields: required field {defn['label']!r} ({key!r}) is missing")
            continue

        if not isinstance(raw_val, str):
            raise ValueError(f"custom_fields: value for {key!r} must be a string, got {type(raw_val).__name__}")

        val = raw_val.strip()

        if not val:
            if defn["required"]:
                raise ValueError(f"custom_fields: required field {defn['label']!r} ({key!r}) is blank")
            continue

        max_len = defn.get("max_length", 100)
        if len(val) > max_len:
            val = val[:max_len]

        result[key] = val

    return result
