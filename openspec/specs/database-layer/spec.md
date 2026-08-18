# Database Layer Specification

## Purpose

Define the async database client and health-check behavior.

## Requirements

### Requirement: Async client

The system MUST provide an async Supabase client for database operations. `Database.__init__` MUST use `acreate_client` (async) instead of `create_client` (sync). ALL `.execute()` calls MUST be preceded by `await`. Database methods MUST return awaited results, not coroutines.

(Previously: used sync create_client; .execute() was not awaited)

#### Scenario: Query execution

- GIVEN the client is initialized
- WHEN a service executes a SELECT query
- THEN the client returns the matching rows

#### Scenario: Concurrent queries

- GIVEN multiple services query the database at the same time
- WHEN requests overlap
- THEN each request completes without blocking the others

#### Scenario: Async client creation

- GIVEN valid Supabase credentials
- WHEN `Database.connect()` is called
- THEN `acreate_client` is used (not sync `create_client`)

#### Scenario: All execute calls awaited

- GIVEN the Database has ~50 methods with `.execute()` calls
- WHEN a grep audit runs for `.execute()`
- THEN every occurrence is preceded by `await`

#### Scenario: Missed await detection

- GIVEN a method calls `.execute()` without `await`
- WHEN the method is called at runtime
- THEN a coroutine object is returned (not a response), causing `_unwrap()` to return `[]` — detectable by mypy or tests

### Requirement: Health check

The system MUST verify database connectivity on startup and report failure clearly.

#### Scenario: Healthy database

- GIVEN valid Supabase credentials
- WHEN the health check runs
- THEN it reports the database as reachable

#### Scenario: Unhealthy database

- GIVEN invalid or unreachable credentials
- WHEN the health check runs
- THEN it reports failure and the bot refuses to execute database-dependent commands

### Requirement: Database domain mixin split

The `Database` class MUST be split into domain mixins under `bot/core/db/`: `GuildDBMixin`, `MemberDBMixin`, `InfractionDBMixin`, `TicketDBMixin`, `TicketNoteDBMixin`, `TicketCategoryDBMixin`, `TicketAuditDBMixin`, `EconomyDBMixin`, `GreetingDBMixin`.

#### Scenario: All methods accessible

- GIVEN the Database class composes all mixins
- WHEN `db.get_guild()` or `db.insert_ticket()` is called
- THEN the method resolves from the correct mixin

#### Scenario: Mixin files exist

- GIVEN the split is complete
- WHEN inspecting `bot/core/db/`
- THEN each domain has its own file (e.g., `guild_db.py`, `ticket_db.py`)

### Requirement: Facade backward-compatible re-export

`bot/core/database.py` MUST re-export `Database` and all public names so existing imports `from bot.core.database import Database` continue to work unchanged.

#### Scenario: Existing import preserved

- GIVEN code imports `from bot.core.database import Database`
- WHEN the DB split is complete
- THEN the import resolves without error

#### Scenario: database.py is slim facade

- GIVEN the split is complete
- WHEN inspecting `bot/core/database.py`
- THEN it contains only imports and the composed `Database` class (~30 lines)

<!-- BEGIN DELTA: product-artifact-audit (database-layer) -->
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

<!-- END DELTA: product-artifact-audit (database-layer) -->

<!-- BEGIN DELTA: ticket-integrity-recovery (database-layer) -->
## ADDED Requirements

### Requirement: Migration 015 on-disk parity tracking

Migration `015_*` (production-applied) MUST be present and tracked on disk in `migrations/`. The on-disk file MUST be byte-named and schema-matched against the production-applied version before any downstream repair code relies on it. Restoration MUST NOT mark a new migration as applied; it re-establishes parity for a migration production already reports as applied.

The system SHALL verify parity before reliance: filename, declared schema objects, and applied status MUST match production evidence. Until parity is verified, the repair activation gate (G.2) MUST remain unresolved.

#### Scenario: Production-applied migration restored on disk

- GIVEN production reports migration `015_*` as already applied and no `migrations/015_*` file exists on disk
- WHEN migration 015 is restored to `migrations/`
- THEN the file is tracked in git and its content matches the production-applied schema

#### Scenario: Parity checked before reliance

- GIVEN migration 015 was restored on disk
- WHEN the preflight parity check runs
- THEN filename, schema objects, and applied-status match production evidence and the check returns `compatible`

#### Scenario: Parity mismatch blocks reliance

