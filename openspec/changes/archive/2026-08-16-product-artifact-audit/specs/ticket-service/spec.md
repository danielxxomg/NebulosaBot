# Delta for Ticket Service

## ADDED Requirements

### Requirement: Shared idempotent evidence repair path

The ticket service MUST expose one repair path used by channel-delete events, periodic sweeps, and manual fallback. The path MUST use a conditional lifecycle transition and MUST return a reviewable result. Automatic event and sweep mutation requires BOTH a resolved live schema/deployment preflight and fresh, per-ticket Discord corroboration that the channel is absent. Missing, ambiguous, stale, or transient evidence MUST produce quarantine/report/no-op without mutation.

#### Scenario: Corroborated automatic repair

- GIVEN preflight is resolved and fresh evidence proves an active ticket's channel is absent
- WHEN a channel-delete event invokes repair
- THEN exactly one conditional close occurs and the result identifies the evidence

#### Scenario: Ambiguous evidence quarantines

- GIVEN channel existence is unknown, stale, or contradictory
- WHEN any entry point evaluates the ticket
- THEN it returns a reviewable quarantine/report result and performs no ticket mutation

#### Scenario: Duplicate event is idempotent

- GIVEN two delete events target the same active ticket
- WHEN both use the shared repair path
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition

### Requirement: Bounded sweeps and explicit manual authority

Integrity sweeps MUST process finite batches, honor backoff on transient Discord failures, and repair only corroborated safe cases. A failed or retried candidate MUST be reported for review without duplicate state transitions. Manual fallback MUST use the same path, require fresh corroboration, and record the initiating authority. Guild administrators MUST be restricted to their guild; bot operators MAY diagnose globally but MUST have an explicit, auditable mutation grant.

#### Scenario: Sweep defers a transient failure

- GIVEN a sweep candidate returns a Discord timeout or rate limit
- WHEN the candidate is evaluated
- THEN backoff and a reviewable skipped result are recorded, with no mutation

#### Scenario: Guild isolation denies cross-guild repair

- GIVEN a guild admin for guild A requests repair for a ticket in guild B
- WHEN manual fallback authorizes the request
- THEN the request is denied, an audit reason is recorded, and ticket B is unchanged

#### Scenario: Operator mutation is explicit

- GIVEN a bot operator diagnoses tickets globally without mutation authority
- WHEN the operator requests repair
- THEN diagnosis may be returned, but mutation is denied until an explicit authority is present and auditable

### Requirement: Canonical recovery lifecycle

`ticket-integrity-recovery` MUST remain the canonical lifecycle. Useful reconciliation contracts, including `CloseResult`, close-reason mapping, close ordering, localization, and evidence semantics, MUST be ported into this lifecycle before the conflicting active change is superseded or archived. This change MUST NOT introduce a parallel repair capability. Disabling the repair gate MUST preserve existing close behavior and deletion logging.

#### Scenario: Rollback is a no-op

- GIVEN repair activation is disabled or preflight is unresolved
- WHEN a candidate is detected
- THEN reports are retained, the ticket is untouched, and deletion-only logging continues
