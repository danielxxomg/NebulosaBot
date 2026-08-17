# Delta for Audit Listener

## ADDED Requirements

### Requirement: Authoritative channel-delete routing

`on_guild_channel_delete` MUST preserve the existing channel audit log and route active-ticket detection to the Ticket Service shared repair path. The listener MUST provide guild and channel facts for per-ticket corroboration, but MUST NOT mutate tickets independently. An audit-log actor, when available, is informational only and MUST NOT decide integrity, authorization, or repair.

#### Scenario: Deleted ticket channel is routed

- GIVEN an active ticket maps to the deleted channel
- WHEN `on_guild_channel_delete` fires
- THEN the shared service path receives the event and no parallel mutation occurs

#### Scenario: Non-ticket deletion preserves behavior

- GIVEN no active ticket maps to the deleted channel
- WHEN the event fires
- THEN normal deletion logging continues and no repair result is claimed

#### Scenario: Actor attribution cannot authorize repair

- GIVEN the Discord audit event identifies an actor who deleted the channel
- WHEN repair eligibility is evaluated
- THEN the actor is recorded as context only and cannot make unsafe evidence actionable

### Requirement: Shared entry-point delegation

Startup sweeps, periodic sweeps, and manual fallback triggers MUST delegate candidate evaluation to the same Ticket Service repair path. The listener MUST honor its bounded batch and backoff result, and MUST surface transient or ambiguous outcomes for review instead of retrying with an independent mutation path.

#### Scenario: Duplicate delete events converge

- GIVEN duplicate delete events arrive for one ticket
- WHEN both are dispatched
- THEN the shared path yields one transition and one deterministic no-op outcome

#### Scenario: Transient Discord failure is deferred

- GIVEN a per-ticket channel check raises a timeout or rate-limit error
- WHEN the event or sweep is processed
- THEN the candidate is reported/quarantined and no ticket mutation occurs

#### Scenario: Preflight is stale

- GIVEN schema/deployment preflight is stale while a deleted ticket channel is detected
- WHEN the listener dispatches the candidate
- THEN detection and reporting occur, but automatic repair is not attempted
