"""MemberDBMixin — member table operations for the Database facade."""

from __future__ import annotations

import logging
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class MemberDBMixin:
    """Member read/update operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_member(self: Any, guild_id: str, user_id: str) -> dict | None:
        """Fetch a member row by guild and user snowflake.

        Returns the camelCase row dict, or ``None`` if the member has no
        row yet (e.g. never warned, no XP).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_member(guild=%s, user=%s)", guild_id, user_id)
        response = (
            await self._client.table("member")
            .select("*")
            .eq("guildId", guild_id)
            .eq("userId", user_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def update_member_warnings(self: Any, guild_id: str, user_id: str, delta: int) -> None:
        """Increment or decrement the warnings counter for a member.

        If the member does not have a row yet, an initial row with
        ``warnings = delta`` is upserted.  This is safe for the first
        warn action on a previously unknown member.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_warnings = max(existing.get("warnings", 0) + delta, 0)
            logger.debug(
                "DB update_member_warnings(%s/%s): %d → %d",
                guild_id,
                user_id,
                existing.get("warnings", 0),
                new_warnings,
            )
            await self._client.table("member").update({"warnings": new_warnings}).eq("guildId", guild_id).eq(
                "userId", user_id
            ).execute()
        else:
            # First interaction — create the row.
            initial = max(delta, 0)
            logger.debug(
                "DB update_member_warnings(%s/%s): new member, warnings=%d",
                guild_id,
                user_id,
                initial,
            )
            await self._client.table("member").upsert(
                {
                    "guildId": guild_id,
                    "userId": user_id,
                    "warnings": initial,
                }
            ).execute()
