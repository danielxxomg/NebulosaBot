"""GuildDBMixin — guild table operations for the Database facade."""

from __future__ import annotations

import logging
from typing import Any

from bot.constants import FALLBACK_PREFIX
from bot.core.db.base import _unwrap
from bot.models.guild import GuildConfig

logger = logging.getLogger(__name__)


class GuildDBMixin:
    """Guild config CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_guild(self: Any, guild_id: str) -> dict | None:
        """Fetch a guild row by its Discord snowflake *guild_id*.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        never been configured.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_guild(%r)", guild_id)
        response = await self._client.table("guild").select("*").eq("id", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_guild(self: Any, config: GuildConfig) -> None:
        """Insert or update a guild configuration row.

        Uses Supabase ``upsert`` so the same method handles both ``INSERT``
        (new guild) and ``UPDATE`` (changed prefix, language, etc.).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_guild(%r)", config.id)
        await self._client.table("guild").upsert(config.to_db_dict()).execute()
        if self._on_write is not None:
            await self._on_write("guild", str(config.id))

    async def ensure_guild_exists(self: Any, guild_id: str) -> None:
        """Insert default guild config only if the row doesn't exist.

        Uses ``ignore_duplicates=True`` (ON CONFLICT DO NOTHING) so existing
        custom config is preserved — unlike :meth:`upsert_guild` which
        overwrites. Used at startup to backfill guilds the bot was already a
        member of (``on_guild_join`` only fires for joins during the session).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB ensure_guild_exists(%r)", guild_id)
        await self._client.table("guild").upsert(
            {"id": guild_id, "prefix": FALLBACK_PREFIX, "language": "es", "active": True},
            on_conflict="id",
            ignore_duplicates=True,
        ).execute()

    async def update_guild_panel(self: Any, guild_id: str, message_id: str, channel_id: str) -> None:
        """Persist the ticket panel message and channel IDs on the guild row.

        Called after deploying a panel so it survives bot restarts.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_guild_panel(guild=%s, msg=%s, ch=%s)",
            guild_id,
            message_id,
            channel_id,
        )
        await self._client.table("guild").update(
            {
                "ticketPanelMessageId": message_id,
                "ticketPanelChannelId": channel_id,
            }
        ).eq("id", guild_id).execute()
