"""Webhook sync payload model — validated JSON body for /webhook/sync.

The payload carries only ``{ guild_id, entity }``. ``guild_id`` MUST be a
string or integer and is ALWAYS stored/returned as ``str`` (int is coerced
to str) so it matches the bot's universal ``str`` guild_id convention:
the DB schema stores guild ids as TEXT, cache keys are
``{guild_id}:{entity}``, and every service takes ``guild_id: str``. JSON
booleans are rejected (``bool`` is an ``int`` subclass but ``true``/``false``
are not valid guild ids). ``entity`` is optional and does not alter
invalidation behaviour (full-guild invalidation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class WebhookSyncPayload:
    """Validated payload for a cache-sync webhook request.

    Attributes:
        guild_id: Discord guild id whose cache entries are invalidated.
            Always a ``str`` to match the bot's guild_id convention.
        entity: Optional hint of which entity changed (e.g. ``guild_config``).
            Does not alter invalidation granularity — full guild is evicted.
    """

    guild_id: str
    entity: str = ""

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> WebhookSyncPayload:
        """Parse and validate *raw* JSON bytes into a payload.

        Args:
            raw: The raw request body bytes.

        Returns:
            A validated :class:`WebhookSyncPayload` with ``guild_id`` as
            ``str`` (an integer ``guild_id`` is coerced to ``str``).

        Raises:
            ValueError: If the body is not valid JSON, is not a JSON object,
                lacks ``guild_id``, or ``guild_id`` is not a string/integer
                (booleans are rejected).
        """
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Malformed JSON body") from exc

        if not isinstance(data, dict):
            raise ValueError("Payload must be a JSON object")

        if "guild_id" not in data:
            raise ValueError("Missing required field: guild_id")

        guild_id = data["guild_id"]
        # bool is a subclass of int — reject JSON true/false explicitly first.
        if isinstance(guild_id, bool) or not isinstance(guild_id, (str, int)):
            raise ValueError("guild_id must be a string or integer")
        guild_id = str(guild_id)  # coerce int -> str; str stays str

        entity = data.get("entity", "")
        if not isinstance(entity, str):
            entity = str(entity)

        return cls(guild_id=guild_id, entity=entity)
