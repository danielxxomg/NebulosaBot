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

The `/kick` command MUST remove a member from the guild and create a KICK infraction. Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, and Confirm/Cancel buttons. The kick only proceeds on explicit Confirm.

(Previously: `/kick` executed immediately with no confirmation step)

#### Scenario: Moderator kicks user

- GIVEN a moderator invokes `/kick` with reason "trolling"
- WHEN the moderator clicks Confirm on the ephemeral confirmation dialog
- THEN the member is removed and a KICK infraction is persisted

#### Scenario: Kick confirmation shown before execution

- GIVEN a moderator invokes `/kick` on a user
- WHEN the command is invoked
- THEN an ephemeral embed shows target, reason, and Confirm/Cancel buttons before any action

#### Scenario: Kick cancelled by moderator

- GIVEN a moderator sees the kick confirmation dialog
- WHEN the moderator clicks Cancel
- THEN the kick is not executed and a cancellation message is shown ephemerally

### Requirement: Ban command

The `/ban` command MUST be restricted to administrators, ban a user, and accept optional `delete_days` (0–7, default 0). Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, delete_days, and Confirm/Cancel buttons. The ban only proceeds on explicit Confirm.

(Previously: `/ban` executed immediately with no confirmation step)

#### Scenario: Admin bans user

- GIVEN an administrator invokes `/ban` with reason "harassment"
- WHEN the administrator clicks Confirm on the ephemeral confirmation dialog
- THEN the user is banned and a BAN infraction is created

#### Scenario: Ban with message deletion

- GIVEN an administrator invokes `/ban` with `delete_days` set to 3
- WHEN the administrator clicks Confirm
- THEN the user is banned and up to 3 days of messages are deleted

#### Scenario: Ban confirmation shown before execution

- GIVEN an administrator invokes `/ban` on a user
- WHEN the command is invoked
- THEN an ephemeral embed shows target, reason, delete_days, and Confirm/Cancel buttons before any action

#### Scenario: Ban cancelled by administrator

- GIVEN an administrator sees the ban confirmation dialog
- WHEN the administrator clicks Cancel
- THEN the ban is not executed and a cancellation message is shown ephemerally

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


<!-- BEGIN DELTA: welcome-neon-timer-banana (sentinel-commands) -->

## ADDED Requirements
### Requirement: Author role hierarchy deny

The moderation target validation (`_validate_target`) MUST deny a mod action
when the author's `top_role <= target.top_role` (the author is not above the
target in the role hierarchy), in addition to the existing bot-hierarchy
check. The owner of the guild is exempt (the owner MAY act on any member). The
deny MUST send an ephemeral error embed (localized via `t()`) naming the
action and target, and MUST return `False` so no moderation mutation occurs.
This is a behavior change: mods who currently rely on bot-hierarchy-only MAY
now be denied when targeting someone at or above their own role. Strict TDD:
a RED test exercising the new author-hierarchy deny MUST be added before the
check is implemented, and the existing bot-hierarchy and owner-exemption
behaviors MUST remain unchanged.

#### Scenario: Mod denied when author role not above target

- GIVEN a mod author whose top role is equal to or below the target's top role
- WHEN the mod invokes a moderation action on that target
- THEN the author-hierarchy deny fires, an ephemeral error embed is sent, and no moderation mutation occurs

#### Scenario: Mod allowed when author role above target

- GIVEN a mod author whose top role is strictly above the target's top role
- WHEN the mod invokes a moderation action on that target
- THEN the author-hierarchy check passes and the action proceeds (subject to the bot-hierarchy check)

#### Scenario: Guild owner is exempt from author hierarchy

- GIVEN the guild owner invokes a moderation action on a member whose role is above the owner's nominal role
- WHEN `_validate_target` runs
- THEN the author-hierarchy check is bypassed (owner MAY act on any member) and the action proceeds subject to the bot-hierarchy check

#### Scenario: Existing bot-hierarchy deny unchanged

- GIVEN the bot's top role is at or below the target's top role and the target is not the owner
- WHEN `_validate_target` runs
- THEN the existing bot-hierarchy deny fires unchanged and no moderation mutation occurs

#### Scenario: RED test precedes the implementation

- GIVEN the author-hierarchy deny is not yet implemented
- WHEN the new test exercising the deny branch is run before implementation
- THEN the test FAILS (proving it tests the new behavior); after implementation it passes and the existing hierarchy tests remain green
<!-- END DELTA: welcome-neon-timer-banana (sentinel-commands) -->

