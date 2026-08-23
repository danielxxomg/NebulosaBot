# Delta for Infraction Service

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

## MODIFIED Requirements

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
