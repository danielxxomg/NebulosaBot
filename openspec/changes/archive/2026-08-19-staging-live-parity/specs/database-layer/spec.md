# Delta for Database Layer

## ADDED Requirements

### Requirement: Credential-gated live execution of migration 018

The database layer MUST execute the tracked `018_ticket_integrity_fks.sql` against real staging only with `LIVE_SUPABASE=1` and a real `DB_URL`. A backup MUST be captured and lock/statement timeouts MUST be set before schema DDL. Before any cast or constraint DDL, the migration MUST run its read-only `DO` preflight and preserve this ordered eight-step contract: (1) preflight, (2) `ticket.categoryId` `TEXT`→`UUID` using an explicit cast, (3) child indexes, (4) parent `RESTRICT` FK, (5) category `SET NULL` FK, (6) note `CASCADE` FK, (7) nullable audit `SET NULL` FK, and (8) validate constraints, run application checks, and drop only `idx_ticket_guild_number`. The path MUST use the tracked migration mechanism, not an untracked SQL editor or `execute_sql` substitute.

#### Scenario: Real preflight permits the migration

- GIVEN staging credentials are present and the live preflight finds 21 tickets, 0 invalid UUIDs, 0 category orphans, zero missing/deep parents, 0 note orphans, and approved audit retention of 1 orphan plus 1 guild mismatch
- WHEN the tracked migration runs
- THEN the eight steps execute in order and before/after catalog evidence is captured

#### Scenario: Missing credentials fail the live gate

- GIVEN `LIVE_SUPABASE` or the real database credential is absent
- WHEN S4 live acceptance is requested
- THEN the command fails with a credential-gate reason and a fake client cannot produce PASS

#### Scenario: Preflight aborts before DDL

- GIVEN any duplicate, invalid UUID, unapproved orphan, or retention count outside policy is found
- WHEN the `DO` preflight executes
- THEN it raises a failure before the `USING` cast and no schema or ticket mutation is attempted

#### Scenario: Foreign-key shapes preserve data

- GIVEN the migration reaches constraint creation
- WHEN parent, category, note, or audit rows are deleted
- THEN `RESTRICT`, `SET NULL`, `CASCADE`, and `SET NULL` apply respectively, with audit history retained

### Requirement: Evidence-based index retention

The migration MUST evaluate any proposed index removal with `EXPLAIN (ANALYZE, BUFFERS)` against a representative staging workload. A zero cumulative scan count alone MUST NOT authorize a drop. S4 MAY drop only the redundant `idx_ticket_guild_number`; `idx_ticket_channel` and all other indexes MUST remain unless a separately approved change proves their replacement.

#### Scenario: Duplicate index is the sole allowed drop

- GIVEN the workload proves the unique guild/ticket-number index covers the duplicate
- WHEN post-validation index policy runs
- THEN only `idx_ticket_guild_number` is dropped

#### Scenario: Unproven index removal is rejected

- GIVEN an index has zero `pg_stat_user_indexes` scans but no representative EXPLAIN evidence
- WHEN removal is evaluated
- THEN the drop is rejected and the index remains
