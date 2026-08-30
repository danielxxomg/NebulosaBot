# Sentinel Commands Specification

## Purpose

Expose moderation actions as slash-only Discord commands with permission guards. Bot core is slash-only (`get_prefix -> []`); no prefix/hybrid path.

## Requirements

### Requirement: Warn command

`/warn` MUST be slash-only `@app_commands.command()` gated by `@can_check("moderation.warn")`; prefix inert; creates WARN; denial via `t()`.

(Previously: hybrid via `@is_mod()`)

#### Scenario: Moderator warns

- GIVEN moderator invokes `/warn` via slash with "spam"
- WHEN it executes
- THEN WARN created

#### Scenario: Warn denied

- GIVEN user without `moderation.warn`/mod/admin
- WHEN they invoke `/warn` via slash
- THEN denied via `t()`

### Requirement: Unwarn command

`/unwarn` MUST be slash-only gated by `@can_check("moderation.warn")`; removes most recent WARN.

(Previously: hybrid `@is_mod()`)

#### Scenario: Moderator unwarns

- GIVEN member has active WARN
- WHEN moderator invokes `/unwarn` via slash
- THEN warning removed

#### Scenario: Unwarn denied

- GIVEN user without `moderation.warn`/mod/admin
- WHEN they invoke `/unwarn` via slash
- THEN denied via `t()`

### Requirement: Mute command

`/mute` MUST be slash-only gated by `@can_check("moderation.mute")`; timeouts member (default 1h).

(Previously: hybrid `@is_mod()`)

#### Scenario: Mute default

- GIVEN moderator invokes `/mute` via slash without duration
- WHEN it executes
- THEN timed out 1h

#### Scenario: Mute denied

- GIVEN user without `moderation.mute`/mod/admin
- WHEN they invoke `/mute` via slash
- THEN denied via `t()`

### Requirement: Unmute command

`/unmute` MUST be slash-only gated by `@can_check("moderation.mute")`; removes timeout.

(Previously: hybrid `@is_mod()`)

#### Scenario: Moderator unmutes

- GIVEN member is muted
- WHEN moderator invokes `/unmute` via slash
- THEN timeout removed

#### Scenario: Unmute denied

- GIVEN user without `moderation.mute`/mod/admin
- WHEN they invoke `/unmute` via slash
- THEN denied via `t()`

### Requirement: Kick command

`/kick` MUST be slash-only gated by `@can_check("moderation.kick")`; removes member via `ConfirmCancelView`; final permanent via `t()`.

(Previously: hybrid `@is_mod()`; final only edited ephemeral)

#### Scenario: Kick succeeds

- GIVEN moderator invokes `/kick` via slash and Confirm
- WHEN it executes
- THEN member removed and permanent embed via `t()`

#### Scenario: Kick denied

- GIVEN user without `moderation.kick`/mod/admin
- WHEN they invoke `/kick` via slash
- THEN denied via `t()`

### Requirement: Ban command

`/ban` MUST be slash-only gated by `@can_check("moderation.ban")`; `delete_days` 0-7 (default 0); shows `ConfirmCancelView`; final permanent via `t()`.

(Previously: hybrid dual path; final only edited ephemeral)

#### Scenario: Ban succeeds

- GIVEN admin invokes `/ban` via slash and Confirm
- WHEN it executes
- THEN user banned and permanent embed via `t()`

#### Scenario: Ban cancelled

- GIVEN admin sees ban dialog
- WHEN they click Cancel
- THEN not executed and cancellation via `t()`

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

`/tempban` MUST be slash-only gated by `@can_check("moderation.ban")` + `ban_members=True`; accept target/duration/reason; parse via `parse_duration_optional()` (None→ error via `t()`); show `ConfirmCancelView`; on Confirm call `InfractionService.tempban()` with `expiresAt=NOW+duration` computed once after Confirm, then `member.ban()`.

(Previously: hybrid; `expires_at` before dialog)

#### Scenario: Tempban succeeds

- GIVEN moderator with `moderation.ban` invokes `/tempban @user 24h` via slash and Confirm
- WHEN it executes
- THEN BAN `expiresAt=execution+24h` inserted and member banned

#### Scenario: Invalid duration

- GIVEN moderator invokes `/tempban` with invalid duration
- WHEN `parse_duration_optional` returns `None`
- THEN error via `t()` and no ban

#### Scenario: No drift

- GIVEN moderator waits 30s before Confirm on `/tempban`
- WHEN it executes
- THEN `expiresAt` equals execution-time+24h (once)

### Requirement: Unban command

`/unban` MUST be slash-only gated by `@can_check("moderation.ban")` + `ban_members=True`; accept user ID; resolve into `UnbanTarget` dataclass (no `discord.Object` patch, no `type: ignore`); deactivate `BAN` via `InfractionService.unban()` + `guild.unban`; when no `BAN`, ephemeral info.

(Previously: hybrid; target `discord.Object` patched under `type: ignore`)

#### Scenario: Unban succeeds

- GIVEN guild has active `BAN` and moderator invokes `/unban <id>` via slash
- WHEN it executes
- THEN BAN deactivated, Discord ban lifted, permanent via `t()`

#### Scenario: Unban idempotent

- GIVEN no active `BAN` and moderator invokes `/unban <id>` via slash
- WHEN it executes
- THEN ephemeral info via `t()` (no mutation)

#### Scenario: Typed target

- GIVEN `/unban` resolves target via slash
- WHEN inspected
- THEN `UnbanTarget` dataclass and no framework object mutated
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
