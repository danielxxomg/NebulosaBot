"""Unit tests for bot.services.infraction_service.

Covers the infraction-service spec scenarios:
    - warn persists infraction and increments warnings
    - unwarn deactivates most-recent active WARN and decrements warnings
    - unwarn returns None when there are no active warnings
    - check_escalation: count==2→None, 3→MUTE, 4→None, 5→KICK
    - warn includes escalation action when threshold is hit
    - apply_escalation: MUTE/KICK success chain, Forbidden failure without
      persistence, unexpected errors propagate
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.i18n import t
from bot.models.infraction import Infraction
from bot.services.infraction_service import (
    EscalationAction,
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
def mock_logging() -> AsyncMock:
    """Return an AsyncMock standing in for LoggingService."""
    logging_mock = AsyncMock()
    logging_mock.log_moderation_action = AsyncMock()
    return logging_mock


@pytest.fixture
def escalation_service(mock_db: AsyncMock, mock_logging: AsyncMock) -> InfractionService:
    """Return an InfractionService wired with mocked DB and LoggingService."""
    return InfractionService(db=mock_db, logging_service=mock_logging)


@pytest.fixture
def target_member() -> MagicMock:
    """Return a mock guild member for escalation actions."""
    member = MagicMock(spec=discord.Member)
    member.id = 444555666
    member.mention = "<@444555666>"
    member.timeout = AsyncMock()
    member.kick = AsyncMock()
    return member


@pytest.fixture
def moderator_member() -> MagicMock:
    """Return a mock moderator member."""
    moderator = MagicMock(spec=discord.Member)
    moderator.id = 777888999
    return moderator


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


# ------------------------------------------------------------------
# apply_escalation (cycle-4-debt-zero / infraction-service spec)
# ------------------------------------------------------------------


def _mute_escalation() -> EscalationAction:
    """Return the canonical MUTE escalation (1 hour at 3 warnings)."""
    return EscalationAction(action="MUTE", duration=3600, threshold=3)


def _kick_escalation() -> EscalationAction:
    """Return the canonical KICK escalation (at 5 warnings)."""
    return EscalationAction(action="KICK", duration=0, threshold=5)


@pytest.mark.asyncio
async def test_apply_escalation_mute_times_out_inserts_and_logs(
    escalation_service: InfractionService,
    mock_db: AsyncMock,
    mock_logging: AsyncMock,
    target_member: MagicMock,
    moderator_member: MagicMock,
) -> None:
    """MUTE escalation MUST timeout, insert a MUTE row, log, and return the success fragment."""
    mock_db.insert_infraction.return_value = {"id": "mute-1"}

    fragment = await escalation_service.apply_escalation(
        guild_id=GUILD_ID,
        member=target_member,
        moderator=moderator_member,
        escalation=_mute_escalation(),
    )

    # Discord action executed with the escalation duration.
    target_member.timeout.assert_awaited_once_with(
        timedelta(seconds=3600),
        reason="Auto-escalation: 3 warnings",
    )
    # Infraction row persisted.
    mock_db.insert_infraction.assert_awaited_once_with(
        guild_id=GUILD_ID,
        target_id=str(target_member.id),
        moderator_id=str(moderator_member.id),
        type="MUTE",
        reason="Auto-escalation after 3 warnings",
    )
    # Moderation action logged via LoggingService.
    mock_logging.log_moderation_action.assert_awaited_once_with(
        GUILD_ID,
        "Mute (Auto-escalation)",
        target_member,
        moderator_member,
        "3 warnings reached",
    )
    # Localized success fragment returned for the caller to embed.
    expected = t(GUILD_ID, "sentinel.warn.auto_mute_description", mention=target_member.mention, threshold=3)
    assert fragment == expected


@pytest.mark.asyncio
async def test_apply_escalation_kick_kicks_inserts_and_logs(
    escalation_service: InfractionService,
    mock_db: AsyncMock,
    mock_logging: AsyncMock,
    target_member: MagicMock,
    moderator_member: MagicMock,
) -> None:
    """KICK escalation MUST kick, insert a KICK row, log, and return the success fragment."""
    mock_db.insert_infraction.return_value = {"id": "kick-1"}

    fragment = await escalation_service.apply_escalation(
        guild_id=GUILD_ID,
        member=target_member,
        moderator=moderator_member,
        escalation=_kick_escalation(),
    )

    target_member.kick.assert_awaited_once_with(reason="Auto-escalation: 5 warnings")
    mock_db.insert_infraction.assert_awaited_once_with(
        guild_id=GUILD_ID,
        target_id=str(target_member.id),
        moderator_id=str(moderator_member.id),
        type="KICK",
        reason="Auto-escalation after 5 warnings",
    )
    mock_logging.log_moderation_action.assert_awaited_once_with(
        GUILD_ID,
        "Kick (Auto-escalation)",
        target_member,
        moderator_member,
        "5 warnings reached",
    )
    expected = t(GUILD_ID, "sentinel.warn.auto_kick_description", mention=target_member.mention, threshold=5)
    assert fragment == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("escalation", [pytest.param(_mute_escalation(), id="mute"), pytest.param(_kick_escalation(), id="kick")])
async def test_apply_escalation_forbidden_returns_failure_without_persisting(
    escalation_service: InfractionService,
    mock_db: AsyncMock,
    mock_logging: AsyncMock,
    target_member: MagicMock,
    moderator_member: MagicMock,
    escalation: EscalationAction,
) -> None:
    """discord.Forbidden MUST yield the failure fragment with NO row and NO log."""
    if escalation.action == "MUTE":
        target_member.timeout.side_effect = discord.Forbidden(MagicMock(), "missing timeout permission")
    else:
        target_member.kick.side_effect = discord.Forbidden(MagicMock(), "missing kick permission")

    fragment = await escalation_service.apply_escalation(
        guild_id=GUILD_ID,
        member=target_member,
        moderator=moderator_member,
        escalation=escalation,
    )

    failed_key = (
        "sentinel.warn.auto_mute_failed_description"
        if escalation.action == "MUTE"
        else "sentinel.warn.auto_kick_failed_description"
    )
    assert fragment == t(GUILD_ID, failed_key, mention=target_member.mention)
    mock_db.insert_infraction.assert_not_called()
    mock_logging.log_moderation_action.assert_not_called()


@pytest.mark.asyncio
async def test_apply_escalation_unexpected_error_propagates(
    escalation_service: InfractionService,
    mock_db: AsyncMock,
    mock_logging: AsyncMock,
    target_member: MagicMock,
    moderator_member: MagicMock,
) -> None:
    """Unexpected exceptions from the Discord action MUST propagate (never swallowed)."""
    target_member.kick.side_effect = RuntimeError("network exploded")

    with pytest.raises(RuntimeError, match="network exploded"):
        await escalation_service.apply_escalation(
            guild_id=GUILD_ID,
            member=target_member,
            moderator=moderator_member,
            escalation=_kick_escalation(),
        )

    mock_db.insert_infraction.assert_not_called()
    mock_logging.log_moderation_action.assert_not_called()


@pytest.mark.asyncio
async def test_apply_escalation_db_insert_failure_propagates(
    escalation_service: InfractionService,
    mock_db: AsyncMock,
    mock_logging: AsyncMock,
    target_member: MagicMock,
    moderator_member: MagicMock,
) -> None:
    """An unexpected exception from the DB insert MUST propagate to the caller."""
    mock_db.insert_infraction.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        await escalation_service.apply_escalation(
            guild_id=GUILD_ID,
            member=target_member,
            moderator=moderator_member,
            escalation=_mute_escalation(),
        )

    # The Discord action already ran; logging must NOT claim success.
    mock_logging.log_moderation_action.assert_not_called()
