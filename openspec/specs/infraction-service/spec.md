# Infraction Service Specification

## Purpose

Centralize creation, retrieval, update, and deletion of moderation infractions, keep the denormalized `Member.warnings` counter in sync, and apply automatic escalation when warning thresholds are reached.

## Requirements

### Requirement: Create infraction

The system MUST create an `Infraction` record and increment `Member.warnings` when a warning is issued.

#### Scenario: Warn user

- GIVEN a guild member has 0 warnings
- WHEN a moderator issues a WARN infraction
- THEN the infraction is persisted and the member's warning count becomes 1

### Requirement: Read infractions

The system MUST retrieve infractions scoped to a guild and target user, optionally filtered by type and active status.

#### Scenario: List active warnings

- GIVEN a member has 2 active WARN infractions in a guild
- WHEN the service queries active warnings for that member
- THEN it returns exactly those 2 infractions

### Requirement: Update infraction

The system MUST allow a moderator to update an existing infraction's reason and active state.

#### Scenario: Edit reason

- GIVEN an active WARN infraction exists
- WHEN a moderator updates its reason to "updated reason"
- THEN the persisted reason is changed and active remains true

### Requirement: Delete infraction

The system MUST allow authorized moderators to delete an infraction and decrement the member's warning count.

#### Scenario: Delete warning

- GIVEN a member has 2 warnings and an infraction exists
- WHEN the infraction is deleted
- THEN the infraction is removed and the warning count becomes 1

### Requirement: Auto-escalation at 3 warnings

The system MUST automatically apply a 1-hour mute when a member's warning count reaches 3.

#### Scenario: Third warning triggers mute

- GIVEN a member has 2 warnings
- WHEN a moderator issues the third WARN infraction
- THEN a 1-hour MUTE infraction is created and the member is muted for 1 hour

### Requirement: Auto-escalation at 5 warnings

The system MUST automatically kick the member when the warning count reaches 5.

#### Scenario: Fifth warning triggers kick

- GIVEN a member has 4 warnings
- WHEN a moderator issues the fifth WARN infraction
- THEN a KICK infraction is created and the member is removed from the guild

### Requirement: Escalation notification

The system SHOULD notify the target user and the channel when an escalation action is taken.

#### Scenario: Notify on auto-mute

- GIVEN a member reaches 3 warnings
- WHEN the auto-escalation mute is applied
- THEN the member receives a DM and a public message is sent in the channel

<!-- BEGIN DELTA: cycle-5-quality-zero (infraction-service) -->
## ADDED Requirements

### Requirement: Moderation action service methods (mute/kick/ban)

`InfractionService` MUST provide async `mute()`, `kick()`, and `ban()` methods mirroring the `tempban()` contract shape: each takes guild/target/moderator/reason identifiers (`mute()` additionally accepts an optional `expires_at` for timed mutes), owns the infraction DB insert via the shared insert path, persists the corresponding type row (`MUTE`, `KICK`, `BAN`), and returns the persisted `Infraction`. The service MUST NOT perform any Discord action — the caller (SentinelCog) remains responsible for the Discord side-effect (`timeout()`/`kick()`/`ban()`) exactly as with `tempban`. Audit-path consistency: every executed action MUST be audited via `LoggingService.log_moderation_action` at exactly one callsite — the same single audit path as tempban; no duplicate or dropped audit entries. Methods MUST be async with `await` between DB ops (no blocking I/O). SentinelCog moderation callsites MUST persist through these methods — cogs MUST NOT insert infraction rows directly.

#### Scenario: Mute persists and returns Infraction

- GIVEN a moderator executes `/mute @user 1h spam`
- WHEN `mute(guild_id, target_id, moderator_id, reason, expires_at=NOW+1h)` is called
- THEN a `MUTE` infraction row is inserted with `type='MUTE'` and `expiresAt = NOW + 1h`, and the persisted `Infraction` is returned

#### Scenario: Kick persists and returns Infraction

- GIVEN a moderator confirms a `/kick` dialog
- WHEN `kick(...)` is called
- THEN a `KICK` infraction row is inserted and the persisted `Infraction` is returned

#### Scenario: Ban persists and returns Infraction

- GIVEN an administrator confirms a `/ban` dialog
- WHEN `ban(...)` is called
- THEN a `BAN` infraction row is inserted and the persisted `Infraction` is returned

#### Scenario: Service performs no Discord action

- GIVEN any `mute`/`kick`/`ban` service call
- WHEN the method executes
- THEN no Discord API mutation occurs inside the service (the caller performs `timeout()`/`kick()`/`ban()` as with tempban)

#### Scenario: Async contract holds

- GIVEN any `mute`/`kick`/`ban` call
- WHEN the method executes
- THEN it is async (`iscoroutinefunction`) and `await`s between DB ops

#### Scenario: Audit path consistency

