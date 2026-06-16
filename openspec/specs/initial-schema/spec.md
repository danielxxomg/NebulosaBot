# Initial Schema Specification

## Purpose

Define Migration 001 and the five core tables.

## Requirements

### Requirement: Migration 001

The system MUST provide a Migration 001 that creates the Guild, User, Member, Infraction, and Ticket tables.

#### Scenario: Fresh install

- GIVEN an empty database
- WHEN Migration 001 runs
- THEN all five tables are created with the defined columns and constraints

### Requirement: Guild table

The system MUST create a Guild table with columns: `id` (PK string), `prefix` (string default `nb!`), `language` (string default `es`), `modRoleId` (nullable string), `logChannelId` (nullable string), `ticketCategoryId` (nullable string), `ticketPanelMessageId` (nullable string), `ticketPanelChannelId` (nullable string), `logEnabled` (boolean default false), `welcomeEnabled` (boolean default false), `active` (boolean default true).

#### Scenario: Guild insert

- GIVEN Migration 002 has run
- WHEN a default guild row is inserted
- THEN all defaults are applied, `id` is unique, and panel columns default to null

### Requirement: User table

The system MUST create a User table with columns: `id` (PK string), `username` (string), `avatarUrl` (nullable string), `lastSeen` (datetime).

#### Scenario: User insert

- GIVEN Migration 001 has run
- WHEN a user row is inserted
- THEN `id` is unique and `lastSeen` is recorded

### Requirement: Member table

The system MUST create a Member table with columns: `guildId` (FK string), `userId` (FK string), `xp` (bigint default 0), `level` (int default 0), `warnings` (int default 0), `coins` (bigint default 0), `lastDaily` (nullable datetime), `lastXpGain` (nullable datetime), composite PK (`guildId`, `userId`).

#### Scenario: Member insert

- GIVEN a Guild and User exist
- WHEN a Member row is inserted
- THEN the composite key is unique

### Requirement: Infraction table

The system MUST create an Infraction table with columns: `id` (uuid PK), `guildId` (FK string), `targetId` (FK User string), `moderatorId` (FK User string), `type` (string WARN/MUTE/KICK/BAN), `reason` (string), `active` (boolean default true), `expiresAt` (nullable datetime), `createdAt` (datetime).

#### Scenario: Infraction insert

- GIVEN a Guild and two Users exist
- WHEN an infraction is inserted
- THEN it references valid guild, target, and moderator

### Requirement: Ticket table

The system MUST create a Ticket table with columns: `id` (uuid PK), `ticketNumber` (int sequential per guild), `guildId` (FK string), `authorId` (FK User string), `channelId` (string), `categoryId` (nullable string), `status` (string open/claimed/closed), `claimedBy` (nullable User ID), `transcriptUrl` (nullable string), `createdAt` (datetime), `closedAt` (nullable datetime), `lastActivity` (datetime).

#### Scenario: Ticket insert

- GIVEN a Guild and User exist
- WHEN a ticket is inserted
- THEN `ticketNumber` is unique within the guild

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
