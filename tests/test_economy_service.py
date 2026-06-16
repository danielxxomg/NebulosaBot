"""Unit tests for bot.services.economy_service.EconomyService.

Covers:
    - compute_level / xp_for_level — pure-function level formula
    - gain_xp — cooldown check, XP increment, level-up detection
    - claim_daily — streak logic, cooldown, reward calculation
    - get_balance — coin balance query
    - get_leaderboard — XP and coins leaderboard with pagination
    - get_rank_info — member rank position and XP progress

Strict TDD: these tests are written BEFORE the implementation exists (RED phase).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.services.economy_service import EconomyService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock for Database, pre-configured for economy methods."""
    db = AsyncMock()
    db.get_economy_config = AsyncMock()
    db.upsert_economy_config = AsyncMock()
    db.get_member = AsyncMock()
    db.update_member_xp = AsyncMock()
    db.update_member_coins = AsyncMock()
    db.update_member_daily = AsyncMock()
    db.get_leaderboard = AsyncMock()
    db.get_member_rank = AsyncMock()
    return db


@pytest.fixture
def service(cache: TTLCache, mock_db: AsyncMock) -> EconomyService:
    """Return a fresh EconomyService with mocked DB."""
    return EconomyService(db=mock_db, cache=cache)


@pytest.fixture
def default_config_row() -> dict:
    """Return a default economy_config DB row (camelCase keys)."""
    return {
        "guildId": "123456789",
        "dailyReward": 100,
        "dailyCooldownHours": 24,
        "xpPerMessage": 10,
        "xpCooldownSeconds": 60,
        "levelBaseXp": 100,
        "levelMultiplier": 1.5,
        "levelRoles": {"5": "111111111", "10": "222222222"},
        "levelUpChannelId": "999999999",
    }


@pytest.fixture
def member_row() -> dict:
    """Return a sample member DB row with moderate XP."""
    return {
        "guildId": "123456789",
        "userId": "111111111",
        "xp": 250,
        "level": 2,
        "warnings": 0,
        "coins": 500,
        "dailyStreak": 0,
        "lastDailyReset": None,
        "lastDaily": None,
        "lastXpGain": None,
    }


# ---------------------------------------------------------------------------
# compute_level — pure-function level formula
# ---------------------------------------------------------------------------


