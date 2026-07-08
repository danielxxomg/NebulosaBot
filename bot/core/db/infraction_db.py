"""InfractionDBMixin — infraction table operations for the Database facade."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class InfractionDBMixin:
    """Infraction CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def insert_infraction(
        self: Any,
        guild_id: str,
        target_id: str,
        moderator_id: str,
        type: str,
        reason: str,
        expires_at: str | None = None,
    ) -> dict:
        """Insert a moderation infraction and return the persisted row.

        Generates a v4 UUID for the primary key.  The ``created_at``
        timestamp is set by the database default clause.

        Returns the camelCase row dict (matching ``Infraction.from_db_row``).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        infraction_id = str(uuid.uuid4())
        row = {
            "id": infraction_id,
            "guildId": guild_id,
            "targetId": target_id,
            "moderatorId": moderator_id,
            "type": type,
            "reason": reason,
            "active": True,
            "expiresAt": expires_at,
        }
        logger.debug("DB insert_infraction(%s) type=%s", infraction_id, type)
        response = await self._client.table("infraction").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

    async def get_infractions(
        self: Any,
        guild_id: str,
        target_id: str,
        type: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        """Return infraction rows for a guild member, with optional filters.

        Args:
            guild_id: Discord guild snowflake.
            target_id: Discord target user snowflake.
            type: Optional infraction type filter (``"WARN"``, ``"MUTE"``, …).
            after: Optional ISO-8601 datetime string; only rows with
                ``createdAt >= after`` are returned.

        Returns:
            List of camelCase row dicts ordered by ``createdAt`` descending.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        query = (
            self._client.table("infraction")
            .select("*")
            .eq("guildId", guild_id)
            .eq("targetId", target_id)
            .order("createdAt", desc=True)
        )
        if type is not None:
            query = query.eq("type", type)
        if after is not None:
            query = query.gte("createdAt", after)

        logger.debug("DB get_infractions(guild=%s, target=%s, type=%s)", guild_id, target_id, type)
        response = await query.execute()
        return _unwrap(response)

    async def get_active_warnings(self: Any, guild_id: str, target_id: str) -> list[dict]:
        """Return all active WARN infractions for a guild member.

        Convenience wrapper around ``get_infractions`` with ``type="WARN"``
        and an explicit ``active`` filter.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_active_warnings(guild=%s, target=%s)", guild_id, target_id)
        response = await (
            self._client.table("infraction")
            .select("*")
            .eq("guildId", guild_id)
            .eq("targetId", target_id)
            .eq("type", "WARN")
            .eq("active", True)
            .order("createdAt", desc=True)
            .execute()
        )
        return _unwrap(response)

    async def deactivate_infraction(self: Any, infraction_id: str) -> None:
        """Soft-delete an infraction by setting ``active = false``."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB deactivate_infraction(%s)", infraction_id)
        await self._client.table("infraction").update({"active": False}).eq("id", infraction_id).execute()
