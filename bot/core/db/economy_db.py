"""EconomyDBMixin — economy_config + member economy operations for the Database facade."""

from __future__ import annotations

import logging
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class EconomyDBMixin:
    """Economy config and member economy (XP, coins, daily) operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_economy_config(self: Any, guild_id: str) -> dict[str, Any] | None:
        """Fetch an economy_config row by guild ID.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        no economy configuration yet.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_economy_config(%r)", guild_id)
        response = await self._client.table("economy_config").select("*").eq("guildId", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_economy_config(self: Any, config: Any) -> None:
        """Insert or update an economy_config row.

        Args:
            config: An :class:`~bot.models.economy_config.EconomyConfig`
                instance whose ``to_db_dict()`` produces camelCase keys.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_economy_config(%r)", config.guild_id)
        await self._client.table("economy_config").upsert(config.to_db_dict()).execute()

    async def update_member_xp(
        self: Any,
        guild_id: str,
        user_id: str,
        xp_delta: int,
        new_level: int | None = None,
    ) -> dict[str, Any]:
        """Increment a member's XP atomically via RPC.

        Calls the ``increment_member_xp`` Postgres function which handles
        the upsert + increment in a single round trip.  The level is NOT
        set by the RPC — it is computed by the caller (EconomyService)
        from guild economy config thresholds.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_member_xp(%s/%s): delta=%d",
            guild_id,
            user_id,
            xp_delta,
        )
        response = await self._client.rpc(
            "increment_member_xp",
            {
                "p_guild_id": guild_id,
                "p_user_id": user_id,
                "p_amount": xp_delta,
            },
        ).execute()
        rows = _unwrap(response)
        if not rows:
            return {"xp": 0, "level": 0}
        result = rows[0]
        # If caller provides a level override, update it separately.
        if new_level is not None:
            await self._client.table("member").update(
                {"level": new_level}
            ).eq("guildId", guild_id).eq("userId", user_id).execute()
            result["level"] = new_level
        return result

    async def update_member_coins(self: Any, guild_id: str, user_id: str, coin_delta: int) -> dict[str, Any]:
        """Increment a member's coins atomically via RPC.

        Calls the ``increment_member_coins`` Postgres function which handles
        the upsert + increment in a single round trip.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_member_coins(%s/%s): delta=%d",
            guild_id,
            user_id,
            coin_delta,
        )
        response = await self._client.rpc(
            "increment_member_coins",
            {
                "p_guild_id": guild_id,
                "p_user_id": user_id,
                "p_amount": coin_delta,
            },
        ).execute()
        rows = _unwrap(response)
        if not rows:
            return {"coins": 0}
        return rows[0]

    async def update_member_daily(
        self: Any,
        guild_id: str,
        user_id: str,
        coin_delta: int,
        streak: int,
        last_daily_reset: str | None,
        last_daily: str | None,
    ) -> dict[str, Any]:
        """Apply a daily claim atomically via RPC.

        Calls the ``set_member_daily`` Postgres function which handles
        the upsert + coin increment + streak + timestamps in a single
        round trip.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_member_daily(%s/%s): coins_delta=%d, streak=%d",
            guild_id,
            user_id,
            coin_delta,
            streak,
        )
        response = await self._client.rpc(
            "set_member_daily",
            {
                "p_guild_id": guild_id,
                "p_user_id": user_id,
                "p_coin_amount": coin_delta,
                "p_streak": streak,
                "p_last_daily_reset": last_daily_reset,
                "p_last_daily": last_daily,
            },
        ).execute()
        rows = _unwrap(response)
        if not rows:
            return {"coins": 0, "dailyStreak": streak, "lastDailyReset": last_daily_reset, "lastDaily": last_daily}
        return rows[0]

    async def get_leaderboard(
        self: Any,
        guild_id: str,
        sort_by: str = "xp",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return leaderboard rows for a guild, sorted by *sort_by* descending.

        Args:
            guild_id: Discord guild snowflake.
            sort_by: Column to sort by (``"xp"`` or ``"coins"``).
            limit: Maximum rows to return.
            offset: Pagination offset.

        Returns:
            List of camelCase row dicts ordered by *sort_by* DESC.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        column = "xp" if sort_by == "xp" else "coins"
        logger.debug(
            "DB get_leaderboard(guild=%s, sort=%s, limit=%d, offset=%d)",
            guild_id,
            column,
            limit,
            offset,
        )
        response = await (
            self._client.table("member")
            .select("guildId,userId,xp,level,coins")
            .eq("guildId", guild_id)
            .order(column, desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        return _unwrap(response)

    async def get_member_rank(self: Any, guild_id: str, user_id: str, sort_by: str = "xp") -> int | None:
        """Return the 1-indexed rank position of a member on the leaderboard.

        Counts how many members have a higher *sort_by* value than the
        target member.  Returns ``None`` if the member has no row.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        member = await self.get_member(guild_id, user_id)
        if member is None:
            return None

        column = "xp" if sort_by == "xp" else "coins"
        target_value = member.get(column, 0)
        if target_value == 0:
            return 0

        logger.debug(
            "DB get_member_rank(guild=%s, user=%s, sort=%s)",
            guild_id,
            user_id,
            column,
        )
        # Count members with higher value → rank = count + 1
        response = await (
            self._client.table("member")
            .select("userId", count="exact")
            .eq("guildId", guild_id)
            .gt(column, target_value)
            .execute()
        )
        rows = _unwrap(response)
        count = response.count if hasattr(response, "count") else len(rows)
        return count + 1