class TestComputeLevel:
    """Tests for the level calculation: xp_for_level and compute_level."""

    # -- xp_for_level --------------------------------------------------------

    def test_xp_for_level_0(self, service: EconomyService) -> None:
        """Level 0 threshold should be 0 XP (starting point)."""
        result = service.compute_xp_for_level(0, base=100, multiplier=1.5)
        assert result == 0

    def test_xp_for_level_1_defaults(self, service: EconomyService) -> None:
        """Level 1 threshold = base * multiplier^1 = 100 * 1.5 = 150."""
        result = service.compute_xp_for_level(1, base=100, multiplier=1.5)
        assert result == 150.0

    def test_xp_for_level_3(self, service: EconomyService) -> None:
        """Level 3 threshold = 100 * 1.5^3 = 100 * 3.375 = 337.5."""
        result = service.compute_xp_for_level(3, base=100, multiplier=1.5)
        assert result == pytest.approx(337.5)

    def test_xp_for_level_custom_base(self, service: EconomyService) -> None:
        """Custom base and multiplier should produce correct threshold."""
        result = service.compute_xp_for_level(2, base=200, multiplier=2.0)
        assert result == 800.0  # 200 * 2^2

    # -- compute_level -------------------------------------------------------

    def test_compute_level_zero_xp(self, service: EconomyService) -> None:
        """0 XP should yield level 0."""
        result = service.compute_level(0, base=100, multiplier=1.5)
        assert result == 0

    def test_compute_level_at_threshold(self, service: EconomyService) -> None:
        """Exactly at level 1 threshold (150 XP) should yield level 1."""
        result = service.compute_level(150, base=100, multiplier=1.5)
        assert result == 1

    def test_compute_level_between(self, service: EconomyService) -> None:
        """250 XP is above level 2 threshold (150) but below level 3 (337.5)."""
        result = service.compute_level(250, base=100, multiplier=1.5)
        assert result == 2

    def test_compute_level_high(self, service: EconomyService) -> None:
        """High XP with large multiplier should yield correct level."""
        # XP thresholds with base=100, mult=3.0:
        # L1=300, L2=900, L3=2700, L4=8100
        # 5000 XP → level 3 (5000 >= 2700, 5000 < 8100)
        result = service.compute_level(5000, base=100, multiplier=3.0)
        assert result == 3

    def test_compute_level_deterministic(self, service: EconomyService) -> None:
        """Same input should always produce same output."""
        a = service.compute_level(1000, base=100, multiplier=1.5)
        b = service.compute_level(1000, base=100, multiplier=1.5)
        assert a == b

    # -- xp_progress ---------------------------------------------------------

    def test_xp_progress_at_level_0(self, service: EconomyService) -> None:
        """Progress at level 0: fraction of XP toward level 1 (threshold 150)."""
        current, needed = service.xp_progress(50, level=0, base=100, multiplier=1.5)
        assert current == 50
        assert needed == 150.0  # xp_for_level(1) - xp_for_level(0) = 150 - 0

    def test_xp_progress_mid_level(self, service: EconomyService) -> None:
        """Progress at level 2 with 250 XP: current=25, needed=112.5 for level 3."""
        # Level 2 threshold: 100 * 1.5^2 = 225
        # Level 3 threshold: 100 * 1.5^3 = 337.5
        current, needed = service.xp_progress(250, level=2, base=100, multiplier=1.5)
        assert current == 25.0  # 250 - 225
        assert needed == pytest.approx(112.5)  # 337.5 - 225

    def test_xp_progress_exactly_at_next(self, service: EconomyService) -> None:
        """At exactly the level 1 threshold from level 0."""
        # Level 0 → 1: threshold is 150
        current, needed = service.xp_progress(150, level=0, base=100, multiplier=1.5)
        assert current == 150.0
        assert needed == 150.0


# ---------------------------------------------------------------------------
# gain_xp — cooldown + XP increment + level-up detection
# ---------------------------------------------------------------------------


