# Initial Schema Specification

## Purpose

Define Migration 001 and the core tables. The `user` table is vestigial and dropped by Migration 006.

## Requirements

### Requirement: Migration 001

The system MUST provide a Migration 001 that creates the Guild, Member, Infraction, and Ticket tables. After all migrations through 006, the `user` table MUST NOT exist. Migration 001 MAY create it, but Migration 006 MUST drop it.

#### Scenario: Fresh install

- GIVEN an empty database
- WHEN all migrations 001-006 run in order
- THEN all four core tables are created with the defined columns and constraints
- AND the `user` table does not exist in the final state
- AND no FK constraints reference the `user` table

(Previously: Migration 001 created five tables including User)

### Requirement: Guild table

The system MUST create a Guild table with columns: `id` (PK string), `prefix` (string default `nb!`), `language` (string default `es`), `modRoleId` (nullable string), `logChannelId` (nullable string), `ticketCategoryId` (nullable string), `ticketPanelMessageId` (nullable string), `ticketPanelChannelId` (nullable string), `logEnabled` (boolean default false), `welcomeEnabled` (boolean default false), `active` (boolean default true).

#### Scenario: Guild insert

- GIVEN Migration 002 has run
- WHEN a default guild row is inserted
- THEN all defaults are applied, `id` is unique, and panel columns default to null

### Requirement: Member table

The system MUST create a Member table with columns: `guildId` (string), `userId` (string), `xp` (bigint default 0), `level` (int default 0), `warnings` (int default 0), `coins` (bigint default 0), `lastDaily` (nullable datetime), `lastXpGain` (nullable datetime), composite PK (`guildId`, `userId`). No FK constraint on `userId`.

#### Scenario: Member insert

- GIVEN a Guild exists
- WHEN a Member row is inserted with a valid `guildId` and `userId`
- THEN the composite key is unique
- AND no FK violation occurs regardless of whether a `user` row exists

(Previously: Member.userId had FK constraint to User table)

### Requirement: Infraction table

The system MUST create an Infraction table with columns: `id` (uuid PK), `guildId` (string), `targetId` (string), `moderatorId` (string), `type` (string WARN/MUTE/KICK/BAN), `reason` (string), `active` (boolean default true), `expiresAt` (nullable datetime), `createdAt` (datetime). No FK constraints on `targetId` or `moderatorId`.

#### Scenario: Infraction insert

- GIVEN a Guild exists
- WHEN an infraction is inserted with valid guildId, targetId, and moderatorId strings
- THEN it stores successfully without requiring User rows

(Previously: targetId and moderatorId had FK constraints to User table)

### Requirement: Ticket table

The system MUST create a Ticket table with columns: `id` (uuid PK), `ticketNumber` (int sequential per guild), `guildId` (string), `authorId` (string), `channelId` (string), `categoryId` (nullable string), `status` (string open/claimed/closed), `claimedBy` (nullable string), `transcriptUrl` (nullable string), `createdAt` (datetime), `closedAt` (nullable datetime), `lastActivity` (datetime). No FK constraint on `authorId`.

#### Scenario: Ticket insert

- GIVEN a Guild exists
- WHEN a ticket is inserted
- THEN `ticketNumber` is unique within the guild
- AND `authorId` stores as a plain string without FK enforcement

(Previously: authorId had FK constraint to User table)

### Requirement: Migration 002

The system MUST provide a Migration 002 that adds the `ticket_category` table and panel columns to the Guild table.

#### Scenario: Run migration 002

- GIVEN Migration 001 has been applied
- WHEN Migration 002 runs
- THEN the `ticket_category` table and guild panel columns exist

### Requirement: Ticket category table

The system MUST create a `ticket_category` table with columns: `id` (uuid PK), `guildId` (FK string), `name` (string), `description` (nullable string), `position` (integer), `createdAt` (datetime).

#### Scenario: Ticket category insert

- GIVEN Migration 002 has run
- WHEN a ticket category row is inserted
- THEN `id` is unique and `guildId` references a valid guild

### Requirement: Ticket category indexes

The system SHOULD create an index on `ticket_category` (`guildId`, `position`).

#### Scenario: Query categories by guild

- GIVEN many ticket categories across guilds
- WHEN listing categories for one guild
- THEN the query uses the index efficiently

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

### Requirement: ticket_note RLS migration

A migration file `008_ticket_note_rls.sql` MUST exist that enables Row Level Security on the `ticket_note` table. The migration MUST be idempotent — re-running it SHALL NOT produce an error.

#### Scenario: Migration applied

- GIVEN the database has migrations 001–007 applied
- WHEN migration 008 runs
- THEN RLS is enabled on `ticket_note`

#### Scenario: Idempotent re-run

- GIVEN migration 008 was already applied
- WHEN migration 008 runs again
- THEN no error occurs (ALTER TABLE ENABLE RLS is a no-op when already enabled)

### Requirement: Member increment RPC functions

Migration `009_member_increment_rpc.sql` MUST create Postgres functions for atomic member field increments: `increment_member_xp(guild_id, user_id, amount)`, `increment_member_coins(guild_id, user_id, amount)`, `increment_member_warnings(guild_id, user_id, amount)`, `set_member_daily(guild_id, user_id, ts)`. Each function MUST be atomic (single SQL statement, no separate GET + UPDATE).

#### Scenario: increment_member_xp atomic update

- GIVEN a member with xp=100
- WHEN `increment_member_xp(guild_id, user_id, 25)` is called
- THEN xp becomes 125 in a single DB round trip

#### Scenario: set_member_daily atomic update

- GIVEN a member with lastDaily=null
- WHEN `set_member_daily(guild_id, user_id, '2026-07-08T00:00:00Z')` is called
- THEN lastDaily is set in a single DB round trip

#### Scenario: Upsert on first increment

- GIVEN no member_economy row exists for (guild_id, user_id)
- WHEN `increment_member_xp(guild_id, user_id, 10)` is called
- THEN a row is created with xp=10 (upsert semantics)
