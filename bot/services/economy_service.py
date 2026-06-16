"""EconomyService — guild economy: XP, levels, daily claims, leaderboards.

Pure business logic for the economy system.  All DB access is delegated to
the database layer; all caching is delegated to ``TTLCache``.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database

logger = logging.getLogger(__name__)

# Default economy values used when no economy_config row exists.
DEFAULT_DAILY_REWARD = 100
DEFAULT_DAILY_COOLDOWN_HOURS = 24
DEFAULT_XP_PER_MESSAGE = 10
DEFAULT_XP_COOLDOWN_SECONDS = 60
DEFAULT_LEVEL_BASE_XP = 100
DEFAULT_LEVEL_MULTIPLIER = 1.5

LEADERBOARD_CACHE_TTL = 30  # seconds
MAX_STREAK = 7
STREAK_BONUS_MULTIPLIER = 0.10


class EconomyService:
    """Handles all economy business logic: XP, coins, levels, daily, leaderboards.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
    """

    __slots__ = ("_db", "_cache")

    def __init__(self, db: Database, cache: TTLCache) -> None:
        self._db = db
        self._cache = cache

    # ------------------------------------------------------------------
    # Level Formula (pure functions — no side effects)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_xp_for_level(
        level: int, base: int = DEFAULT_LEVEL_BASE_XP, multiplier: float = DEFAULT_LEVEL_MULTIPLIER
    ) -> float:
        """Return the total XP threshold needed to reach the given *level*.

        Formula: ``base * multiplier ^ level``.

        Level 0 threshold is always 0.
        """
        if level <= 0:
            return 0
        return base * (multiplier ** level)

    @staticmethod
    def compute_level(
        xp: int, base: int = DEFAULT_LEVEL_BASE_XP, multiplier: float = DEFAULT_LEVEL_MULTIPLIER
    ) -> int:
        """Return the highest level whose XP threshold does not exceed *xp*.

        Works by incrementing level while the threshold is ≤ xp.
        O(log(xp)) in practice since threshold grows exponentially.
        """
        level = 0
        while True:
            threshold = EconomyService.compute_xp_for_level(level + 1, base, multiplier)
            if xp < threshold:
                return level
            level += 1

    @staticmethod
    def xp_progress(
        xp: int,
        level: int,
        base: int = DEFAULT_LEVEL_BASE_XP,
        multiplier: float = DEFAULT_LEVEL_MULTIPLIER,
    ) -> tuple[float, float]:
        """Return (xp_current, xp_needed) for progress toward the next level.

        *xp_current* is how much XP the member has earned at the current
        level.  *xp_needed* is the total XP needed to reach the next level
        from the start of the current level.
        """
        current_threshold = EconomyService.compute_xp_for_level(level, base, multiplier)
        next_threshold = EconomyService.compute_xp_for_level(level + 1, base, multiplier)
        xp_current = xp - current_threshold
        xp_needed = next_threshold - current_threshold
        return xp_current, xp_needed

    # ------------------------------------------------------------------
    # XP Gain
    # ------------------------------------------------------------------

    async def gain_xp(
        self, guild_id: str, user_id: str
    ) -> tuple[int, int, bool]:
        """Award XP for a message, respecting cooldown.

        Returns:
            ``(new_xp, new_level, leveled_up)``.  If the member is on
            cooldown, returns ``(0, 0, False)``.
        """
        config = await self._db.get_economy_config(guild_id)
        xp_per_message = config.get("xpPerMessage", DEFAULT_XP_PER_MESSAGE) if config else DEFAULT_XP_PER_MESSAGE
        xp_cooldown_seconds = config.get("xpCooldownSeconds", DEFAULT_XP_COOLDOWN_SECONDS) if config else DEFAULT_XP_COOLDOWN_SECONDS
        level_base = config.get("levelBaseXp", DEFAULT_LEVEL_BASE_XP) if config else DEFAULT_LEVEL_BASE_XP
        level_mult = config.get("levelMultiplier", DEFAULT_LEVEL_MULTIPLIER) if config else DEFAULT_LEVEL_MULTIPLIER

        member = await self._db.get_member(guild_id, user_id)

        # Cooldown check — use lastXpGain timestamp.
        if member is not None and member.get("lastXpGain") is not None:
            last_gain = member["lastXpGain"]
            now = datetime.now(timezone.utc)
            elapsed = (now - last_gain).total_seconds()
            if elapsed < xp_cooldown_seconds:
                logger.debug(
                    "gain_xp(%s/%s): on cooldown (%.1fs < %ds)",
                    guild_id, user_id, elapsed, xp_cooldown_seconds,
                )
                return (0, 0, False)

        # Award XP.
        old_level = member.get("level", 0) if member else 0
        new_total_xp = (member.get("xp", 0) if member else 0) + xp_per_message

        # Compute new level from total XP.
        new_level = self.compute_level(new_total_xp, level_base, level_mult)
        leveled_up = new_level > old_level

        # Persist XP, level, and lastXpGain timestamp in one call.
        updated = await self._db.update_member_xp(
            guild_id, user_id, xp_per_message, new_level=new_level
        )
        new_xp = updated["xp"]

        # Invalidate leaderboard cache on any XP gain.
        self._invalidate_leaderboard_cache(guild_id)

        logger.debug(
            "gain_xp(%s/%s): +%d XP → %d XP (level %d, leveled_up=%s)",
            guild_id, user_id, xp_per_message, new_xp, new_level, leveled_up,
        )
        return (new_xp, new_level, leveled_up)

    # ------------------------------------------------------------------
    # Daily Claim
    # ------------------------------------------------------------------

    async def claim_daily(
        self, guild_id: str, user_id: str
    ) -> tuple[bool, int, int]:
        """Attempt a daily coin claim with streak tracking.

        Returns:
            ``(success, coins_awarded, current_streak)``.
            If on cooldown, ``success`` is ``False`` and ``coins_awarded`` is 0.
        """
        config = await self._db.get_economy_config(guild_id)
        daily_reward = config.get("dailyReward", DEFAULT_DAILY_REWARD) if config else DEFAULT_DAILY_REWARD
        cooldown_hours = config.get("dailyCooldownHours", DEFAULT_DAILY_COOLDOWN_HOURS) if config else DEFAULT_DAILY_COOLDOWN_HOURS

        member = await self._db.get_member(guild_id, user_id)
        now = datetime.now(timezone.utc)

        # Helper: parse a DB timestamp (may be str or datetime).
        def _to_datetime(value) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            # Assume ISO-8601 string.
            try:
                return datetime.fromisoformat(str(value))
            except (ValueError, TypeError):
                return None

        if member is not None and member.get("lastDaily") is not None:
            last_daily = _to_datetime(member["lastDaily"])
            if last_daily is not None:
                elapsed = (now - last_daily).total_seconds()
                cooldown_seconds = cooldown_hours * 3600
                if elapsed < cooldown_seconds:
                    logger.debug(
                        "claim_daily(%s/%s): on cooldown (%.1fh < %dh)",
                        guild_id, user_id, elapsed / 3600, cooldown_hours,
                    )
                    streak = member.get("dailyStreak", 0)
                    return (False, 0, streak)

        # Determine streak.
        old_streak = member.get("dailyStreak", 0) if member else 0
        last_reset = member.get("lastDailyReset") if member else None
        last_reset_dt = _to_datetime(last_reset) if last_reset else None

        if last_reset_dt is not None:
            reset_date = last_reset_dt.date()
            today = now.date()
            yesterday = (now - timedelta(days=1)).date()

            if reset_date == today:
                # Same day — should be caught by cooldown above.
                new_streak = old_streak
            elif reset_date == yesterday:
                # Consecutive day.
                new_streak = min(old_streak + 1, MAX_STREAK)
            else:
                # Broken streak.
                new_streak = 1
        else:
            # First ever claim.
            new_streak = 1

        # Reward = dailyReward * (1 + 0.1 * min(streak - 1, 6))
        streak_for_bonus = min(new_streak, MAX_STREAK) - 1
        coins_awarded = int(daily_reward * (1 + STREAK_BONUS_MULTIPLIER * streak_for_bonus))

        now_iso = now.isoformat()
        result = await self._db.update_member_daily(
            guild_id, user_id,
            coin_delta=coins_awarded,
            streak=new_streak,
            last_daily_reset=now_iso,
            last_daily=now_iso,
        )

        logger.info(
            "claim_daily(%s/%s): awarded %d coins, streak=%d",
            guild_id, user_id, coins_awarded, new_streak,
        )
        return (True, coins_awarded, new_streak)

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    async def get_balance(self, guild_id: str, user_id: str) -> int:
        """Return the member's current coin balance (0 if no row exists)."""
        member = await self._db.get_member(guild_id, user_id)
        if member is None:
            return 0
        return member.get("coins", 0)

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    async def get_leaderboard(
        self, guild_id: str, sort_by: str = "xp", limit: int = 10, offset: int = 0
    ) -> list[dict]:
        """Return leaderboard entries for a guild, with caching.

        Cache key: ``{guild_id}:leaderboard:{sort_by}`` with 30s TTL.
        Cache hit returns cached data; cache miss queries DB and populates.
        """
        cache_key = f"{guild_id}:leaderboard:{sort_by}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("get_leaderboard(%s): cache hit", cache_key)
            return cached

        logger.debug("get_leaderboard(%s): cache miss — querying DB", cache_key)
        rows = await self._db.get_leaderboard(guild_id, sort_by, limit, offset)
        self._cache.set(cache_key, rows, ttl=LEADERBOARD_CACHE_TTL)
        return rows

    # ------------------------------------------------------------------
    # Rank Info
    # ------------------------------------------------------------------

    async def get_rank_info(
        self, guild_id: str, user_id: str
    ) -> dict | None:
        """Return rank card data for a member: xp, level, coins, rank, progress.

        Returns ``None`` if the member has no row.
        """
        member = await self._db.get_member(guild_id, user_id)
        if member is None:
            return None

        config = await self._db.get_economy_config(guild_id)
        level_base = config.get("levelBaseXp", DEFAULT_LEVEL_BASE_XP) if config else DEFAULT_LEVEL_BASE_XP
        level_mult = config.get("levelMultiplier", DEFAULT_LEVEL_MULTIPLIER) if config else DEFAULT_LEVEL_MULTIPLIER

        xp = member.get("xp", 0)
        level = member.get("level", 0)
        coins = member.get("coins", 0)

        rank = await self._db.get_member_rank(guild_id, user_id, sort_by="xp")
        if rank is None:
            rank = 0

        xp_current, xp_needed = self.xp_progress(xp, level, level_base, level_mult)

        return {
            "xp": xp,
            "level": level,
            "coins": coins,
            "rank": rank,
            "xp_current": xp_current,
            "xp_needed": xp_needed,
        }

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def get_economy_config(self, guild_id: str) -> dict | None:
        """Return the economy configuration for *guild_id*, or ``None``.

        Thin wrapper over ``Database.get_economy_config()`` so callers
        never need to reach into the private ``_db`` attribute.
        """
        return await self._db.get_economy_config(guild_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _invalidate_leaderboard_cache(self, guild_id: str) -> None:
        """Invalidate all leaderboard cache keys for a guild."""
        self._cache.invalidate(f"{guild_id}:leaderboard:xp")
        self._cache.invalidate(f"{guild_id}:leaderboard:coins")
