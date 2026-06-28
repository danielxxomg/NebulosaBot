"""Integration tests for the XP message-to-level-up flow.

Verifies that repeated messages accumulate XP and trigger a level-up event
when the threshold is crossed.  Uses ``frozen_clock`` for deterministic
datetime and mocked DB layer.

TDD cycle: RED → GREEN — tests specify expected behavior of existing code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.services.economy_service import EconomyService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def xp_db() -> AsyncMock:
    """Return a mock DB configured for XP gain tests."""
    db = AsyncMock()
    db.get_economy_config = AsyncMock(return_value={
        "guildId": "123456789",
        "xpPerMessage": 10,
        "xpCooldownSeconds": 60,
        "levelBaseXp": 100,
        "levelMultiplier": 1.5,
    })
    db.get_member = AsyncMock(return_value=None)
    db.update_member_xp = AsyncMock()
    return db


@pytest.fixture
def xp_service(xp_db: AsyncMock, cache: TTLCache) -> EconomyService:
    """Return an EconomyService wired to the mock DB."""
    return EconomyService(db=xp_db, cache=cache)


# ---------------------------------------------------------------------------
# TestXpFlow — integration: XP accumulation → level-up
# ---------------------------------------------------------------------------


class TestXpFlow:
    """Integration tests for the XP message-to-level-up flow.

    Verifies: gain_xp() → XP increment → level-up detection.
    """

    async def test_message_accumulation_triggers_level_up(
        self,
        xp_service: EconomyService,
        xp_db: AsyncMock,
        frozen_clock: datetime,
    ) -> None:
        """Repeated gain_xp calls accumulate XP and trigger level-up.

        Scenario: member with 0 XP sends enough messages to cross threshold
        → assert level increments by 1 → assert level-up notification sent
        (leveled_up=True).

        Since frozen_clock freezes time, we simulate 15 messages by making
        each call see a member with no lastXpGain (fresh member each time),
        and track XP accumulation via the update_member_xp side_effect.
        """
        guild_id = "123456789"
        user_id = "111111111"

        # Level 0→1 threshold: base * multiplier^1 = 100 * 1.5 = 150 XP.
        # With 10 XP per message, need 15 messages to cross.
        current_xp = 0
        current_level = 0

        # Track XP accumulation via update_member_xp.
        async def mock_update_xp(gid, uid, xp_delta, new_level=None):
            nonlocal current_xp, current_level
            current_xp += xp_delta
            if new_level is not None:
                current_level = new_level
            return {"xp": current_xp, "level": current_level}

        xp_db.update_member_xp = AsyncMock(side_effect=mock_update_xp)

        # get_member returns state with no lastXpGain to bypass cooldown.
        def mock_get_member(gid, uid):
            return {"xp": current_xp, "level": current_level, "lastXpGain": None}

        xp_db.get_member = AsyncMock(side_effect=mock_get_member)

        leveled_up = False
        for _ in range(15):
            _, _, did_level = await xp_service.gain_xp(guild_id, user_id)
            if did_level:
                leveled_up = True

        # 1. XP accumulated across calls.
        assert current_xp == 150

        # 2. Level-up triggered.
        assert leveled_up is True
        assert current_level >= 1

    async def test_xp_cooldown_prevents_spam(
        self,
        xp_service: EconomyService,
        xp_db: AsyncMock,
        frozen_clock: datetime,
    ) -> None:
        """Member on cooldown gets no additional XP.

        Scenario: member who just gained XP sends another message within
        cooldown → no additional XP awarded (returns 0, 0, False).
        """
        guild_id = "123456789"
        user_id = "111111111"

        # First call: no existing member (cold start).
        xp_db.get_member = AsyncMock(return_value=None)
        xp_db.update_member_xp = AsyncMock(return_value={"xp": 10, "level": 0})

        new_xp, new_level, leveled_up = await xp_service.gain_xp(guild_id, user_id)
        assert new_xp == 10
        assert leveled_up is False

        # Second call: member exists with lastXpGain = frozen_clock (just gained).
        xp_db.get_member = AsyncMock(return_value={
            "guildId": guild_id,
            "userId": user_id,
            "xp": 10,
            "level": 0,
            "lastXpGain": frozen_clock,  # just gained — within 60s cooldown
        })

        new_xp2, new_level2, leveled_up2 = await xp_service.gain_xp(guild_id, user_id)

        # 3. Cooldown prevents additional XP.
        assert new_xp2 == 0
        assert new_level2 == 0
        assert leveled_up2 is False

        # 4. update_member_xp NOT called for cooldown hit.
        xp_db.update_member_xp.assert_awaited_once()  # only the first call