class TestGainXp:
    """Tests for gain_xp: cooldown enforcement, XP gain, level-up."""

    @pytest.mark.asyncio
    async def test_gain_xp_first_time(
        self, service: EconomyService, mock_db: AsyncMock, default_config_row: dict
    ) -> None:
        """First-time XP gain: no cooldown row, awards full XP."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # No member row → no cooldown
        mock_db.get_member.return_value = None
        mock_db.update_member_xp.return_value = {"xp": 10, "level": 0}

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 10
        assert new_level == 0
        assert leveled_up is False
        mock_db.update_member_xp.assert_called_once_with(guild_id, user_id, 10, new_level=0)
        mock_db.get_economy_config.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_gain_xp_cooldown_active(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """When cooldown is active, no XP should be awarded."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # Member gained XP 10 seconds ago (cooldown is 60s)
        member_with_cooldown = {**member_row, "lastXpGain": datetime.now(timezone.utc) - timedelta(seconds=10)}
        mock_db.get_member.return_value = member_with_cooldown

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 0
        assert new_level == 0
        assert leveled_up is False
        mock_db.update_member_xp.assert_not_called()

    @pytest.mark.asyncio
    async def test_gain_xp_cooldown_elapsed(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """When cooldown has elapsed, XP should be awarded."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # Member gained XP 120 seconds ago (cooldown is 60s)
        member_elapsed = {
            **member_row,
            "lastXpGain": datetime.now(timezone.utc) - timedelta(seconds=120),
            "xp": 250,
            "level": 2,
        }
        mock_db.get_member.return_value = member_elapsed
        mock_db.update_member_xp.return_value = {"xp": 260, "level": 2}

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 260
        assert new_level == 2
        assert leveled_up is False
        mock_db.update_member_xp.assert_called_once_with(guild_id, user_id, 10, new_level=2)

    @pytest.mark.asyncio
    async def test_gain_xp_levels_up(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """XP gain that crosses a level threshold should trigger level-up."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # Member at 330 XP (level 2), +10 XP → 340 XP — just over level 3 threshold (337.5).
        member_near_level = {
            **member_row,
            "lastXpGain": datetime.now(timezone.utc) - timedelta(seconds=120),
            "xp": 330,
            "level": 2,
        }
        mock_db.get_member.return_value = member_near_level
        mock_db.update_member_xp.return_value = {"xp": 340, "level": 3}

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 340
        assert new_level == 3
        assert leveled_up is True

    @pytest.mark.asyncio
    async def test_gain_xp_no_config_uses_defaults(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """When no economy_config exists, default values should be used."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = None  # No config row
        mock_db.get_member.return_value = None
        mock_db.update_member_xp.return_value = {"xp": 10, "level": 0}

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 10  # Default xpPerMessage = 10
        assert new_level == 0

    @pytest.mark.asyncio
    async def test_gain_xp_invalidates_leaderboard_cache(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, cache: TTLCache,
    ) -> None:
        """After XP gain, guild leaderboard cache should be invalidated."""
        guild_id = "123456789"
        user_id = "111111111"

        # Pre-populate cache
        cache.set(f"{guild_id}:leaderboard:xp", [{"dummy": True}], ttl=30)
        assert cache.get(f"{guild_id}:leaderboard:xp") is not None

        mock_db.get_economy_config.return_value = default_config_row
        mock_db.get_member.return_value = None
        mock_db.update_member_xp.return_value = {"xp": 10, "level": 0}

        await service.gain_xp(guild_id, user_id)

        assert cache.get(f"{guild_id}:leaderboard:xp") is None
        assert cache.get(f"{guild_id}:leaderboard:coins") is None


# ---------------------------------------------------------------------------
# claim_daily — streak logic, cooldown, reward
# ---------------------------------------------------------------------------


class TestClaimDaily:
    """Tests for claim_daily: streak tracking, reward calculation, cooldown."""

    @pytest.mark.asyncio
    async def test_claim_daily_first_time(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """First daily claim: streak=1, reward = dailyReward (base 100)."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        mock_db.get_member.return_value = member_row  # No prior daily
        mock_db.update_member_daily.return_value = {"coins": 600}

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 100  # dailyReward * 1.0
        assert streak == 1

    @pytest.mark.asyncio
    async def test_claim_daily_consecutive(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Consecutive claim: streak increments by 1, reward scales."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        yesterday_26h = datetime.now(timezone.utc) - timedelta(hours=26)
        yesterday_20h = datetime.now(timezone.utc) - timedelta(hours=20)
        member_with_streak = {
            **member_row,
            "dailyStreak": 3,
            "lastDailyReset": yesterday_20h.isoformat(),
            "lastDaily": yesterday_26h.isoformat(),
        }
        mock_db.get_member.return_value = member_with_streak
        mock_db.update_member_daily.return_value = {"coins": 640}

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 130  # 100 * (1 + 0.1 * 3) = 130
        assert streak == 4

    @pytest.mark.asyncio
    async def test_claim_daily_streak_capped_at_7(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Streak capped at 7: reward = 100 * (1 + 0.1 * 6) = 160."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        yesterday_26h = datetime.now(timezone.utc) - timedelta(hours=26)
        yesterday_20h = datetime.now(timezone.utc) - timedelta(hours=20)
        member_max_streak = {
            **member_row,
            "dailyStreak": 7,
            "lastDailyReset": yesterday_20h.isoformat(),
            "lastDaily": yesterday_26h.isoformat(),
        }
        mock_db.get_member.return_value = member_max_streak
        mock_db.update_member_daily.return_value = {"coins": 660}

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 160  # 100 * (1 + 0.1 * 6) = 160
        assert streak == 7  # stays capped

    @pytest.mark.asyncio
    async def test_claim_daily_broken_streak(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Missed a day: streak resets to 1, base reward."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        two_days_ago = datetime.now(timezone.utc) - timedelta(hours=48)
        member_broken = {
            **member_row,
            "dailyStreak": 5,
            "lastDailyReset": two_days_ago.isoformat(),
            "lastDaily": two_days_ago.isoformat(),
        }
        mock_db.get_member.return_value = member_broken
        mock_db.update_member_daily.return_value = {"coins": 600}

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 100  # Reset to base
        assert streak == 1

    @pytest.mark.asyncio
    async def test_claim_daily_cooldown_active(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Claim within cooldown window should be rejected."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        member_recent = {
            **member_row,
            "dailyStreak": 3,
            "lastDailyReset": two_hours_ago.isoformat(),
            "lastDaily": two_hours_ago.isoformat(),
        }
        mock_db.get_member.return_value = member_recent

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is False
        assert coins_awarded == 0
        assert streak == 3  # unchanged

    @pytest.mark.asyncio
    async def test_claim_daily_custom_reward(
        self, service: EconomyService, mock_db: AsyncMock, member_row: dict,
    ) -> None:
        """Custom dailyReward from config should be respected."""
        guild_id = "123456789"
        user_id = "111111111"

        custom_config = {
            "guildId": "123456789",
            "dailyReward": 200,
            "dailyCooldownHours": 24,
            "xpPerMessage": 10,
            "xpCooldownSeconds": 60,
            "levelBaseXp": 100,
            "levelMultiplier": 1.5,
            "levelRoles": {},
            "levelUpChannelId": None,
        }
        mock_db.get_economy_config.return_value = custom_config
        mock_db.get_member.return_value = member_row
        mock_db.update_member_daily.return_value = {"coins": 700}

        success, coins_awarded, streak = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 200
        assert streak == 1


# ---------------------------------------------------------------------------
# get_balance — coin balance
# ---------------------------------------------------------------------------


class TestGetBalance:
    """Tests for get_balance."""

    @pytest.mark.asyncio
    async def test_get_balance_has_coins(
        self, service: EconomyService, mock_db: AsyncMock, member_row: dict,
    ) -> None:
        """Should return the member's coin balance."""
        mock_db.get_member.return_value = member_row

        balance = await service.get_balance("123456789", "111111111")

        assert balance == 500

    @pytest.mark.asyncio
    async def test_get_balance_no_member(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """New member with no row should have 0 balance."""
        mock_db.get_member.return_value = None

        balance = await service.get_balance("123456789", "111111111")

        assert balance == 0

    @pytest.mark.asyncio
    async def test_get_balance_zero_coins(
        self, service: EconomyService, mock_db: AsyncMock, member_row: dict,
    ) -> None:
        """Member with 0 coins should return 0."""
        member_no_coins = {**member_row, "coins": 0}
        mock_db.get_member.return_value = member_no_coins

        balance = await service.get_balance("123456789", "111111111")

        assert balance == 0


# ---------------------------------------------------------------------------
# get_leaderboard — XP and coins leaderboard with cache + pagination
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    """Tests for get_leaderboard with caching."""

    @pytest.mark.asyncio
    async def test_get_leaderboard_xp_miss_populates_cache(
        self, service: EconomyService, mock_db: AsyncMock, cache: TTLCache,
    ) -> None:
        """Cache miss triggers DB query and populates cache."""
        guild_id = "123456789"
        db_rows = [
            {"userId": "aaa", "xp": 100, "coins": 50},
            {"userId": "bbb", "xp": 80, "coins": 30},
        ]
        mock_db.get_leaderboard.return_value = db_rows

        result = await service.get_leaderboard(guild_id, sort_by="xp", limit=10, offset=0)

        assert len(result) == 2
        assert result[0]["userId"] == "aaa"
        mock_db.get_leaderboard.assert_called_once_with(guild_id, "xp", 10, 0)
        # Cache should now be populated
        assert cache.get(f"{guild_id}:leaderboard:xp") is not None

    @pytest.mark.asyncio
    async def test_get_leaderboard_xp_cache_hit(
        self, service: EconomyService, mock_db: AsyncMock, cache: TTLCache,
    ) -> None:
        """Cache hit should return cached data without DB query."""
        guild_id = "123456789"
        cached_data = [{"userId": "zzz", "xp": 999, "coins": 0}]
        cache.set(f"{guild_id}:leaderboard:xp", cached_data, ttl=30)

        result = await service.get_leaderboard(guild_id, sort_by="xp", limit=10, offset=0)

        assert result is cached_data
        mock_db.get_leaderboard.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_leaderboard_coins(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """Coins leaderboard should query with sort_by='coins'."""
        guild_id = "123456789"
        db_rows = [{"userId": "ccc", "xp": 10, "coins": 500}]
        mock_db.get_leaderboard.return_value = db_rows

        result = await service.get_leaderboard(guild_id, sort_by="coins", limit=5, offset=0)

        assert len(result) == 1
        mock_db.get_leaderboard.assert_called_once_with(guild_id, "coins", 5, 0)

    @pytest.mark.asyncio
    async def test_get_leaderboard_empty(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """Empty guild should return empty list."""
        mock_db.get_leaderboard.return_value = []

        result = await service.get_leaderboard("123456789", sort_by="xp", limit=10, offset=0)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_with_offset(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """Pagination with offset should pass through correctly."""
        guild_id = "123456789"
        db_rows = [{"userId": "mid", "xp": 50, "coins": 10} for _ in range(5)]
        mock_db.get_leaderboard.return_value = db_rows

        result = await service.get_leaderboard(guild_id, sort_by="xp", limit=10, offset=20)

        assert len(result) == 5
        mock_db.get_leaderboard.assert_called_once_with(guild_id, "xp", 10, 20)


# ---------------------------------------------------------------------------
# get_rank_info — member rank, XP, level, progress
# ---------------------------------------------------------------------------


class TestGetRankInfo:
    """Tests for get_rank_info."""

    @pytest.mark.asyncio
    async def test_get_rank_info_returns_complete_data(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Should return rank, XP, level, coins, and progress for a member."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_member.return_value = member_row
        mock_db.get_member_rank.return_value = 3
        mock_db.get_economy_config.return_value = default_config_row

        result = await service.get_rank_info(guild_id, user_id)

        assert result is not None
        assert result["xp"] == 250
        assert result["level"] == 2
        assert result["coins"] == 500
        assert result["rank"] == 3
        assert "xp_current" in result
        assert "xp_needed" in result
        assert result["xp_current"] >= 0
        assert result["xp_needed"] > 0

    @pytest.mark.asyncio
    async def test_get_rank_info_no_member(
        self, service: EconomyService, mock_db: AsyncMock,
    ) -> None:
        """Member without a row should return None."""
        mock_db.get_member.return_value = None

        result = await service.get_rank_info("123456789", "999999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_rank_info_no_config_uses_defaults(
        self, service: EconomyService, mock_db: AsyncMock, member_row: dict,
    ) -> None:
        """Missing economy_config should fall back to defaults."""
        mock_db.get_member.return_value = member_row
        mock_db.get_member_rank.return_value = 5
        mock_db.get_economy_config.return_value = None

        result = await service.get_rank_info("123456789", "111111111")

        assert result is not None
        assert result["level"] == 2  # Still correctly computed

    @pytest.mark.asyncio
    async def test_get_rank_info_unranked(
        self, service: EconomyService, mock_db: AsyncMock,
        default_config_row: dict, member_row: dict,
    ) -> None:
        """Member with 0 XP and no rank should return rank 0."""
        guild_id = "123456789"
        member_zero = {**member_row, "xp": 0, "level": 0}
        mock_db.get_member.return_value = member_zero
        mock_db.get_member_rank.return_value = None  # No rank
        mock_db.get_economy_config.return_value = default_config_row

        result = await service.get_rank_info(guild_id, "111111111")

        assert result is not None
        assert result["rank"] == 0
        assert result["level"] == 0
