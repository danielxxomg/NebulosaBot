# Delta for database-layer

## MODIFIED Requirements

### Requirement: Credential-gated live execution of migration 018

The database layer MUST execute the tracked `018_ticket_integrity_fks.sql` against real staging only with `LIVE_SUPABASE=1` and a real `DB_URL`; absence of either MUST fail the gate with a credential-gate reason and a fake client MUST NOT produce PASS. Application MUST be tracked — via `supabase link` + tracked migration mechanism — never an untracked `psql -f` or SQL-editor `execute_sql` bypass (which would leave the ledger at 19 rows with 018 untracked). A backup table `ticket_backup_categoryid_text_20260818` MUST be captured and `lock_timeout='5s'` + `ON_ERROR_STOP=1` MUST be set before schema DDL. Before any cast or constraint DDL, the migration MUST run its read-only `DO $preflight$` and preserve this ordered eight-step contract: (1) preflight, (2) `ticket.categoryId` `TEXT`→`UUID` using an explicit cast, (3) child indexes, (4) parent `RESTRICT` FK, (5) category `SET NULL` FK, (6) note `CASCADE` FK, (7) nullable audit `SET NULL` FK, (8) validate constraints and drop only `idx_ticket_guild_number`. A documented `DOWN` section MUST restore `TEXT` `categoryId`, drop the four FKs, and recreate `idx_ticket_guild_number`.
(Previously: tracked mechanism and backup/lock/ON_ERROR_STOP/DOWN unspecified; raw psql would desync the ledger.)

#### Scenario: Real preflight permits the migration

- GIVEN staging credentials are present and the live preflight finds 21 tickets, 0 invalid UUIDs, 0 category orphans, zero missing/deep parents, 0 note orphans, approved audit retention (1 orphan + 1 guild mismatch)
- WHEN the tracked migration runs
- THEN the eight steps execute in order and before/after catalog evidence is captured

#### Scenario: Missing credentials fail the live gate

- GIVEN `LIVE_SUPABASE=1` or the real `DB_URL` is absent
- WHEN S5 live acceptance is requested
- THEN the command fails with a credential-gate reason and a fake client cannot produce PASS

#### Scenario: Untracked psql bypass is rejected

- GIVEN 018 is applied via raw `psql -f` without `supabase link`/tracked mechanism or `repair --status applied`
- WHEN the ledger is reconciled
- THEN 018 is untracked and live acceptance is blocked

#### Scenario: Preflight aborts before DDL

- GIVEN any duplicate, invalid UUID, unapproved orphan, or retention count outside policy is found
- WHEN the `DO $preflight$` executes
- THEN it raises a failure before the `USING` cast and no schema or ticket mutation is attempted

#### Scenario: Foreign-key shapes preserve data

- GIVEN the migration reaches constraint creation
- WHEN parent, category, note, or audit rows are deleted
- THEN `RESTRICT`, `SET NULL`, `CASCADE`, and `SET NULL` apply respectively, with audit history retained

#### Scenario: Lock timeout and backup protect the window

- GIVEN a long transaction holds a conflicting lock during `VALIDATE CONSTRAINT`
- WHEN `lock_timeout='5s'` elapses
- THEN the migration aborts, `ON_ERROR_STOP=1` halts, and `ticket_backup_categoryid_text_20260818` is retained for `DOWN` restore

### Requirement: Evidence-based index retention

The migration MUST evaluate any proposed index removal with `EXPLAIN (ANALYZE, BUFFERS)` against a representative staging workload. A zero cumulative scan count alone MUST NOT authorize a drop. The receipt for `idx_ticket_guild_number` MUST prove the unique `idx_ticket_guild_ticket_number` covers the lookup (Index Only Scan, 0 heap fetches) before the drop. `idx_ticket_channel` and all other indexes MUST remain unless a separately approved change proves their replacement.
(Previously: S4 allowed EXPLAIN; S5 requires the receipt be captured live before DROP.)

#### Scenario: Duplicate index is the sole allowed drop

- GIVEN `EXPLAIN (ANALYZE, BUFFERS)` on `WHERE "guildId"=? AND "ticketNumber"=?` proves `idx_ticket_guild_ticket_number` Index Only Scan with 0 heap fetches
- WHEN post-validation index policy runs
- THEN only `idx_ticket_guild_number` is dropped

#### Scenario: Unproven index removal is rejected

- GIVEN an index has zero `pg_stat_user_indexes` scans but no representative EXPLAIN evidence
- WHEN removal is evaluated
- THEN the drop is rejected and the index remains
