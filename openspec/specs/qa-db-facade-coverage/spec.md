# QA DB Facade Coverage Specification

## Purpose

Facade-level tests for untested DB mixin methods across ticket_category_db, ticket_db, greeting_db, and infraction_db using `FakeSupabaseClient`.

## Requirements

### Requirement: TicketCategoryDB facade coverage

Tests MUST cover `count_open_tickets_by_category` and `update_ticket_category_field_definitions`.

#### Scenario: count_open_tickets_by_category returns exact count

- GIVEN a FakeSupabaseClient with 3 open tickets for category X
- WHEN `count_open_tickets_by_category(guild_id, category_id)` is called
- THEN the return value is 3

#### Scenario: update_ticket_category_field_definitions guild-scoped

- GIVEN a guild with a ticket category
- WHEN `update_ticket_category_field_definitions(guild_id, category_id, fields)` is called
- THEN the update query includes both `guild_id` and `category_id` filters

### Requirement: TicketDB facade coverage

Tests MUST cover `get_stale_tickets`, `get_open_ticket_channel_ids`, and `update_ticket_last_activity`.

#### Scenario: get_stale_tickets filters by time threshold

- GIVEN tickets with varying `last_activity` timestamps
- WHEN `get_stale_tickets(guild_id, threshold)` is called
- THEN only tickets older than the threshold are returned

#### Scenario: get_open_ticket_channel_ids extracts IDs

- GIVEN 4 open tickets with distinct channel IDs
- WHEN `get_open_ticket_channel_ids(guild_id)` is called
- THEN the return value is a list of 4 channel IDs

#### Scenario: update_ticket_last_activity scoped to channel

- GIVEN an open ticket
- WHEN `update_ticket_last_activity(guild_id, channel_id, timestamp)` is called
- THEN the update targets only the specified channel

### Requirement: GreetingDB facade coverage

Tests MUST cover `upsert_greeting_config`.

#### Scenario: upsert_greeting_config creates or updates

- GIVEN no existing greeting config for the guild
- WHEN `upsert_greeting_config(guild_id, config)` is called
- THEN the config is persisted and `_on_write` callback fires

### Requirement: InfractionDB facade coverage

Tests MUST cover `deactivate_infraction`.

#### Scenario: deactivate_infraction soft-deletes

- GIVEN an active infraction with a known ID
- WHEN `deactivate_infraction(guild_id, infraction_id)` is called
- THEN the infraction's `active` field is set to false
