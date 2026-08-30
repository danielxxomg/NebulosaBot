# Delta for sentinel-commands

## MODIFIED Requirements

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
