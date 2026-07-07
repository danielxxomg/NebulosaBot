# Delta for Initial Schema

## REMOVED Requirements

### Requirement: User table

(Reason: The `user` table is vestigial — the bot never writes to it and dashboard specs do not reference it. All 4 FK constraints referencing `user(id)` are dropped in Migration 006.)
(Migration: Remove any code or tests that insert/query the `user` table. The `member.userId`, `infraction.targetId`, `infraction.moderatorId`, and `ticket.authorId` columns are retained as plain strings without FK enforcement.)

## MODIFIED Requirements

### Requirement: Migration 001

The system MUST provide a Migration 001 that creates the Guild, Member, Infraction, and Ticket tables. After all migrations through 006, the `user` table MUST NOT exist. Migration 001 MAY create it, but Migration 006 MUST drop it.

#### Scenario: Fresh install

- GIVEN an empty database
- WHEN all migrations 001-006 run in order
- THEN all four core tables are created with the defined columns and constraints
- AND the `user` table does not exist in the final state
- AND no FK constraints reference the `user` table

(Previously: Migration 001 created five tables including User)

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
