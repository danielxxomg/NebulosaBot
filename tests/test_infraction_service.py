"""Unit tests for bot.services.infraction_service.

Covers the infraction-service spec scenarios:
    - warn persists infraction and increments warnings
    - unwarn deactivates most-recent active WARN and decrements warnings
    - unwarn returns None when there are no active warnings
    - check_escalation: count==2→None, 3→MUTE, 4→None, 5→KICK
    - warn includes escalation action when threshold is hit
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.models.infraction import Infraction
from bot.services.infraction_service import (
    InfractionService,
)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

GUILD_ID = "111222333"
TARGET_ID = "444555666"
MODERATOR_ID = "777888999"
REASON = "spamming in general"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock standing in for Database with infraction methods."""
    from bot.core.database import Database

    db = AsyncMock(spec=Database)
    db.insert_infraction = AsyncMock()
    db.get_infractions = AsyncMock()
    db.get_active_warnings = AsyncMock()
    db.deactivate_infraction = AsyncMock()
    db.get_member = AsyncMock()
    db.update_member_warnings = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> InfractionService:
    """Return an InfractionService backed by the mocked database."""
    return InfractionService(db=mock_db)


@pytest.fixture
def sample_infraction_row() -> dict:
    """Return a raw camelCase row dict matching the Infraction schema."""
    return {
        "id": "abc-123-infraction-uuid",
        "guildId": GUILD_ID,
        "targetId": TARGET_ID,
        "moderatorId": MODERATOR_ID,
        "type": "WARN",
        "reason": REASON,
        "active": True,
        "createdAt": "2025-06-15T12:00:00+00:00",
        "expiresAt": None,
    }


# ------------------------------------------------------------------
# warn
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warn_persists_infraction_and_increments_warnings(
    service: InfractionService,
    mock_db: AsyncMock,
    sample_infraction_row: dict,
) -> None:
    """Issuing a WARN MUST insert the infraction and increment Member.warnings."""
    mock_db.insert_infraction.return_value = sample_infraction_row
    mock_db.get_member.return_value = {"guildId": GUILD_ID, "userId": TARGET_ID, "warnings": 1}

    infraction, escalation = await service.warn(
        guild_id=GUILD_ID,
        target_id=TARGET_ID,
        moderator_id=MODERATOR_ID,
        reason=REASON,
    )

    # DB insert was called with the right arguments.
    mock_db.insert_infraction.assert_awaited_once_with(
        guild_id=GUILD_ID,
        target_id=TARGET_ID,
        moderator_id=MODERATOR_ID,
        type="WARN",
        reason=REASON,
    )

    # Warnings counter was bumped.
    mock_db.update_member_warnings.assert_awaited_once_with(GUILD_ID, TARGET_ID, delta=1)

    # Returned infraction matches the row.
    assert infraction.id == sample_infraction_row["id"]
    assert infraction.type == "WARN"
    assert infraction.reason == REASON

    # 1 warning is below escalation thresholds.
    assert escalation is None


# ------------------------------------------------------------------
# unwarn
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unwarn_deactivates_last_active_warning(
    service: InfractionService,
    mock_db: AsyncMock,
    sample_infraction_row: dict,
) -> None:
    """unwarn MUST deactivate the most recent active WARN and decrement warnings."""
    mock_db.get_active_warnings.return_value = [sample_infraction_row]

    result = await service.unwarn(guild_id=GUILD_ID, target_id=TARGET_ID)

    assert result is not None
    assert result.id == sample_infraction_row["id"]
    mock_db.deactivate_infraction.assert_awaited_once_with(GUILD_ID, sample_infraction_row["id"])
    mock_db.update_member_warnings.assert_awaited_once_with(GUILD_ID, TARGET_ID, delta=-1)


