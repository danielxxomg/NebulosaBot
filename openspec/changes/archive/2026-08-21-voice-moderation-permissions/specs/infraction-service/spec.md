# Delta for Infraction Service

## ADDED Requirements

### Requirement: Warn-decay deactivates

The system MUST deactivate `WARN` infractions older than 30 days via a `get_expired_warns(guild_id)` DB query (`type='WARN' AND active=true AND "createdAt" < NOW() - INTERVAL '30 days'`) and an `InfractionService.decay_warnings(guild_id)` method. The scan MUST be guild-scoped and MUST NOT touch future WARN rows. Each expired WARN row MUST be deactivated and the target member's `warnings` counter MUST be decremented by 1. The query MUST use explicit columns (no `select("*")`) and MUST leverage the partial index `idx_infraction_warn_decay`.

#### Scenario: Decay deactivates and decrements

- GIVEN a member has 3 active WARN infractions, 2 of which are older than 30 days
- WHEN `decay_warnings(guild_id)` runs
- THEN the 2 old WARN rows are deactivated and `Member.warnings` is decremented by 2 (3 → 1)

#### Scenario: Future WARN rows untouched

- GIVEN a member has 2 active WARN infractions older than 30 days and 1 future WARN
- WHEN `get_expired_warns(guild_id)` is called
- THEN only the 2 old rows are returned (the future WARN is untouched)

### Requirement: Tempban creates BAN with expiresAt

The system MUST provide an `InfractionService.tempban(guild_id, target_id, moderator_id, reason, expires_at) -> Infraction` method that inserts a `BAN` infraction with a non-null `expiresAt` via `insert_infraction(expires_at=...)`. The `expires_at` MUST be a future ISO-8601 timestamp. The caller (SentinelCog) is responsible for `member.ban()` and logging. The method MUST be async with `await` between DB ops (no blocking I/O).

#### Scenario: Tempban writes expiresAt

- GIVEN a moderator with `moderation.ban` invokes `/tempban @user 24h spam`
- WHEN `tempban()` is called with `expires_at = NOW + 24h`
- THEN a `BAN` infraction is inserted with `type='BAN'` and `expiresAt = NOW + 24h`

#### Scenario: No blocking I/O

- GIVEN any `tempban`/`unban`/`decay_warnings` call
- WHEN the method executes
- THEN it is async (`iscoroutinefunction`) and `await`s between DB ops

### Requirement: Unban removes an active ban

The system MUST provide an `InfractionService.unban(guild_id, target_id) -> Infraction | None` method that deactivates the most recent active `BAN` infraction. When no active `BAN` exists, the method MUST be idempotent: it MUST NOT raise and MUST return `None` (caller is informed, no mutation). The caller (SentinelCog) is responsible for lifting the Discord ban (`guild.unban`) when a `BAN` was deactivated.

#### Scenario: Unban removes an active ban

- GIVEN a guild has an active `BAN` infraction for a target
- WHEN `unban(guild_id, target_id)` is called
- THEN the active BAN is deactivated and the `Infraction` is returned (caller lifts the Discord ban)

#### Scenario: Unban is idempotent

- GIVEN a guild has no active `BAN` for the target
- WHEN `unban(guild_id, target_id)` is called
- THEN it returns `None` without raising (no mutation, caller informed)

### Requirement: Decay does not decrement below zero

The `decay_warnings()` method MUST floor `Member.warnings` at 0. When a member's counter is already 0 and an old WARN row exists, the row MUST still be deactivated but `warnings` MUST NOT go negative. The service MUST clamp the delta (`min(delta, current)`) as defense in depth, even though the `increment_member_warnings` RPC (009) also floors via `GREATEST(warnings, 0)`.

#### Scenario: Decay does not decrement below zero

- GIVEN a member has `warnings = 0` and an old WARN row
- WHEN `decay_warnings(guild_id)` runs
- THEN the old WARN row is deactivated and `warnings` stays 0 (no negative)

### Requirement: Escalation stays correct after decay

The `check_escalation` method MUST use exact-equality semantics (`warnings_count == threshold`) so escalation fires once per threshold crossing. After decay (e.g. 3 → 1) and a re-warn (→ 2), escalation MUST NOT re-fire the MUTE threshold (which fires at 3). The decay invariant MUST preserve exact-equality behavior.

#### Scenario: Escalation stays correct after decay

- GIVEN a member had 3 warnings (MUTE fired), decayed to 1, then re-warned to 2
- WHEN `check_escalation(guild_id, target_id)` is evaluated
- THEN it returns `None` (no re-fire at 2; exact-equality preserved)

### Requirement: Expired tempban is unbanned

The system MUST provide a `get_expired_tempbans(guild_id)` DB query (`type='BAN' AND active=true AND "expiresAt" <= NOW() AND "expiresAt" IS NOT NULL`) that returns guild-scoped expired tempbans. The query MUST use explicit columns and the partial index `idx_infraction_tempban_expiry`. The hourly loop in `SentinelCog` MUST call this scan and unban (deactivate + lift Discord ban) each expired tempban. The scan MUST be DB-sourced so a bot restart recovers pending unbans without an in-memory timer.

#### Scenario: Tempban expiry loop

- GIVEN a guild has an active `BAN` with `expiresAt` 1 hour in the past
- WHEN the hourly loop scans `get_expired_tempbans(guild_id)`
- THEN only the past-expiry row is returned (future-expiry rows are untouched) and the loop unbans it

#### Scenario: Restart durability via DB source of truth

- GIVEN a tempban was created, the bot was restarted, and `expiresAt` is now in the past
- WHEN the hourly loop fires after restart
- THEN the loop unbans the expired tempban (DB-sourced, no in-memory timer)
