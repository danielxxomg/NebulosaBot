# Delta for infraction-service

> Change: `cycle-5-quality-zero`. Scope: ADDED `mute`/`kick`/`ban` service methods mirroring the `tempban`/`unban` method contract, with Sentinel callsite swaps and audit-path consistency.

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
