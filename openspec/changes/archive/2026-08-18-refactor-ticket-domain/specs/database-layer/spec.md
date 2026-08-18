# Delta for Database Layer

## MODIFIED Requirements

### Requirement: Guild-scoped database boundary inventory

The database layer MUST enforce guild ownership for all 12 inventoried ticket, category, note, and audit paths: `get_ticket`, `get_ticket_by_channel`, `update_ticket`, `get_tickets_by_parent`, `get_ticket_category`, `delete_ticket_category`, `insert_ticket_note`, `get_ticket_notes`, `delete_ticket_note`, `get_recent_notes_for_dedup`, `insert_audit_row`, and `get_audit_rows`. Every read or mutation MUST establish ownership before returning or changing a row. Cross-guild input MUST return no eligible row or an explicit denial and MUST NOT mutate data. The S2 contract MUST close the `GUILD_SCOPE_GAPS` ledger without relying on a caller-only check.
(Previously: S1 only inventoried ID-only methods as `GUILD_SCOPE_GAPS` and deferred enforcement to S2.)

#### Scenario: Cross-guild access is denied

- GIVEN equivalent identifiers or channel IDs exist in guilds A and B
- WHEN a guild A request targets an identifier belonging to guild B
- THEN no guild B data is returned and no guild B row is mutated

#### Scenario: Note and audit ownership is validated

- GIVEN a note or audit request names a ticket from another guild
- WHEN an insert, read, or delete is attempted
- THEN the operation is denied before persistence and records a non-empty denial reason when auditing applies

#### Scenario: All twelve gaps are closed

- GIVEN the `GUILD_SCOPE_GAPS` ledger contains 12 methods
- WHEN the S2.2 contract audit runs
- THEN every listed method has an enforceable guild boundary and no gap is reported as merely documented

## ADDED Requirements

### Requirement: No S2 schema mutation

S2.1–S2.4 MUST NOT add, alter, or drop database schema objects, RLS policies, foreign keys, or migrations. Guild enforcement MUST be delivered through code and tests; live schema differences MUST be reported for a later migration decision.

#### Scenario: Code-only guild migration

- GIVEN S2.2 adds guild-aware mixin entry points
- WHEN the change is reviewed
- THEN no DDL or migration is created or applied

#### Scenario: Live retention evidence remains informational

- GIVEN live metadata shows six child-to-guild foreign keys with `ON DELETE CASCADE`
- WHEN S2 evaluates database behavior
- THEN the evidence is recorded without changing FK retention or claiming missing ticket-note/audit FKs were repaired
