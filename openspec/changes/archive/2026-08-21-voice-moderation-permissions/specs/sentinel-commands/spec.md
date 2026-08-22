# Delta for Sentinel Commands

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
