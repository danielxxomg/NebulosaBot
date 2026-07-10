"""GreetingDBMixin — greeting_config table operations for the Database facade."""

from __future__ import annotations

import logging
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class GreetingDBMixin:
    """Greeting config CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_greeting_config(self: Any, guild_id: str) -> dict | None:
        """Fetch a greeting_config row by guild ID.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        no greeting configuration yet.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_greeting_config(%r)", guild_id)
        response = await self._client.table("greeting_config").select("*").eq("guildId", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_greeting_config(self: Any, guild_id: str, config: Any) -> None:
        """Insert or update a greeting_config row.

        Args:
            guild_id: The guild snowflake — used as the upsert key.
            config: A :class:`~bot.models.greeting_config.GreetingConfig`
                instance whose ``to_db_dict()`` produces camelCase keys.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_greeting_config(%r)", guild_id)
        await self._client.table("greeting_config").upsert(config.to_db_dict()).execute()
        if self._on_write is not None:
            await self._on_write("greeting_config", str(guild_id))