<!-- BEGIN DELTA: voice-moderation-permissions (sentinel-commands) -->
## ADDED Requirements

### Requirement: Tempban command

The `/tempban` hybrid command MUST be gated by `@can_check("moderation.ban")` (dual-path prefix + slash) and `@app_commands.default_permissions(ban_members=True)`. The command MUST accept a target user, a duration string, and a reason. The duration MUST be parsed via `parse_duration_optional()` (None on invalid input). When the duration is invalid, the command MUST send an ephemeral error embed and MUST NOT ban. Before executing, the command MUST show an ephemeral `ConfirmCancelView` (target, duration, reason, Confirm/Cancel). On Confirm, the command MUST call `InfractionService.tempban()` (insert BAN with `expiresAt = NOW + duration`), ban the member via `member.ban()`, and send a permanent action embed to the channel. A user without `moderation.ban` (no matrix grant, no modRoleId fallback, no administrator) MUST be denied on both prefix and slash paths.

#### Scenario: Tempban command

- GIVEN a moderator with `moderation.ban`
- WHEN they invoke `/tempban @user 24h spam` and click Confirm
- THEN a `BAN` infraction is inserted with `expiresAt = NOW + 24h`, the member is banned, and a permanent confirm embed is sent to the channel

#### Scenario: Invalid duration rejected

- GIVEN a moderator invokes `/tempban @user notaduration spam`
- WHEN `parse_duration_optional("notaduration")` returns `None`
- THEN an ephemeral error embed is sent and no ban occurs

#### Scenario: Tempban denied without permission

- GIVEN a user without `moderation.ban` (no matrix grant, no modRoleId, no administrator)
- WHEN they invoke `/tempban`
- THEN access is denied on both prefix and slash paths

### Requirement: Unban command

The `/unban` hybrid command MUST be gated by `@can_check("moderation.ban")` and `@app_commands.default_permissions(ban_members=True)`. The command MUST accept a user ID. When an active `BAN` exists, the command MUST deactivate it (via `InfractionService.unban()`), lift the Discord ban (`guild.unban`), and send a permanent confirm embed. When no active `BAN` exists, the command MUST send an ephemeral info embed (idempotent — no error, no mutation). A user without `moderation.ban` MUST be denied on both paths.

#### Scenario: Unban command

- GIVEN a guild has an active `BAN` for a user and a moderator invokes `/unban <user_id>`
- WHEN the command executes
- THEN the BAN is deactivated, the Discord ban is lifted, and a permanent confirm embed is sent

#### Scenario: Unban idempotent

- GIVEN a guild has no active `BAN` for the user and a moderator invokes `/unban <user_id>`
- WHEN the command executes
- THEN an ephemeral info embed is sent (no error, no mutation)

#### Scenario: Unban denied without permission

- GIVEN a user without `moderation.ban`
- WHEN they invoke `/unban`
- THEN access is denied on both prefix and slash paths

### Requirement: Loop runs decay then expiry hourly

The `SentinelCog` MUST register a `@tasks.loop(hours=1)` that, on each iteration, runs `decay_warnings()` for each guild and then runs the tempban-expiry scan (`get_expired_tempbans` → `unban` + deactivate) for each guild, in one body. Each phase MUST log via `LoggingService`. The loop MUST `await bot.wait_until_ready()` before the first iteration (`@before_loop`). `cog_unload()` MUST cancel the loop (`is_running()` False, no further iteration). Loop logs MUST use brand tokens (no hex literals).

#### Scenario: Loop runs decay then expiry hourly

- GIVEN the loop is registered and the bot is ready
- WHEN the loop fires
- THEN `decay_warnings()` runs for each guild, then the tempban-expiry scan runs for each guild, and each phase logs via `LoggingService`

#### Scenario: Loop waits for bot ready

- GIVEN the loop is registered
- WHEN the bot is not yet ready
- THEN `before_loop` awaits `bot.wait_until_ready()` before the first iteration

#### Scenario: Loop cancels on cog unload

- GIVEN the loop is running
- WHEN `cog_unload()` is called
- THEN `is_running()` returns False and no further iteration occurs

#### Scenario: Loop logs use brand tokens

- GIVEN the loop fires
- WHEN each phase logs
- THEN the log entries use `brand.INFO`-adjacent tokens (no hex literals in `sentinel.py`)
<!-- END DELTA: voice-moderation-permissions (sentinel-commands) -->
