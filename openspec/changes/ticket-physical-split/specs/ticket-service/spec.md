# Delta for Ticket Service

## ADDED Requirements

### Requirement: Facade-preserving service composition

`TicketService` MUST remain the stable public facade while composing `TicketQueryService`, `TicketLifecycleService`, and `TicketRepairService`. Query/cache reads, lifecycle mutations, and repair/channel orchestration MUST each have one owner. The facade MUST delegate each operation once and MUST NOT duplicate cache, audit, or invariant mutation.

#### Scenario: Existing callers remain compatible

- GIVEN cogs, listeners, and views import `TicketService`
- WHEN the physical split is enabled
- THEN existing public method calls and return contracts continue to work through the facade

#### Scenario: Query ownership is singular

- GIVEN a caller requests a guild-scoped ticket or cache lookup
- WHEN the request passes through `TicketService`
- THEN `TicketQueryService` performs the read and exactly one owner updates the cache

#### Scenario: Lifecycle ownership is singular

- GIVEN a caller claims, closes, reopens, or transfers a ticket
- WHEN the facade delegates the operation
- THEN `TicketLifecycleService` owns the transition and no facade or sibling repeats it

### Requirement: Single repair eligibility seam after extraction

Channel-delete events, bounded sweeps, and manual or reference repairs MUST delegate to `TicketRepairService`, which MUST use one `evaluate_repair_eligibility` decision and one guild-scoped conditional transition. Adapters MUST NOT decide evidence eligibility or mutate ticket rows directly.

#### Scenario: All repair entry points share one decision

- GIVEN an event, sweep, and manual request target the same ticket
- WHEN each request is evaluated
- THEN all use the same eligibility seam and produce reviewable results

#### Scenario: Repair race remains idempotent

- GIVEN two corroborated repair requests race for one active ticket
- WHEN both reach persistence
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition

#### Scenario: Unresolved evidence remains safe

- GIVEN preflight or channel evidence is unresolved
- WHEN any extracted repair path evaluates the ticket
- THEN it reports a skipped/quarantined result and performs no mutation
