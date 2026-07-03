# Greeting Configuration Specification

## Purpose

Define guild greeting settings: welcome/goodbye channels, message templates, and card toggles.

## Requirements

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`, `welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`, and `goodbye_card_enabled` in the guild record.

#### Scenario: Default values for new guild

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN greeting channels are null, templates use defaults, and card toggles are false

### Requirement: CRUD via GuildService

The system MUST provide GuildService methods to read and update greeting configuration.

#### Scenario: Update welcome channel

- GIVEN an existing guild configuration
- WHEN an administrator sets `welcome_channel_id`
- THEN subsequent reads return the new channel ID

#### Scenario: Disable welcome card

- GIVEN an existing guild configuration
- WHEN `welcome_card_enabled` is set to false
- THEN welcome cards are no longer sent

### Requirement: Cache-first reads

The system MUST read greeting configuration from cache first and fall back to the database.

#### Scenario: Cache invalidation on update

- GIVEN greeting configuration is cached
- WHEN an administrator updates a greeting field
- THEN the cache entry is invalidated or updated

### Requirement: Dashboard webhook notification

The dashboard `updateGreetingConfig()` Server Action MUST fire an asynchronous POST to the bot's webhook endpoint after a successful Supabase write. The webhook call MUST NOT block or fail the Supabase write.

#### Scenario: Webhook fired after greeting config write

- GIVEN the dashboard writes a greeting config change to Supabase
- WHEN the Supabase write succeeds
- THEN a signed POST is sent to the webhook endpoint with `{"guild_id": G}` (guild_id only; the optional `entity` field is omitted because the bot performs a full `invalidate_guild`)

#### Scenario: Webhook failure does not fail write

- GIVEN the webhook endpoint is unreachable or returns an error
- WHEN `updateGreetingConfig()` completes the Supabase write
- THEN the Server Action returns success (fire-and-forget)
