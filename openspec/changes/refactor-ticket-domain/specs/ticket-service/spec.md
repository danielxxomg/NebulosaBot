# Delta for Ticket Service

## ADDED Requirements

### Requirement: Guild-scoped ticket facade

The `TicketService` compatibility facade MUST require guild ownership for S2 ticket reads, mutations, and repair entry points. A request targeting another guild MUST NOT disclose or mutate that guild's ticket. Existing public service names and persistent view custom IDs MUST remain compatible.

#### Scenario: Numeric reference is guild-scoped

- GIVEN guild A and guild B may use the same ticket number
- WHEN guild A resolves a numeric repair reference
- THEN only guild A's ticket is eligible

#### Scenario: Channel deletion cannot cross guilds

- GIVEN a deleted channel event belongs to guild A
- WHEN the service looks up an active ticket
- THEN only the guild A and channel A pair is considered

#### Scenario: Public facade remains compatible

- GIVEN existing cogs, listeners, and views call `TicketService`
- WHEN the S2 repair seam is enabled
- THEN those callers continue using the facade without a parallel repair API

### Requirement: Single repair eligibility seam

`TicketService` MUST route channel-delete handling, integrity sweeps, and manual/reference repair through one `evaluate_repair_eligibility` decision and one conditional guild-scoped transition. Adapters MUST NOT duplicate gate/evidence decisions or mutate ticket rows directly. Denied decisions MUST return reviewable no-op results.

#### Scenario: Unresolved preflight fails closed

- GIVEN live preflight is unresolved and evidence reports a missing channel
- WHEN any repair entry point evaluates the ticket
- THEN it returns `skipped` with `gate_unresolved` and performs no transition

#### Scenario: Unknown evidence is quarantined

- GIVEN preflight is resolved but channel evidence is unknown or stale
- WHEN a repair entry point evaluates the ticket
- THEN it returns `skipped` with `evidence_unresolved` and performs no mutation

#### Scenario: Corroborated repair has one winner

- GIVEN resolved preflight and corroborated evidence for an active ticket
- WHEN event, sweep, or manual paths race
- THEN exactly one conditional close succeeds and later attempts return `already_closed`

## MODIFIED Requirements

### Requirement: Shared idempotent evidence repair path

The ticket service MUST expose one repair path used by channel-delete events, periodic sweeps, and manual fallback. The path MUST use `evaluate_repair_eligibility`, a guild-scoped conditional lifecycle transition, and a reviewable result. Automatic event and sweep mutation requires BOTH resolved live schema/deployment preflight and fresh, per-ticket Discord corroboration. Missing, ambiguous, stale, or transient evidence MUST produce quarantine/report/no-op without mutation.
(Previously: the shared path required a conditional close and evidence gate but did not explicitly define the single eligibility seam and guild-scoped facade contract.)

#### Scenario: Corroborated automatic repair

- GIVEN preflight is resolved and fresh evidence proves an active ticket's channel is absent
- WHEN a channel-delete event invokes repair
- THEN exactly one guild-scoped conditional close occurs and the result identifies the evidence

#### Scenario: Ambiguous evidence quarantines

- GIVEN channel existence is unknown, stale, or contradictory
- WHEN any entry point evaluates the ticket
- THEN it returns a reviewable quarantine/report result and performs no ticket mutation

#### Scenario: Duplicate event is idempotent

- GIVEN two delete events target the same active ticket
- WHEN both use the shared repair path
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition
