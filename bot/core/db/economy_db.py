"""EconomyDBMixin — economy_config + member economy operations for the Database facade."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class EconomyDBMixin:
    """Economy config and member economy (XP, coins, daily) operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def get_economy_config(self: Any, guild_id: str) -> dict | None:
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
    ) -> dict:
        """Increment a member's XP and return the updated row.

        Optionally updates the stored level and sets ``lastXpGain`` to now.
        If the member does not have a row yet, an initial row is upserted.
        Returns the camelCase row dict with at least ``xp`` and ``level``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        now = datetime.now(UTC).isoformat()
        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_xp_val = max(existing.get("xp", 0) + xp_delta, 0)
            level = new_level if new_level is not None else existing.get("level", 0)
            logger.debug(
                "DB update_member_xp(%s/%s): xp %d → %d, level=%d",
                guild_id,
                user_id,
                existing.get("xp", 0),
                new_xp_val,
                level,
            )
            await self._client.table("member").update(
                {
                    "xp": new_xp_val,
                    "level": level,
                    "lastXpGain": now,
                }
            ).eq("guildId", guild_id).eq("userId", user_id).execute()
            return {"xp": new_xp_val, "level": level}
        else:
            level = new_level if new_level is not None else 0
            logger.debug(
                "DB update_member_xp(%s/%s): new member, xp=%d",
                guild_id,
                user_id,
                xp_delta,
            )
            await self._client.table("member").upsert(
                {
                    "guildId": guild_id,
                    "userId": user_id,
                    "xp": max(xp_delta, 0),
                    "level": level,
                    "lastXpGain": now,
                }
            ).execute()
            return {"xp": xp_delta, "level": level}

    async def update_member_coins(self: Any, guild_id: str, user_id: str, coin_delta: int) -> dict:
        """Increment a member's coins and return the updated row.

        If the member does not have a row yet, an initial row with
        ``coins = coin_delta`` is upserted.  Returns the camelCase row
        dict with at least ``coins``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_coins = max(existing.get("coins", 0) + coin_delta, 0)
            logger.debug(
                "DB update_member_coins(%s/%s): coins %d → %d",
                guild_id,
                user_id,
                existing.get("coins", 0),
                new_coins,
            )
            await self._client.table("member").update({"coins": new_coins}).eq("guildId", guild_id).eq(
                "userId", user_id
            ).execute()
            return {"coins": new_coins}
        else:
            logger.debug(
                "DB update_member_coins(%s/%s): new member, coins=%d",
                guild_id,
                user_id,
                coin_delta,
            )
            await self._client.table("member").upsert(
                {
                    "guildId": guild_id,
                    "userId": user_id,
                    "coins": max(coin_delta, 0),
                }
            ).execute()
            return {"coins": coin_delta}

    async def update_member_daily(
        self: Any,
        guild_id: str,
        user_id: str,
        coin_delta: int,
        streak: int,
        last_daily_reset: str | None,
        last_daily: str | None,
    ) -> dict:
        """Apply a daily claim: increment coins, set streak + timestamps.

        If the member does not have a row yet, an initial row is upserted.
        Returns the camelCase row dict with at least ``coins``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_coins = max(existing.get("coins", 0) + coin_delta, 0)
            logger.debug(
                "DB update_member_daily(%s/%s): coins %d → %d, streak=%d",
                guild_id,
                user_id,
                existing.get("coins", 0),
                new_coins,
                streak,
            )
            await self._client.table("member").update(
                {
                    "coins": new_coins,
                    "dailyStreak": streak,
                    "lastDailyReset": last_daily_reset,
                    "lastDaily": last_daily,
                }
            ).eq("guildId", guild_id).eq("userId", user_id).execute()
            return {"coins": new_coins}
        else:
            logger.debug(
                "DB update_member_daily(%s/%s): new member, coins=%d, streak=%d",
                guild_id,
                user_id,
                coin_delta,
                streak,
            )
            await self._client.table("member").upsert(
                {
                    "guildId": guild_id,
                    "userId": user_id,
                    "coins": max(coin_delta, 0),
                    "dailyStreak": streak,
                    "lastDailyReset": last_daily_reset,
                    "lastDaily": last_daily,
                }
            ).execute()
            return {"coins": coin_delta}

    async def get_leaderboard(
        self: Any,
        guild_id: str,
        sort_by: str = "xp",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
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