- GIVEN the restored `migrations/015_*` content differs from the production-applied schema
- WHEN the preflight parity check runs
- THEN the check returns `incompatible`, the G.2 gate remains unresolved, and no repair activation is permitted

### Requirement: Deployment/migration preflight evidence (G.2 gate)

Preflight MUST collect deployment and migration compatibility evidence before any automatic repair is activated. Evidence MUST include: migration 015 on-disk/production parity (from the prior requirement), supported Supabase/Postgres deployment mode, and absence of incompatible schema-drift signals. When evidence is missing or incompatible, preflight MUST return `gate_unresolved` and automatic repair MUST stay disabled. This gate is read-only with respect to ticket data — it MUST NOT mutate tickets.

#### Scenario: Evidence present and compatible

- GIVEN migration 015 parity is verified and the deployment mode is supported
- WHEN the G.2 preflight runs
- THEN the gate returns `resolved` and automatic repair activation MAY proceed

#### Scenario: Missing evidence blocks activation

- GIVEN migration 015 parity is unverified
- WHEN the G.2 preflight runs
- THEN the gate returns `gate_unresolved` and automatic repair is disabled

#### Scenario: Incompatible deployment blocks activation

- GIVEN the deployment mode is unsupported or schema-drift is detected
- WHEN the G.2 preflight runs
- THEN the gate returns `gate_unresolved` and automatic repair is disabled

#### Scenario: Preflight does not mutate tickets

- GIVEN any preflight outcome
- WHEN the G.2 preflight runs
- THEN no ticket row is inserted, updated, or deleted by the preflight itself

<!-- END DELTA: ticket-integrity-recovery (database-layer) -->

<!-- BEGIN DELTA: cleanup-stability (database-layer) -->
<!-- Delta: cleanup-stability — Hygiene & Stability (S1 L3) — S2-deferred: live FK/RLS inventory, unsigned JWT verification, guild enforcement. S1 installs read-only inventory + fail-closed sentinel and documents gaps as warnings. -->

### Requirement: Explicit non-goals for advisor findings

The database layer MUST encode the live `rls_enabled_no_policy` state as an explicit service-role-only contract for S1. All nine public tables MUST remain RLS-enabled; publishable or authenticated non-service credentials MUST be denied access, while the server-side `service_role` client MAY access required tables. Startup MUST validate that the configured credential is present and service-role-compatible, failing closed otherwise. Advisor findings MAY remain visible as diagnostics, but MUST NOT authorize broader access or replace schema and ownership evidence. This contract changes no DDL.

(Previously: RLS no-policy and leaked-password advisor findings were explicitly out of scope.)

#### Scenario: Service-role startup validation succeeds

- GIVEN a present credential is verified as `service_role`
- WHEN database startup validation runs
- THEN the database layer becomes available for server-side operations

#### Scenario: Non-service startup fails closed

- GIVEN the credential is missing, unverifiable, or non-service-role
- WHEN database startup validation runs
- THEN startup reports failure and database-dependent commands remain disabled

#### Scenario: Negative non-service access test

- GIVEN an anon, publishable, or authenticated credential
- WHEN it attempts to read any public application table
- THEN access is denied and no application rows are exposed

#### Scenario: Advisor findings do not authorize repair

- GIVEN advisor findings remain unresolved
- WHEN ticket-integrity preflight is evaluated
- THEN only verified schema/deployment evidence and fresh Discord evidence determine repair eligibility

### Requirement: Read-only schema and FK retention inventory

S1 MUST inventory live and on-disk schema state before any schema change. The retained contract is `ticket_note` `ON DELETE CASCADE` and `ticket_audit` `ON DELETE SET NULL`; the inventory MUST record whether each live and disk definition matches. Migration `015_*` filename, objects, and applied status MUST be compared before any future DDL is considered. This change MUST apply no DDL.

#### Scenario: Inventory records matching state

- GIVEN live metadata, migration history, disk files, and migration 015 are available
- WHEN the read-only inventory runs
- THEN FK actions and 015 parity are reported without changing the database

#### Scenario: Drift blocks schema work

- GIVEN live and disk FK actions or migration 015 parity differ
- WHEN the inventory evaluates the state
- THEN it reports unresolved drift and no DDL is created or applied

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

<!-- END DELTA: cleanup-stability (database-layer) -->

<!-- BEGIN DELTA: refactor-ticket-domain (database-layer) -->
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

<!-- END DELTA: refactor-ticket-domain (database-layer) -->
