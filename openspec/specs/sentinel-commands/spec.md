# Sentinel Commands Specification

## Purpose

Expose moderation actions as hybrid Discord commands with permission guards.

## Requirements

### Requirement: Warn command

The `/warn` command MUST be available to moderators and create a WARN infraction with a reason.

#### Scenario: Moderator warns user

- GIVEN a moderator invokes `/warn` on a guild member with reason "spam"
- THEN a WARN infraction is created and the target is notified

### Requirement: Unwarn command

The `/unwarn` command MUST allow a moderator to remove the most recent active warning.

#### Scenario: Moderator unwarns user

- GIVEN a member has an active WARN infraction
- WHEN a moderator invokes `/unwarn`
- THEN the warning is removed and `Member.warnings` is decremented

### Requirement: Mute command

The `/mute` command MUST timeout a member for an optional duration, defaulting to 1 hour.

#### Scenario: Mute with default duration

- GIVEN a moderator invokes `/mute` without a duration
- THEN the member is timed out for 1 hour

#### Scenario: Mute with custom duration

- GIVEN a moderator invokes `/mute` with duration "30m"
- THEN the member is timed out for 30 minutes

### Requirement: Unmute command

The `/unmute` command MUST remove an active timeout.

#### Scenario: Moderator unmutes user

- GIVEN a member is currently muted
- WHEN a moderator invokes `/unmute`
- THEN the timeout is removed

### Requirement: Kick command

The `/kick` command MUST remove a member from the guild and create a KICK infraction.

#### Scenario: Moderator kicks user

- GIVEN a moderator invokes `/kick` with reason "trolling"
- THEN the member is removed and a KICK infraction is persisted

### Requirement: Ban command

The `/ban` command MUST be restricted to administrators, ban a user, and accept optional `delete_days` (0–7, default 0).

#### Scenario: Admin bans user

- GIVEN an administrator invokes `/ban` with reason "harassment"
- THEN the user is banned and a BAN infraction is created

#### Scenario: Ban with message deletion

- GIVEN an administrator invokes `/ban` with `delete_days` set to 3
- THEN the user is banned and up to 3 days of messages are deleted

### Requirement: Lock command

The `/lock` command MUST disable `send_messages` for `@everyone` in the specified or current channel.

#### Scenario: Lock current channel

- GIVEN a moderator invokes `/lock` without a channel argument
- THEN `@everyone` loses send permission in the current channel

### Requirement: Unlock command

The `/unlock` command MUST restore `send_messages` for `@everyone` in the specified or current channel.

#### Scenario: Unlock current channel

- GIVEN a channel is locked
- WHEN a moderator invokes `/unlock`
- THEN `@everyone` regains send permission in the channel

### Requirement: Modlogs command

The `/modlogs` command MUST list infractions paginated at 5 per page with optional filters for type and date. Responses MUST be ephemeral. The command MUST be restricted via `@app_commands.default_permissions(moderate_members=True)`.

#### Scenario: List modlogs

- GIVEN a guild has 6 infractions
- WHEN a moderator invokes `/modlogs` page 1
- THEN the first 5 infractions are returned ephemerally

### Requirement: Moderator permission hint

All moderation action commands (warn, unwarn, mute, unmute, kick, lock, unlock) MUST include `@app_commands.default_permissions(moderate_members=True)` so Discord displays a permission hint to users without the permission.

#### Scenario: Permission hint displayed

- GIVEN a user without Moderate Members permission
- WHEN they view the slash command list
- THEN moderation commands show a permission indicator in the Discord UI

### Requirement: Administrator permission hint on ban

The `/ban` command MUST include `@app_commands.default_permissions(ban_members=True)` so Discord displays a permission hint.

#### Scenario: Ban permission hint

- GIVEN a user without Ban Members permission
- WHEN they view the slash command list
- THEN `/ban` shows a permission indicator in the Discord UI
