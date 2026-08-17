# Delta for Ticket Invariants

## ADDED Requirements

### Requirement: Two-factor repair invariant

Automatic repair MUST be authorized only when the deployment/schema preflight is verified and the per-ticket Discord evidence is fresh, unambiguous, guild-matched, and corroborates channel absence for an active ticket. Any missing, stale, future-dated, transient, or ambiguous input MUST fail closed to quarantine/report/no-op. The channel deletion actor MUST NOT participate in this decision.

#### Scenario: Both gates permit repair

- GIVEN verified live preflight and fresh corroborated evidence for an active ticket
- WHEN the repair invariant is evaluated
- THEN automatic mutation is permitted

#### Scenario: Stale preflight blocks repair

- GIVEN schema evidence is stale or deployment compatibility is unverified
- WHEN fresh channel-absence evidence is evaluated
- THEN the invariant denies mutation and requires a reviewable result

#### Scenario: Ambiguous evidence blocks repair

- GIVEN Discord evidence is unknown, contradictory, or not per-ticket
- WHEN repair authorization is evaluated
- THEN mutation is denied and no state transition is allowed

### Requirement: Scoped repair authority

Guild administrators MUST be authorized only for operations targeting their own guild. Bot operators MAY diagnose across guilds, but operator mutation authority MUST be an explicit operation-level grant and MUST be recorded with actor, scope, target guild, and outcome. No caller role or audit-log attribution MAY implicitly grant mutation authority.

#### Scenario: Same-guild admin allowed

- GIVEN an administrator targets a corroborated ticket in their guild
- WHEN authority is evaluated
- THEN the guild-scoped operation may proceed through the shared service path

#### Scenario: Cross-guild admin denied

- GIVEN an administrator for guild A targets guild B
- WHEN authority is evaluated
- THEN mutation is denied and the target ticket remains unchanged

#### Scenario: Global diagnosis is read-only

- GIVEN an operator has global diagnosis but no explicit mutation grant
- WHEN the operator requests a repair
- THEN diagnosis is allowed, mutation is denied, and the denial is auditable

### Requirement: Audit invariant for outcomes

Every denied or failed repair MUST produce best-effort audit evidence with a non-empty reason. Quarantine and no-op outcomes MUST NOT be recorded as successful mutation. Duplicate-event losers MUST produce a deterministic denied/no-op audit outcome without a second success transition; audit-write failure MUST be logged and MUST NOT create a false success claim.

#### Scenario: Denied operation is reviewable

- GIVEN a permission or evidence gate denies repair
- WHEN the operation returns
- THEN a non-empty denied/quarantine reason is available to audit and review

#### Scenario: No-op is not mutation

- GIVEN a ticket is already closed or no safe candidate exists
- WHEN repair completes
- THEN no success mutation audit is written
