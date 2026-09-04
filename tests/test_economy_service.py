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

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from bot.core.cache import DEFAULT_TTL, ECONOMY_CONFIG_TTL, TTLCache, cache_key
from bot.models.economy_config import EconomyConfig
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
    @pytest.mark.parametrize(
        (
            "last_gain_seconds",
            "member_xp",
            "member_level",
            "no_config",
            "update_xp",
            "update_level",
            "leveled_up",
            "expected_call_level",
            "assert_config_call",
        ),
        [
            # first time: no member row; original asserts the config fetch
            (None, 250, 2, False, 10, 0, False, 0, True),
            # cooldown elapsed (60s): original asserts update call level
            (120, 250, 2, False, 260, 2, False, 2, False),
            # crosses level 3 threshold: original asserts outcome only
            (120, 330, 2, False, 340, 3, True, None, False),
            # no config → defaults: original asserts outcome only
            (None, 250, 2, True, 10, 0, False, None, False),
        ],
        ids=["first-time", "cooldown-elapsed", "levels-up", "no-config-defaults"],
    )
    async def test_gain_xp_awards_xp(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
        last_gain_seconds: int | None,
        member_xp: int,
        member_level: int,
        no_config: bool,
        update_xp: int,
        update_level: int,
        leveled_up: bool,
        expected_call_level: int | None,
        assert_config_call: bool,
    ) -> None:
        """gain_xp awards configured XP, detects level-ups, honors cooldown."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = None if no_config else default_config_row
        if last_gain_seconds is None:
            # No member row → no cooldown
            mock_db.get_member.return_value = None
        else:
            mock_db.get_member.return_value = {
                **member_row,
                "lastXpGain": frozen_clock - timedelta(seconds=last_gain_seconds),
                "xp": member_xp,
                "level": member_level,
            }
        mock_db.update_member_xp.return_value = {"xp": update_xp, "level": update_level}

        new_xp, new_level, got_leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == update_xp
        assert new_level == update_level
        assert got_leveled_up is leveled_up
        if expected_call_level is not None:
            mock_db.update_member_xp.assert_called_once_with(guild_id, user_id, 10, new_level=expected_call_level)
        if assert_config_call:
            mock_db.get_economy_config.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_gain_xp_cooldown_active(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
    ) -> None:
        """When cooldown is active, no XP should be awarded."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # Member gained XP 10 seconds ago (cooldown is 60s)
        member_with_cooldown = {**member_row, "lastXpGain": frozen_clock - timedelta(seconds=10)}
        mock_db.get_member.return_value = member_with_cooldown

        new_xp, new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 0
        assert new_level == 0
        assert leveled_up is False
        mock_db.update_member_xp.assert_not_called()

    @pytest.mark.asyncio
    async def test_gain_xp_invalidates_leaderboard_cache(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        cache: TTLCache,
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


def _member_with_daily(member_row: dict, daily_streak: int, last_daily: object, last_daily_reset: object) -> dict:
    """Return a member row with daily-claim timestamps set (str or datetime)."""
    return {
        **member_row,
        "dailyStreak": daily_streak,
        "lastDailyReset": last_daily_reset,
        "lastDaily": last_daily,
    }


class TestClaimDaily:
    """Tests for claim_daily: streak tracking, reward calculation, cooldown."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("streak", "days_ago_hours", "expected_coins", "scenario"),
        [
            (0, None, 100, "first-time"),  # no prior daily: base reward
            (5, 48, 100, "broken-streak"),  # missed a day: reset to base
        ],
        ids=["first-time", "broken-streak"],
    )
    async def test_claim_daily_streak_resets_to_base(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
        streak: int,
        days_ago_hours: int | None,
        expected_coins: int,
        scenario: str,
    ) -> None:
        """First claim or after a missed day: streak=1, base reward."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        if days_ago_hours is None:
            mock_db.get_member.return_value = member_row  # No prior daily
        else:
            two_days_ago = frozen_clock - timedelta(hours=days_ago_hours)
            mock_db.get_member.return_value = _member_with_daily(member_row, streak, two_days_ago, two_days_ago)
        mock_db.update_member_daily.return_value = {"coins": 600}

        success, coins_awarded, streak, remaining = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == expected_coins
        assert streak == 1
        assert remaining == 0  # success path: no cooldown

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("streak", "update_coins", "expected_coins", "expected_streak", "string_timestamps"),
        [
            (3, 640, 130, 4, False),  # 100 * (1 + 0.1 * 3) = 130
            (7, 660, 160, 7, False),  # capped: 100 * (1 + 0.1 * 6) = 160
            # String lastDaily/lastDailyReset MUST parse via _to_datetime
            # (no TypeError) and hit the same consecutive-day branch.
            (3, 640, 130, 4, True),
        ],
        ids=["consecutive", "streak-capped-at-7", "string-timestamps"],
    )
    async def test_claim_daily_streak_scales_reward(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
        streak: int,
        update_coins: int,
        expected_coins: int,
        expected_streak: int,
        string_timestamps: bool,
    ) -> None:
        """Consecutive claim: streak increments (capped at 7), reward scales."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # lastDaily 26h ago -> passes the 24h cooldown check regardless of
        # time of day (26h > 24h always).
        yesterday_26h = frozen_clock - timedelta(hours=26)
        # lastDailyReset must fall on YESTERDAY's calendar date at any time
        # of day so the "consecutive day" branch fires deterministically.
        # timedelta(hours=20) only equals yesterday before 20:00 UTC; after
        # that, 20h ago is still today and the same-day branch fires
        # (giving new_streak=old_streak instead of old_streak+1). Without
        # this, the cap row passes via the same-day branch instead of
        # actually exercising the consecutive-day cap path — masking the
        # same latent flake.
        yesterday = frozen_clock - timedelta(days=1)
        if string_timestamps:
            last_daily: str | object = yesterday_26h.isoformat()
            last_reset: str | object = yesterday.isoformat()
        else:
            last_daily = yesterday_26h
            last_reset = yesterday
        mock_db.get_member.return_value = _member_with_daily(member_row, streak, last_daily, last_reset)
        mock_db.update_member_daily.return_value = {"coins": update_coins}

        success, coins_awarded, streak_result, remaining = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == expected_coins
        assert streak_result == expected_streak
        assert remaining == 0  # success path: no cooldown

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("ago_kwargs", "member_streak", "expected_remaining"),
        [
            ({"hours": 2}, 3, 22 * 3600),  # 24h cooldown - 2h elapsed
            ({"hours": 23, "minutes": 50}, 1, 10 * 60),  # 600 seconds
        ],
        ids=["cooldown-active", "cooldown-near-expiry"],
    )
    async def test_claim_daily_cooldown_rejected(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
        ago_kwargs: dict,
        member_streak: int,
        expected_remaining: int,
    ) -> None:
        """Claim within cooldown window is rejected with exact remaining time."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        recent = frozen_clock - timedelta(**ago_kwargs)
        mock_db.get_member.return_value = _member_with_daily(member_row, member_streak, recent, recent)

        success, coins_awarded, streak, remaining = await service.claim_daily(guild_id, user_id)

        assert success is False
        assert coins_awarded == 0
        if member_streak == 3:  # cooldown-active row asserts streak unchanged
            assert streak == member_streak
        assert remaining == expected_remaining

    @pytest.mark.asyncio
    async def test_claim_daily_custom_reward(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        member_row: dict,
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

        success, coins_awarded, streak, remaining = await service.claim_daily(guild_id, user_id)

        assert success is True
        assert coins_awarded == 200
        assert streak == 1
        assert remaining == 0  # success path: no cooldown


# ---------------------------------------------------------------------------
# get_balance — coin balance
# ---------------------------------------------------------------------------


class TestGetBalance:
    """Tests for get_balance."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("coins", "expected_balance"),
        [
            (500, 500),  # member with coins
            (0, 0),  # member with 0 coins
        ],
        ids=["has-coins", "zero-coins"],
    )
    async def test_get_balance_returns_member_coins(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        member_row: dict,
        coins: int,
        expected_balance: int,
    ) -> None:
        """get_balance returns the member's coin balance."""
        mock_db.get_member.return_value = {**member_row, "coins": coins}

        balance = await service.get_balance("123456789", "111111111")

        assert balance == expected_balance

    @pytest.mark.asyncio
    async def test_get_balance_no_member(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
    ) -> None:
        """New member with no row should have 0 balance."""
        mock_db.get_member.return_value = None

        balance = await service.get_balance("123456789", "111111111")

        assert balance == 0


# ---------------------------------------------------------------------------
# get_leaderboard — XP and coins leaderboard with cache + pagination
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    """Tests for get_leaderboard with caching."""

    @pytest.mark.asyncio
    async def test_get_leaderboard_xp_miss_populates_cache(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        cache: TTLCache,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        cache: TTLCache,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
    ) -> None:
        """Empty guild should return empty list."""
        mock_db.get_leaderboard.return_value = []

        result = await service.get_leaderboard("123456789", sort_by="xp", limit=10, offset=0)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_with_offset(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
    ) -> None:
        """Member without a row should return None."""
        mock_db.get_member.return_value = None

        result = await service.get_rank_info("123456789", "999999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_rank_info_no_config_uses_defaults(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        member_row: dict,
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
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
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


# ===========================================================================
# String-type timestamp parsing (runtime-hotfix)
# ===========================================================================


class TestGainXpTimestampParsing:
    """gain_xp MUST safely parse string-type lastXpGain from DB."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("as_iso_string", "doc"),
        [
            (True, "lastXpGain as ISO string MUST NOT raise TypeError on cooldown check"),
            (False, "lastXpGain as datetime MUST still work (passthrough)"),
        ],
        ids=["string-parses", "datetime-passthrough"],
    )
    async def test_gain_xp_last_xp_gain_awards(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
        as_iso_string: bool,
        doc: str,
    ) -> None:
        """String lastXpGain parses via _to_datetime; datetime passes through."""
        last_gain = frozen_clock - timedelta(seconds=120)
        gain_value = last_gain.isoformat() if as_iso_string else last_gain
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        mock_db.get_member.return_value = {
            **member_row,
            "lastXpGain": gain_value,
            "xp": 250,
            "level": 2,
        }
        mock_db.update_member_xp.return_value = {"xp": 260, "level": 2}

        # Must not raise TypeError — string is parsed via _to_datetime.
        new_xp, _new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 260
        assert leveled_up is False

    @pytest.mark.asyncio
    async def test_gain_xp_string_last_xp_gain_cooldown_active(
        self,
        service: EconomyService,
        mock_db: AsyncMock,
        default_config_row: dict,
        member_row: dict,
        frozen_clock,
    ) -> None:
        """String lastXpGain within cooldown MUST block XP gain."""
        guild_id = "123456789"
        user_id = "111111111"

        mock_db.get_economy_config.return_value = default_config_row
        # 10 seconds ago as ISO string (cooldown is 60s).
        member_str = {
            **member_row,
            "lastXpGain": (frozen_clock - timedelta(seconds=10)).isoformat(),
        }
        mock_db.get_member.return_value = member_str

        new_xp, _new_level, leveled_up = await service.gain_xp(guild_id, user_id)

        assert new_xp == 0
        assert leveled_up is False
        mock_db.update_member_xp.assert_not_called()


# ---------------------------------------------------------------------------
# S4.5 — economy_config cache-first TTL reads + save-path invalidation
# ---------------------------------------------------------------------------


class TestEconomyConfigCache:
    """get_economy_config is cache-first; save path invalidates (design D4)."""

    async def test_miss_fetches_and_populates_cache(self, service: EconomyService, mock_db, default_config_row) -> None:
        mock_db.get_economy_config.return_value = default_config_row
        result = await service.get_economy_config("123456789")
        assert result == default_config_row
        mock_db.get_economy_config.assert_awaited_once()
        assert service._cache.get(cache_key("123456789", "economy_config")) == default_config_row

    async def test_hit_skips_db(self, service: EconomyService, mock_db, default_config_row) -> None:
        mock_db.get_economy_config.return_value = default_config_row
        first = await service.get_economy_config("123456789")
        second = await service.get_economy_config("123456789")
        assert second == first
        mock_db.get_economy_config.assert_awaited_once()

    async def test_none_row_is_not_cached(self, service: EconomyService, mock_db) -> None:
        mock_db.get_economy_config.return_value = None
        assert await service.get_economy_config("123456789") is None
        mock_db.get_economy_config.return_value = {"fresh": True}
        # A later call must hit the DB again — None was never cached.
        assert await service.get_economy_config("123456789") == {"fresh": True}
        assert mock_db.get_economy_config.await_count == 2

    async def test_save_invalidates_cache(self, service: EconomyService, mock_db, default_config_row) -> None:
        mock_db.get_economy_config.return_value = default_config_row
        await service.get_economy_config("123456789")
        stale = {"xpPerMessage": 10}
        service._cache.set(cache_key("123456789", "economy_config"), stale)

        config = EconomyConfig(guild_id="123456789")
        await service.save_economy_config(config)

        assert service._cache.get(cache_key("123456789", "economy_config")) is None
        mock_db.upsert_economy_config.assert_awaited_once_with(config)

    async def test_hot_paths_gain_xp_and_claim_daily_hit_cache(
        self, service: EconomyService, mock_db, default_config_row, member_row
    ) -> None:
        """gain_xp/claim_daily route through the cache-first accessor."""
        mock_db.get_economy_config.return_value = default_config_row
        member_row["lastXpGain"] = None
        member_row["lastDaily"] = None
        mock_db.get_member.return_value = dict(member_row)
        mock_db.update_member_xp.return_value = {"xp": 10, "level": 0}
        mock_db.update_member_daily.return_value = {"coins": 100}

        await service.gain_xp("123456789", "111111111")
        await service.claim_daily("123456789", "111111111")

        mock_db.get_economy_config.assert_awaited_once()

    def test_economy_config_ttl_reexported(self) -> None:
        assert ECONOMY_CONFIG_TTL == DEFAULT_TTL
