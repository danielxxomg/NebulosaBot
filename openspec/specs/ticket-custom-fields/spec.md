# Ticket Custom Fields Specification

## Purpose

Define per-category configurable intake fields stored as JSONB, enabling admins to collect structured data beyond title and description.

## Requirements

### Requirement: Field definition schema

The system MUST store `field_definitions` as a JSONB array on `ticket_category`. Each entry SHALL contain `key` (string, unique within category), `label` (string), `style` ("short" or "paragraph"), `required` (boolean), and optional `max_length` (integer, default 100 for short, 2000 for paragraph) and `placeholder` (string). The system MUST enforce a maximum of 3 field definitions per category.

#### Scenario: Valid field definitions

- GIVEN a category with `field_definitions` containing two entries: `[{key: "player_nick", label: "Player Nickname", style: "short", required: true}, {key: "evidence_url", label: "Evidence URL", style: "short", required: false}]`
- WHEN the category is saved
- THEN the field definitions are persisted as JSONB

#### Scenario: Max 3 fields enforced

- GIVEN a category with 3 existing field definitions
- WHEN a 4th field definition is added
- THEN the operation is rejected with a validation error

#### Scenario: Missing required keys rejected

- GIVEN a field definition with `key` but no `label`
- WHEN the category is saved
- THEN the operation is rejected with a validation error

### Requirement: Custom fields storage on ticket

The system MUST store `custom_fields` as a JSONB object on `ticket`. Keys SHALL match the `key` values from the category's `field_definitions`. Values SHALL be strings or null.

#### Scenario: Custom fields persisted

- GIVEN a ticket created with `custom_fields = {player_nick: "DarkSlayer42", evidence_url: "https://imgur.com/..."}`
- WHEN the ticket row is inserted
- THEN `custom_fields` is stored as JSONB

#### Scenario: Empty custom fields

- GIVEN a ticket created for a category with no field definitions
- WHEN the ticket row is inserted
- THEN `custom_fields` defaults to `{}`

### Requirement: Migration

A migration MUST add `field_definitions JSONB DEFAULT '[]'` to `ticket_category` and `custom_fields JSONB DEFAULT '{}'` to `ticket`.

#### Scenario: Migration applied

- GIVEN the migration is run against an existing database
- WHEN existing rows are queried
- THEN `field_definitions` is `[]` for all categories and `custom_fields` is `{}` for all tickets

### Requirement: Report category seed

A data migration or seed MUST set `field_definitions` on the "Report" category to `[{key: "player_nick", label: "Player Nickname", style: "short", required: true, placeholder: "The player's in-game name"}, {key: "evidence_url", label: "Evidence URL", style: "short", required: false}]` in all guilds that have a Report category.

#### Scenario: Report category seeded

- GIVEN a guild with a "Report" category and no field definitions
- WHEN the seed migration runs
- THEN the Report category has `field_definitions` with player_nick (required) and evidence_url (optional)

#### Scenario: Non-report categories unchanged

- GIVEN a guild with a "Support" category
- WHEN the seed migration runs
- THEN the Support category retains empty `field_definitions`
