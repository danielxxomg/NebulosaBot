# Data Retention Specification

## Purpose

Bound database/storage growth via pg_cron retention jobs (closed tickets, inactive infractions, crash reports), fix PostgREST expiry serialization, and clean index debt. Retention defaults are GLOBAL (config.toml only) — no per-guild override.

## Requirements

### Requirement: Ticket retention purge with sub-tickets-first ordering

A scheduled job MUST purge closed tickets older than the configured global TTL (default 30 days) plus their notes. Sub-ticket rows MUST be deleted BEFORE their parent rows. The purge MUST be idempotent; DDL MUST use `IF NOT EXISTS`.

#### Scenario: Old closed ticket and notes purged

- GIVEN a ticket closed 31 days ago with 3 notes
- WHEN the job runs
- THEN the ticket and its 3 notes are deleted

#### Scenario: Sub-tickets deleted before parents

- GIVEN an expired parent with two expired sub-tickets
- WHEN the job runs
- THEN sub-tickets are deleted before the parent (observable order)

#### Scenario: Recent closed tickets kept

- GIVEN a ticket closed 5 days ago
- WHEN the job runs
- THEN it is retained

### Requirement: Infraction retention keeps permanent bans forever

The job MUST purge infractions inactive beyond the configured TTL (default 180 days), EXCEPT permanent BANs, retained indefinitely.

#### Scenario: Stale infraction purged

- GIVEN an inactive mute older than 180 days
- WHEN the job runs
- THEN the row is deleted

#### Scenario: Permanent ban survives

- GIVEN a permanent BAN older than 180 days
- WHEN the job runs
- THEN the row is retained

### Requirement: Tempban expiry query serialization is PostgREST-safe

The tempban expiry sweep MUST filter expirable rows with a null-safe PostgREST filter on `expiresAt` (`not_.is_` semantics). It MUST NOT emit `neq("expiresAt", None)` — which serializes into an invalid timestamp comparison (PostgREST 22007). A real serialization test MUST assert the outgoing request query string (fake builders previously masked the defect).

#### Scenario: Expired tempban deactivates without serialization error

- GIVEN one tempban past `expiresAt` and one with null
- WHEN the sweep queries
- THEN it executes without error and selects exactly the expired row

#### Scenario: Real serialization test asserts the wire format

- GIVEN the sweep builds its query
- WHEN the test inspects the request query string
- THEN a null-safe `is` filter for non-null `expiresAt` appears and no neq-with-null comparison exists

### Requirement: Crash report scope and TTL

The system MUST persist `crash_report` rows ONLY for unhandled exceptions and CRITICAL-level errors; business ERROR logs MUST NOT create rows. A job MUST purge rows older than 30 days.

#### Scenario: Unhandled exception recorded

- GIVEN an unhandled exception
- WHEN processed
- THEN exactly one `crash_report` row captures the traceback context

#### Scenario: Business ERROR excluded

- GIVEN a handled rule logs at ERROR
- WHEN processed
- THEN no `crash_report` row is created

#### Scenario: Old crash reports purged

- GIVEN rows older than 30 days
- WHEN the job runs
- THEN they are deleted; newer rows retained

### Requirement: Index hygiene with idempotent DDL

Migrations MUST add `member(updated_at)` and drop duplicate `idx_ticket_note_created`. All DDL MUST be idempotent (`IF NOT EXISTS`) so live re-runs succeed, honoring delete-before-migrate ordering where superseded objects exist.

#### Scenario: Migration re-run is safe

- GIVEN the migration was already applied
- WHEN applied again
- THEN it completes without errors

#### Scenario: Duplicate index removed, new present

- GIVEN the migration ran
- WHEN indexes are inspected
- THEN `member(updated_at)` exists and `idx_ticket_note_created` does not
