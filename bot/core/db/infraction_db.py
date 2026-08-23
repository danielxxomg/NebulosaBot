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
        type: str,  # noqa: A002 -- DB column `type` is external contract
        reason: str,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a moderation infraction and return the persisted row.

        Generates a v4 UUID for the primary key.  The ``created_at``
        timestamp is set by the database default clause.

        Returns the camelCase row dict (matching ``Infraction.from_db_row``).
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

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
        type: str | None = None,  # noqa: A002 -- DB column `type` is external contract
        after: str | None = None,
    ) -> list[dict[str, Any]]:
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
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        query = (
            self._client
            .table("infraction")
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

    async def get_active_warnings(self: Any, guild_id: str, target_id: str) -> list[dict[str, Any]]:
        """Return all active WARN infractions for a guild member.

        Convenience wrapper around ``get_infractions`` with ``type="WARN"``
        and an explicit ``active`` filter.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB get_active_warnings(guild=%s, target=%s)", guild_id, target_id)
        response = await (
            self._client
            .table("infraction")
            .select("*")
            .eq("guildId", guild_id)
            .eq("targetId", target_id)
            .eq("type", "WARN")
            .eq("active", True)
            .order("createdAt", desc=True)
            .execute()
        )
        return _unwrap(response)

    async def deactivate_infraction(self: Any, guild_id: str, infraction_id: str) -> None:
        """Soft-delete an infraction by setting ``active = false``.

        Scoped by *guild_id* so one guild cannot deactivate another
        guild's infractions even if the infraction ID is known.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB deactivate_infraction(%s, %s)", guild_id, infraction_id)
        await (
            self._client
            .table("infraction")
            .update({"active": False})
            .eq("guildId", guild_id)
            .eq("id", infraction_id)
            .execute()
        )

    async def get_expired_warns(self: Any, guild_id: str) -> list[dict[str, Any]]:
        """Return WARN infractions older than 30 days for a guild.

        Guild-scoped; only ``type='WARN'`` + ``active`` rows with
        ``createdAt < NOW() - 30d`` are returned. Uses explicit column
        selection (no ``select("*")``) for the partial index path.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        logger.debug("DB get_expired_warns(guild=%s, cutoff=%s)", guild_id, cutoff)
        response = await (
            self._client
            .table("infraction")
            .select("id", "guildId", "targetId", "type", "active", "createdAt")
            .eq("guildId", guild_id)
            .eq("type", "WARN")
            .eq("active", True)
            .lt("createdAt", cutoff)
            .execute()
        )
        return _unwrap(response)

    async def get_expired_tempbans(self: Any, guild_id: str) -> list[dict[str, Any]]:
        """Return active BAN infractions whose ``expiresAt <= NOW()``.

        Guild-scoped; only ``type='BAN'`` + ``active`` rows with a
        non-null ``expiresAt`` at or before now are returned. Uses
        explicit column selection (no ``select("*")``).
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        from datetime import UTC, datetime

        now_iso = datetime.now(UTC).isoformat()
        logger.debug("DB get_expired_tempbans(guild=%s, now=%s)", guild_id, now_iso)

        builder = self._client.table("infraction").select("id", "guildId", "targetId", "type", "active", "expiresAt")
        builder = builder.eq("guildId", guild_id).eq("type", "BAN").eq("active", True)
        # lte preferred; lt fallback for FakeQueryBuilder in tests
        lte_fn = getattr(builder, "lte", None)
        lt_fn = getattr(builder, "lt", None)
        if callable(lte_fn):
            builder = lte_fn("expiresAt", now_iso)
        elif callable(lt_fn):
            builder = lt_fn("expiresAt", now_iso)
        else:
            builder = builder.eq("expiresAt", now_iso)
        neq_fn = getattr(builder, "neq", None)
        if callable(neq_fn):
            # Exclude permanent bans (NULL expiresAt). The callable() guard above
            # proves neq is a real builder method; let any error propagate rather
            # than swallowing it with a broad suppress.
            builder = neq_fn("expiresAt", None)
        response = await builder.execute()
        return _unwrap(response)
