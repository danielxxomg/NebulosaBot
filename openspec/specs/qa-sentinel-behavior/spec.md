# QA Sentinel Behavior Specification

## Purpose

Behavioral tests for sentinel moderation commands (warn, mute, kick, ban) and `validate_target` deny logic — independent of i18n locale strings.

## Requirements

### Requirement: Warn command persists infraction

Tests MUST prove warn calls `infraction_service.warn()` and sends a moderation log.

#### Scenario: warn happy path

- GIVEN a valid moderator and target member
- WHEN the warn command is executed with a reason
- THEN `infraction_service.warn()` is called with guild_id, target, moderator, and reason
- AND a moderation log embed is sent

#### Scenario: warn auto-escalation to mute

- GIVEN a target with prior infractions reaching the mute threshold
- WHEN warn is executed
- THEN escalation triggers a mute action automatically

### Requirement: Mute command applies timeout

Tests MUST prove mute calls `member.timeout()` with the correct duration.

#### Scenario: mute happy path

- GIVEN a valid moderator and target member
- WHEN the mute command is executed with a duration
- THEN `member.timeout()` is called with the parsed timedelta
- AND a moderation log embed is sent

### Requirement: Kick and ban show confirmation

Tests MUST prove kick/ban send an ephemeral ConfirmCancelView before acting.

#### Scenario: kick sends confirmation dialog

- GIVEN a valid moderator and target member
- WHEN the kick command is executed
- THEN an ephemeral ConfirmCancelView is sent to the moderator

#### Scenario: ban sends confirmation dialog

- GIVEN a valid moderator and target member
- WHEN the ban command is executed
- THEN an ephemeral ConfirmCancelView is sent to the moderator

### Requirement: validate_target denies invalid targets

Tests MUST prove `_validate_target` returns False for self-targeting, hierarchy violations, and bot targets.

#### Scenario: deny self-targeting

- GIVEN a moderator
- WHEN `_validate_target` is called with the moderator as target
- THEN it returns False

#### Scenario: deny higher-role target

- GIVEN a moderator whose top role is below the target's top role
- WHEN `_validate_target` is called
- THEN it returns False

#### Scenario: deny bot as target

- GIVEN the bot's own member object as target
- WHEN `_validate_target` is called
- THEN it returns False
