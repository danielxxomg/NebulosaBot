# Delta for Sentinel Commands

## MODIFIED Requirements

### Requirement: Warn command

The `/warn` command MUST be gated by `@can_check("moderation.warn")` (matrix-gated, dual path prefix + slash) and MUST create a WARN infraction with a reason. A user without the `moderation.warn` matrix grant, the mod-role fallback, or administrator MUST be denied on both paths, with the error naming the missing permission.

(Previously: the command was gated by `@is_mod()`.)

#### Scenario: Moderator warns user

- GIVEN a moderator invokes `/warn` on a guild member with reason "spam"
- THEN a WARN infraction is created and the target is notified

#### Scenario: Warn denied without matrix grant

- GIVEN a user without `moderation.warn`, mod role, or administrator
- WHEN they invoke `/warn` on either path
- THEN access is denied with an error referencing `moderation.warn`

### Requirement: Unwarn command

The `/unwarn` command MUST be gated by `@can_check("moderation.warn")` and MUST allow a moderator to remove the most recent active warning. Denial semantics match the matrix gate above.

(Previously: the command was gated by `@is_mod()`.)

#### Scenario: Moderator unwarns user

- GIVEN a member has an active WARN infraction
- WHEN a moderator invokes `/unwarn`
- THEN the warning is removed and `Member.warnings` is decremented

#### Scenario: Unwarn denied without matrix grant

- GIVEN a user without `moderation.warn`, mod role, or administrator
- WHEN they invoke `/unwarn` on either path
- THEN access is denied with an error referencing `moderation.warn`

### Requirement: Mute command

The `/mute` command MUST be gated by `@can_check("moderation.mute")` and MUST timeout a member for an optional duration, defaulting to 1 hour.

(Previously: the command was gated by `@is_mod()`.)

#### Scenario: Mute with default duration

- GIVEN a moderator invokes `/mute` without a duration
- THEN the member is timed out for 1 hour

#### Scenario: Mute with custom duration

- GIVEN a moderator invokes `/mute` with duration "30m"
- THEN the member is timed out for 30 minutes

#### Scenario: Mute denied without matrix grant

- GIVEN a user without `moderation.mute`, mod role, or administrator
- WHEN they invoke `/mute` on either path
- THEN access is denied with an error referencing `moderation.mute`

### Requirement: Unmute command

The `/unmute` command MUST be gated by `@can_check("moderation.mute")` and MUST remove an active timeout.

(Previously: the command was gated by `@is_mod()`.)

#### Scenario: Moderator unmutes user

- GIVEN a member is currently muted
- WHEN a moderator invokes `/unmute`
- THEN the timeout is removed

#### Scenario: Unmute denied without matrix grant

- GIVEN a user without `moderation.mute`, mod role, or administrator
- WHEN they invoke `/unmute` on either path
- THEN access is denied with an error referencing `moderation.mute`

### Requirement: Kick command

The `/kick` command MUST be gated by `@can_check("moderation.kick")` and MUST remove a member from the guild and create a KICK infraction. Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, and Confirm/Cancel buttons; the kick proceeds only on explicit Confirm. The FINAL action result MUST be delivered as a permanent channel message; it MUST NOT live only as an edit of the ephemeral dialog.

(Previously: gated by `@is_mod()`, and the final result only edited the ephemeral confirmation message.)

#### Scenario: Moderator kicks user

- GIVEN a moderator invokes `/kick` with reason "trolling"
- WHEN the moderator clicks Confirm on the ephemeral confirmation dialog
- THEN the member is removed, a KICK infraction is persisted, and a permanent result embed is sent to the channel

#### Scenario: Kick confirmation shown before execution

- GIVEN a moderator invokes `/kick` on a user
- WHEN the command is invoked
- THEN an ephemeral embed shows target, reason, and Confirm/Cancel buttons before any action

#### Scenario: Kick cancelled by moderator

- GIVEN a moderator sees the kick confirmation dialog
- WHEN the moderator clicks Cancel
- THEN the kick is not executed and a cancellation message is shown ephemerally

#### Scenario: Kick final result is permanent

- GIVEN a kick executed successfully
- WHEN the result message is posted
- THEN it is permanent in the channel, visible to all members

#### Scenario: Kick denied without matrix grant