@pytest.mark.asyncio
async def test_unwarn_returns_none_when_no_active_warnings(
    service: InfractionService,
    mock_db: AsyncMock,
) -> None:
    """unwarn MUST return None when the user has no active WARN infractions."""
    mock_db.get_active_warnings.return_value = []

    result = await service.unwarn(guild_id=GUILD_ID, target_id=TARGET_ID)

    assert result is None
    mock_db.deactivate_infraction.assert_not_called()
    mock_db.update_member_warnings.assert_not_called()


# ------------------------------------------------------------------
# get_modlogs
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_modlogs_returns_infractions(
    service: InfractionService,
    mock_db: AsyncMock,
    sample_infraction_row: dict,
) -> None:
    """get_modlogs MUST return Infraction objects for the given target."""
    mock_db.get_infractions.return_value = [sample_infraction_row]

    results = await service.get_modlogs(guild_id=GUILD_ID, target_id=TARGET_ID)

    assert len(results) == 1
    assert isinstance(results[0], Infraction)
    assert results[0].id == sample_infraction_row["id"]


@pytest.mark.asyncio
async def test_get_modlogs_passes_filters_to_db(
    service: InfractionService,
    mock_db: AsyncMock,
) -> None:
    """get_modlogs MUST forward type_filter and after to the database."""
    mock_db.get_infractions.return_value = []

    await service.get_modlogs(
        guild_id=GUILD_ID,
        target_id=TARGET_ID,
        type_filter="MUTE",
        after="2025-01-01T00:00:00Z",
    )

    mock_db.get_infractions.assert_awaited_once_with(
        guild_id=GUILD_ID,
        target_id=TARGET_ID,
        type="MUTE",
        after="2025-01-01T00:00:00Z",
    )


# ------------------------------------------------------------------
# check_escalation
# ------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("warnings_count", "expected_action", "expected_duration", "expected_threshold"),
    [
        (2, None, None, None),
        (3, "MUTE", 3600, 3),
        (4, None, None, None),
        (5, "KICK", 0, 5),
    ],
)
async def test_check_escalation_thresholds(
    service: InfractionService,
    mock_db: AsyncMock,
    warnings_count: int,
    expected_action: str | None,
    expected_duration: int | None,
    expected_threshold: int | None,
) -> None:
    """Escalation MUST fire at exact thresholds and not between them."""
    mock_db.get_member.return_value = {
        "guildId": GUILD_ID,
        "userId": TARGET_ID,
        "warnings": warnings_count,
    }

    result = await service.check_escalation(GUILD_ID, TARGET_ID)

    if expected_action is None:
        assert result is None
    else:
        assert result is not None
        assert result.action == expected_action
        assert result.duration == expected_duration
        assert result.threshold == expected_threshold


@pytest.mark.asyncio
async def test_check_escalation_no_member_row_returns_none(
    service: InfractionService,
    mock_db: AsyncMock,
) -> None:
    """When no member row exists, escalation MUST return None."""
    mock_db.get_member.return_value = None

    result = await service.check_escalation(GUILD_ID, TARGET_ID)

    assert result is None


# ------------------------------------------------------------------
# warn + escalation integration
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warn_triggers_escalation_at_threshold(
    service: InfractionService,
    mock_db: AsyncMock,
    sample_infraction_row: dict,
) -> None:
    """When warn pushes warnings to a threshold, the returned tuple MUST contain the EscalationAction."""
    sample_infraction_row["type"] = "WARN"
    mock_db.insert_infraction.return_value = sample_infraction_row
    # simulate the member having 2 existing warnings → this is the 3rd.
    mock_db.get_member.return_value = {
        "guildId": GUILD_ID,
        "userId": TARGET_ID,
        "warnings": 3,
    }

    infraction, escalation = await service.warn(
        guild_id=GUILD_ID,
        target_id=TARGET_ID,
        moderator_id=MODERATOR_ID,
        reason=REASON,
    )

    assert infraction is not None
    assert escalation is not None
    assert escalation.action == "MUTE"
    assert escalation.duration == 3600
    assert escalation.threshold == 3