- GIVEN a moderation action executed end-to-end through a service method
- WHEN the flow completes
- THEN exactly one `log_moderation_action` entry is produced by the caller (same routing as tempban; none duplicated, none dropped)

#### Scenario: Sentinel callsite swap

- GIVEN the SentinelCog mute/kick/ban commands are inspected
- WHEN their persistence step is examined
- THEN they invoke `infraction_service.mute/kick/ban` and contain no direct infraction-row inserts
<!-- END DELTA: cycle-5-quality-zero (infraction-service) -->

<!-- BEGIN DELTA: voice-moderation-permissions (infraction-service) -->
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

The system MUST provide a `get_expired_tempbans(guild_id)` DB query (`type='BAN' AND active=true AND "expiresAt" <= NOW() AND "expiresAt" IS NOT NULL`) that returns guild-scoped expired tempbans. The query MUST use explicit columns and the partial index `idx_infraction_tempban_expiry`. The hourly loop in `SentinelCog` MUST call this scan and process each expired tempban by lifting the Discord ban FIRST and deactivating the infraction row ONLY after the unban succeeds; an `unban_fn` raising `NotFound` MUST be treated as success (the manual `/unban` race). Any other unban failure MUST leave the row ACTIVE, log a warning, and skip deactivation; because the scan is DB-sourced, the next hourly iteration re-selects the still-active expired row and retries — no retry flag or schema change. Loop cadence and log routing are unchanged.

(Previously: unban failure was logged non-fatally and the row was deactivated anyway, leaving the Discord ban in place with no retry path.)

#### Scenario: Tempban expiry loop

- GIVEN a guild has an active `BAN` with `expiresAt` 1 hour in the past
- WHEN the hourly loop scans `get_expired_tempbans(guild_id)`
- THEN only the past-expiry row is returned (future-expiry rows are untouched) and the loop processes it

#### Scenario: Restart durability via DB source of truth

- GIVEN a tempban was created, the bot was restarted, and `expiresAt` is now in the past
- WHEN the hourly loop fires after restart
- THEN the loop unbans the expired tempban (DB-sourced, no in-memory timer)

#### Scenario: Unban success deactivates

- GIVEN an expired tempban whose Discord unban succeeds
- WHEN the loop processes it
- THEN the infraction row is deactivated after the unban and counted as processed

#### Scenario: NotFound treated as success

- GIVEN an expired tempban whose Discord ban was already lifted manually
- WHEN `unban_fn` raises `NotFound`
- THEN this counts as success: the row is deactivated and no warning is raised

#### Scenario: Failed unban keeps row active

- GIVEN an expired tempban whose unban fails with an error other than `NotFound`
- WHEN the loop processes it
- THEN the row stays active, a warning is logged, and the row is NOT deactivated

#### Scenario: Next scan retries the failure

- GIVEN a row left active by a previous failed unban
- WHEN the next hourly scan runs after the transient failure clears
- THEN the same row is re-selected, the unban succeeds, and the row is deactivated
<!-- END DELTA: voice-moderation-permissions (infraction-service) -->

<!-- BEGIN DELTA: cycle-4-debt-zero (infraction-service) -->
## ADDED Requirements

### Requirement: Apply escalation service method

`InfractionService` MUST provide `async apply_escalation(*, guild_id, member, moderator, escalation) -> str` with keyword-only parameters. The service MUST own the full escalation side-effect chain: execute the Discord action implied by `escalation.action` (MUTE → timeout for the escalation duration; KICK → remove the member from the guild), insert the corresponding infraction row, and log the moderation action via `LoggingService`. It MUST return the localized result message fragment (str) for the caller to embed. Only `discord.Forbidden` MAY be caught: on Forbidden the method MUST return the failure fragment WITHOUT persisting an infraction row or logging success; any other exception MUST propagate to the caller. The cog retains input validation and embed delivery only — no escalation business logic in the cog.

#### Scenario: Auto-mute escalation applied

- GIVEN a member's warning count crosses the MUTE threshold
- WHEN `apply_escalation(...)` is called with a MUTE escalation (1 hour)
- THEN the member is timed out, a MUTE infraction is inserted, the action is logged via `LoggingService`, and a success fragment is returned

#### Scenario: Auto-kick escalation applied

- GIVEN a member's warning count crosses the KICK threshold
- WHEN `apply_escalation(...)` is called with a KICK escalation
- THEN the member is removed from the guild, a KICK infraction is inserted, the action is logged, and a success fragment is returned

#### Scenario: Forbidden yields failure fragment without persistence

- GIVEN the bot lacks permission for the Discord action
- WHEN the action raises `discord.Forbidden`
- THEN the failure fragment is returned, no infraction row is inserted, and no success log entry is produced

#### Scenario: Unexpected errors propagate

- GIVEN the database insert raises an unexpected exception
- WHEN `apply_escalation(...)` runs
- THEN the exception propagates to the caller (it MUST NOT be swallowed into a fragment)
<!-- END DELTA: cycle-4-debt-zero (infraction-service) -->