- GIVEN a user without `moderation.kick`, mod role, or administrator
- WHEN they invoke `/kick` on either path
- THEN access is denied with an error referencing `moderation.kick`

### Requirement: Ban command

The `/ban` command MUST be gated by `@can_check("moderation.ban")`, ban a user, and accept optional `delete_days` (0–7, default 0). Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, delete_days, and Confirm/Cancel buttons; the ban proceeds only on explicit Confirm. The FINAL action result MUST be delivered as a permanent channel message; it MUST NOT live only as an edit of the ephemeral dialog.

(Previously: described as administrator-restricted, and the final result only edited the ephemeral confirmation message.)

#### Scenario: Admin bans user

- GIVEN an administrator invokes `/ban` with reason "harassment"
- WHEN the administrator clicks Confirm on the ephemeral confirmation dialog
- THEN the user is banned, a BAN infraction is created, and a permanent result embed is sent to the channel

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

#### Scenario: Ban final result is permanent

- GIVEN a ban executed successfully
- WHEN the result message is posted
- THEN it is permanent in the channel, visible to all members

### Requirement: Tempban command

The `/tempban` hybrid command MUST be gated by `@can_check("moderation.ban")` (dual-path prefix + slash) and `@app_commands.default_permissions(ban_members=True)`. The command MUST accept a target user, a duration string, and a reason. The duration MUST be parsed via `parse_duration_optional()` (None on invalid input). When the duration is invalid, the command MUST send an ephemeral error embed and MUST NOT ban. Before executing, the command MUST show an ephemeral `ConfirmCancelView` (target, duration, reason, Confirm/Cancel). On Confirm, the command MUST call `InfractionService.tempban()` (insert BAN with `expiresAt = NOW + duration`), ban the member via `member.ban()`, and send a permanent action embed to the channel. A user without `moderation.ban` (no matrix grant, no modRoleId fallback, no administrator) MUST be denied on both prefix and slash paths. The `expires_at` value MUST be computed exactly once at execution time — after the moderator confirms — and that single value MUST be used for the DB insert and all logging, so `expiresAt` reflects the real ban start regardless of how long the dialog stayed open.

(Previously: `expires_at` was computed before the confirmation dialog appeared, drifting from the actual ban start by the dialog latency.)

#### Scenario: Tempban command

- GIVEN a moderator with `moderation.ban`
- WHEN they invoke `/tempban @user 24h spam` and click Confirm
- THEN a `BAN` infraction is inserted with `expiresAt = (execution time + 24h)`, the member is banned, and a permanent confirm embed is sent to the channel

#### Scenario: Invalid duration rejected

- GIVEN a moderator invokes `/tempban @user notaduration spam`
- WHEN `parse_duration_optional("notaduration")` returns `None`
- THEN an ephemeral error embed is sent and no ban occurs

#### Scenario: Tempban denied without permission

- GIVEN a user without `moderation.ban` (no matrix grant, no modRoleId, no administrator)
- WHEN they invoke `/tempban`
- THEN access is denied on both prefix and slash paths

#### Scenario: Expiry has no confirmation drift

- GIVEN the moderator waits the full 30s dialog timeout before clicking Confirm on `/tempban @user 24h`
- WHEN the ban executes
- THEN `expiresAt` equals execution-time + 24h (not invocation-time + 24h), computed once and shared by DB insert and logs

### Requirement: Unban command

The `/unban` hybrid command MUST be gated by `@can_check("moderation.ban")` and `@app_commands.default_permissions(ban_members=True)`. The command MUST accept a user ID and MUST resolve it into a typed `UnbanTarget` value object (a dataclass carrying the user id plus display metadata such as mention/name). The implementation MUST NOT fabricate attributes on `discord.Object` nor silence attribute errors with `type: ignore`. When an active `BAN` exists, the command MUST deactivate it (via `InfractionService.unban()`), lift the Discord ban (`guild.unban`), and send a permanent confirm embed. When no active `BAN` exists, the command MUST send an ephemeral info embed (idempotent — no error, no mutation). A user without `moderation.ban` MUST be denied on both paths.

(Previously: the target was a `discord.Object` with monkey-patched `.mention`/`.name` under `type: ignore`.)

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

#### Scenario: Target resolved via typed value object

- GIVEN `/unban` resolves its target
- WHEN the target object is inspected
- THEN it is an `UnbanTarget` dataclass instance and no framework object has had attributes attached post-construction
