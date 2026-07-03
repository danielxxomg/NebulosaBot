"""Unit tests for bot.webhook.models.WebhookSyncPayload.

Covers the cache-sync-webhook spec — Payload validation requirement.
The bot uses ``guild_id`` as ``str`` everywhere (DB schema stores guild
ids as TEXT, cache keys are ``{guild_id}:{entity}``, services take
``str``). The webhook payload MUST accept ``guild_id`` as ``str | int``
and STORE/RETURN it as ``str`` (int is coerced to str). JSON booleans
MUST still be rejected (``bool`` is an ``int`` subclass; ``true``/``false``
are not valid guild ids).
"""

from __future__ import annotations

import json

import pytest

from bot.webhook.models import WebhookSyncPayload

# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------


class TestWebhookSyncPayloadDataclass:
    """Verify the dataclass fields and defaults.

    ``guild_id`` is stored as ``str`` to match the bot's universal str
    convention (DB TEXT, cache keys, services).
    """

    def test_construct_with_guild_id_and_entity(self) -> None:
        payload = WebhookSyncPayload(guild_id="12345", entity="guild_config")
        assert payload.guild_id == "12345"
        assert payload.entity == "guild_config"

    def test_entity_defaults_to_empty_string(self) -> None:
        payload = WebhookSyncPayload(guild_id="12345")
        assert payload.entity == ""


# ---------------------------------------------------------------------------
# from_json_bytes — happy path + triangulation
# ---------------------------------------------------------------------------


class TestFromJsonBytes:
    """Verify JSON byte parsing and validation per spec scenarios."""

    def test_valid_payload_with_entity(self) -> None:
        body = json.dumps({"guild_id": 12345, "entity": "guild_config"}).encode()
        payload = WebhookSyncPayload.from_json_bytes(body)

        assert payload.guild_id == "12345"
        assert payload.entity == "guild_config"

    def test_valid_payload_without_entity(self) -> None:
        """entity is optional per spec — defaults to empty string."""
        body = json.dumps({"guild_id": 12345}).encode()
        payload = WebhookSyncPayload.from_json_bytes(body)

        assert payload.guild_id == "12345"
        assert payload.entity == ""

    def test_string_guild_id_accepted_as_str(self) -> None:
        """A STRING guild_id MUST be accepted and returned as str.

        The dashboard reads guild_id from Supabase as TEXT and sends
        ``{"guild_id": "123"}``. Rejecting it (the old int-only behaviour)
        caused a 400 so invalidate_guild was never called -> stale cache.
        """
        body = json.dumps({"guild_id": "12345"}).encode()
        payload = WebhookSyncPayload.from_json_bytes(body)

        assert payload.guild_id == "12345"
        assert isinstance(payload.guild_id, str)

    def test_integer_guild_id_coerced_to_str(self) -> None:
        """An INTEGER guild_id MUST be accepted and coerced to str.

        Triangulation: a different input shape (int) must still produce the
        same str contract, forcing real coercion logic rather than a
        pass-through.
        """
        body = json.dumps({"guild_id": 987654321}).encode()
        payload = WebhookSyncPayload.from_json_bytes(body)

        assert payload.guild_id == "987654321"
        assert isinstance(payload.guild_id, str)

    def test_string_guild_id_with_entity_accepted(self) -> None:
        """A STRING guild_id with an entity MUST be accepted end-to-end."""
        body = json.dumps({"guild_id": "42", "entity": "economy_config"}).encode()
        payload = WebhookSyncPayload.from_json_bytes(body)

        assert payload.guild_id == "42"
        assert payload.entity == "economy_config"

    def test_boolean_guild_id_rejected(self) -> None:
        """JSON ``true``/``false`` MUST be rejected (bool is an int subclass)."""
        body = json.dumps({"guild_id": True}).encode()

        with pytest.raises(ValueError):
            WebhookSyncPayload.from_json_bytes(body)

    def test_missing_guild_id_raises_value_error(self) -> None:
        """Spec: missing guild_id rejected -> ValueError (endpoint returns 400)."""
        body = json.dumps({"entity": "guild_config"}).encode()

        with pytest.raises(ValueError):
            WebhookSyncPayload.from_json_bytes(body)

    def test_malformed_json_raises_value_error(self) -> None:
        """Spec: malformed JSON body -> ValueError (endpoint returns 400)."""
        body = b"{not valid json"

        with pytest.raises(ValueError):
            WebhookSyncPayload.from_json_bytes(body)
