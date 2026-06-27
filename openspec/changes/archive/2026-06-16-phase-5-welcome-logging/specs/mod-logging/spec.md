# Delta for Mod Logging

## MODIFIED Requirements

### Requirement: Log actions to channel

The system MUST send an embed to `logChannelId` for each moderation action via `LoggingService` when logging is enabled.
(Previously: `SentinelCog` sent embeds directly through `_log_action()`.)

#### Scenario: Log a warn

- GIVEN `logEnabled` is true and `logChannelId` is set
- WHEN a moderator issues a warning
- THEN an embed is sent containing moderator, target, action type, reason, and timestamp

#### Scenario: Log via LoggingService

- GIVEN `LoggingService` is wired to `SentinelCog`
- WHEN a moderator issues a warning
- THEN `SentinelCog` invokes `LoggingService.log_moderation_action()` and an embed is sent

### Requirement: Skip logging when disabled

The system MUST NOT send log embeds when `logEnabled` is false.
(Previously: same behavior, enforced by `SentinelCog`.)

#### Scenario: Logging disabled

- GIVEN `logEnabled` is false
- WHEN a moderation action occurs
- THEN no embed is sent

### Requirement: Skip logging when no channel configured

The system MUST silently skip logging when `logChannelId` is null.
(Previously: same behavior, enforced by `SentinelCog`.)

#### Scenario: Missing log channel

- GIVEN `logEnabled` is true but `logChannelId` is null
- WHEN a moderation action occurs
- THEN no embed is sent and no error is surfaced to the user

### Requirement: Include escalation actions

The system MUST log automatic escalation actions with the same detail as manual actions.
(Previously: same behavior, enforced by `SentinelCog`.)

#### Scenario: Log auto-mute

- GIVEN auto-escalation mutes a member
- WHEN the mute is applied
- THEN a log embed is sent identifying the action as automatic escalation
