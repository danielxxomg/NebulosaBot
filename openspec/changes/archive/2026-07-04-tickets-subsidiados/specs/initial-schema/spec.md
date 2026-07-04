# Delta for Initial Schema

## ADDED Requirements

### Requirement: Migration 003

The system MUST provide a Migration 003 that adds the `parentId` column to the `ticket` table and creates the `ticket_note` table. Migration MUST apply cleanly on existing data — all existing tickets SHALL receive `parentId=null`.

#### Scenario: Run migration 003 on existing data

- GIVEN a database with Migration 001/002 applied and 20 existing tickets (all with no parentId)
- WHEN Migration 003 runs
- THEN the `parentId` column exists on `ticket` (nullable UUID), all 20 tickets have `parentId=null`, and `ticket_note` table exists

#### Scenario: Fresh install with all migrations

- GIVEN an empty database
- WHEN Migrations 001, 002, and 003 run in order
- THEN all tables from 001, 002, and 003 exist with correct columns

### Requirement: parentId column

The `ticket` table MUST have a `parentId` column: `UUID`, nullable, self-referential. No DB-level FK constraint (app-level validation only, per Supabase Transaction Mode limitation). Existing tickets MUST NOT be affected.

#### Scenario: parentId defaults to null

- GIVEN Migration 003 applied
- WHEN a new ticket is created without specifying parentId
- THEN `parentId` is null

#### Scenario: parentId set on insert

- GIVEN Migration 003 applied and a parent ticket exists
- WHEN a sub-ticket is inserted with `parentId` = parent's UUID
- THEN the row stores the parentId correctly

### Requirement: ticket_note table

The system MUST create a `ticket_note` table with columns: `id` (UUID PK), `ticketId` (UUID, references ticket), `authorId` (TEXT), `content` (TEXT), `createdAt` (TIMESTAMPTZ default now). Index on `ticketId`.

#### Scenario: Insert note

- GIVEN Migration 003 applied and a ticket exists
- WHEN a note row is inserted with valid ticketId, authorId, content
- THEN `id` is auto-generated, `createdAt` defaults to now

#### Scenario: Query notes by ticket

- GIVEN 5 notes for ticket A and 3 notes for ticket B
- WHEN querying notes filtered by `ticketId=A`
- THEN exactly 5 rows are returned

### Requirement: ticket_note index

The system SHOULD create an index on `ticket_note` (`ticketId`).

#### Scenario: Efficient note lookup

- GIVEN many notes across multiple tickets
- WHEN listing notes for a single ticket
- THEN the query uses the `ticketId` index
