# Delta for Database Layer

## ADDED Requirements

### Requirement: Verified schema and deployment preflight

The database layer MUST provide a read-only preflight result that is resolved only from verified, fresh schema/deployment evidence. The diagnostic fact `active_rows_channel_id_non_null` MAY be reported with that evidence, but MUST be informational only and MUST NOT be required for `LivePreflightResult.resolved` or authorize repair. Evidence verified on 2026-08-11 records project `ACTIVE_HEALTHY`, migration 015 applied, nullable `ticket.closeReason`, required active/channel/guild indexes, Realtime publication coverage for `guild`, `greeting_config`, `ticket`, and `ticket_note`, and three active rows with non-null channel IDs. This proves schema readiness only; it MUST NOT be treated as proof that Discord channels exist. Automatic mutation still requires fresh per-ticket Discord corroboration.

#### Scenario: Live schema evidence permits the preflight half

- GIVEN the listed live evidence is verified and fresh
- WHEN preflight evaluates deployment compatibility
- THEN the schema/deployment half is resolved without mutating tickets

#### Scenario: Stale or missing evidence fails closed

- GIVEN migration, deployment, or index evidence is missing, stale, or incompatible
- WHEN preflight runs
- THEN it returns unresolved and automatic repair remains disabled

#### Scenario: Preflight is read-only

- GIVEN any preflight result
- WHEN the database layer evaluates it
- THEN no ticket row is inserted, updated, or deleted

### Requirement: Guild-scoped conditional repair persistence

The database layer MUST expose guild-scoped active-ticket lookup and a conditional active-to-closed transition for the shared service path. The transition MUST return the winning row or a deterministic no-op for an already-closed/missing ticket, preserve existing close reason when no new reason is supplied, and never permit a second success transition. Audit writes MUST retain non-empty denial/quarantine reasons.

#### Scenario: Conditional transition has one winner

- GIVEN two repair attempts target the same active ticket
- WHEN both reach persistence
- THEN one update wins and the other returns no-op without a duplicate close

#### Scenario: Guild isolation is enforced

- GIVEN identical channel IDs or ticket IDs are queried for guilds A and B
- WHEN guild A lookup runs
- THEN only guild A rows are eligible for detection or mutation

#### Scenario: No-op preserves state

- GIVEN a ticket is already closed
- WHEN a repair transition runs
- THEN no row changes and the result cannot claim mutation

### Requirement: Explicit non-goals for advisor findings

The Security Advisor leaked-password warning and `rls_enabled_no_policy` INFO findings MUST remain out of scope for this change. They MAY be referenced as dependencies or follow-up evidence, but this spec MUST NOT claim to remediate them or use them as a substitute for ticket-channel corroboration.

#### Scenario: Advisor findings do not authorize repair

- GIVEN advisor findings remain unresolved
- WHEN ticket integrity preflight is evaluated
- THEN only the defined schema/deployment evidence and fresh Discord evidence determine repair eligibility
