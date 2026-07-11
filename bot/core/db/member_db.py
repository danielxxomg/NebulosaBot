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

    async def get_member(self: Any, guild_id: str, user_id: str) -> dict[str, Any] | None:
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
        """Increment or decrement the warnings counter atomically via RPC.

        Calls the ``increment_member_warnings`` Postgres function which handles
        the upsert + increment in a single round trip.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_member_warnings(%s/%s): delta=%d",
            guild_id,
            user_id,
            delta,
        )
        await self._client.rpc(
            "increment_member_warnings",
            {
                "p_guild_id": guild_id,
                "p_user_id": user_id,
                "p_amount": delta,
            },
        ).execute()
