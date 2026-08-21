"""GreetingDBMixin — greeting_config table operations for the Database facade."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from bot.core.db.base import _unwrap
from bot.models.greeting_config import GreetingConfig

logger = logging.getLogger(__name__)

# Explicit column list for greeting_config — avoids select('*') bloat
# (D12: scoped to greeting for PR1; economy/infraction deferred to Cycle 3).
_GREETING_CONFIG_COLUMNS = (
    "guildId",
    "welcomeEnabled",
    "goodbyeEnabled",
    "welcomeChannelId",
    "goodbyeChannelId",
    "onboardingChannelId",
    "welcomeMessage",
    "goodbyeMessage",
    "welcomeCardEnabled",
    "goodbyeCardEnabled",
    "updatedAt",
    "themeId",
)


def _is_unique_violation(exc: BaseException) -> bool:
    """Return True if *exc* is a Supabase/PostgREST 23505 unique_violation.

    supabase-py raises ``PostgrestAPIError`` carrying a ``code`` attribute.
    We duck-type on ``code == "23505"`` so tests can emulate without the
    concrete exception class.
    """
    return getattr(exc, "code", None) == "23505"


class GreetingDBMixin:
    """Greeting config CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_greeting_config(self: Any, guild_id: str) -> dict[str, Any] | None:
        """Fetch a greeting_config row by guild ID.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        no greeting configuration yet.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB get_greeting_config(%r)", guild_id)
        cols = ",".join(_GREETING_CONFIG_COLUMNS)
        response = await self._client.table("greeting_config").select(cols).eq("guildId", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_greeting_config(self: Any, guild_id: str, config: GreetingConfig) -> None:
        """Insert or update a greeting_config row.

        Args:
            guild_id: The guild snowflake — used as the upsert key.
            config: A :class:`~bot.models.greeting_config.GreetingConfig`
                instance whose ``to_db_dict()`` produces camelCase keys,
                including the nullable ``onboardingChannelId`` field.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB upsert_greeting_config(%r)", guild_id)
        payload = config.to_db_dict()
        payload["updatedAt"] = datetime.now(UTC).isoformat()
        # 23505 handling: keyed by guildId (unique), a concurrent writer may
        # win the upsert race — same config, so treat as no-op (D13).
        try:
            await self._client.table("greeting_config").upsert(payload, on_conflict="guildId").execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                logger.debug(
                    "upsert_greeting_config 23505 for %s — concurrent writer won, no-op",
                    guild_id,
                )
            else:
                raise
        if self._on_write is not None:
            await self._on_write("greeting_config", str(guild_id))
