# Ticket Category Model Specification

## Purpose

Define the TicketCategory dataclass and guild-scoped category CRUD.

## Requirements

### Requirement: Dataclass fields

The system MUST define a TicketCategory dataclass with fields: `id` (UUID), `guildId` (string), `name` (string), `description` (nullable string), `position` (integer), `createdAt` (datetime).

#### Scenario: Build from row

- GIVEN a Supabase row with camelCase keys
- WHEN `from_db_row` is called
- THEN a TicketCategory instance is returned with correct field values

### Requirement: Guild-scoped CRUD

The system MUST support create, read, update, and delete of ticket categories scoped to a guild.

#### Scenario: Create category

- GIVEN a guild ID and category name
- WHEN a category is created
- THEN it is stored with a unique `id` and a guild-scoped `position` value

#### Scenario: List by guild

- GIVEN multiple categories across different guilds
- WHEN categories are queried for guild A
- THEN only guild A's categories are returned ordered by `position`

#### Scenario: Duplicate name within guild

- GIVEN guild A already has a category named "Billing"
- WHEN another "Billing" category is created in guild A
- THEN the operation is rejected

### Requirement: Positioning

The system MUST maintain a stable positioning for categories within each guild.

#### Scenario: Position increment

- GIVEN guild A has categories with positions 0, 1, and 2
- WHEN a new category is created in guild A
- THEN it receives position 3
