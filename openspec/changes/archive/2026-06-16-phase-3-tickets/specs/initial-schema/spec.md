# Delta for Initial Schema

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Guild table

The system MUST create a Guild table with columns: `id` (PK string), `prefix` (string default `nb!`), `language` (string default `es`), `modRoleId` (nullable string), `logChannelId` (nullable string), `ticketCategoryId` (nullable string), `ticketPanelMessageId` (nullable string), `ticketPanelChannelId` (nullable string), `logEnabled` (boolean default false), `welcomeEnabled` (boolean default false), `active` (boolean default true).
(Previously: Guild table did not include `ticketPanelMessageId` and `ticketPanelChannelId`.)

#### Scenario: Guild insert

- GIVEN Migration 002 has run
- WHEN a default guild row is inserted
- THEN all defaults are applied, `id` is unique, and panel columns default to null
