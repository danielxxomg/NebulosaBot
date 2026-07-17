# Delta for greeting-config

## ADDED Requirements

### Requirement: Onboarding channel column

The system MUST persist an optional nullable `onboarding_channel_id` greeting configuration field naming a start/onboarding channel used by the welcome CTA. The column MUST be added via an additive, backwards-compatible migration that keeps all existing rows valid. Reads and writes MUST respect the cache-first pattern and Realtime invalidation.

#### Scenario: New guild defaults to null onboarding channel

- GIVEN the bot joins a guild with no existing record
- WHEN the default greeting configuration is created
- THEN `onboarding_channel_id` is null

#### Scenario: Existing rows remain valid after migration

- GIVEN an existing `greeting_config` row without an onboarding channel column
- WHEN the additive migration is applied
- THEN the row is preserved and reads back `onboarding_channel_id` as null

#### Scenario: Set onboarding channel

- GIVEN an existing guild configuration and a bot administrator
- WHEN the administrator sets `onboarding_channel_id` to a valid channel
- THEN subsequent cache-first reads return the new channel ID

#### Scenario: Clear onboarding channel

- GIVEN a guild configuration with `onboarding_channel_id` set
- WHEN an administrator sets it to null
- THEN subsequent reads return null and the welcome CTA is omitted

### Requirement: Onboarding channel cache and Realtime invalidation

The system MUST read and update `onboarding_channel_id` through the cache-first `GreetingConfig` path and MUST invalidate the greeting cache via the existing Supabase Realtime CDC flow when the column changes. Dashboard writes MUST NOT call a bot webhook.

#### Scenario: Cache invalidated on onboarding channel update

- GIVEN greeting configuration is cached
- WHEN an administrator updates `onboarding_channel_id`
- THEN the cache entry for that guild is invalidated or updated

#### Scenario: Realtime CDC invalidates onboarding channel

- GIVEN the bot Realtime subscriber is connected
- WHEN Supabase emits a `greeting_config` change for a guild
- THEN the bot invalidates that guild's greeting cache so the new onboarding channel is observed

#### Scenario: Dashboard onboarding channel write uses Realtime only

- GIVEN the dashboard writes a new `onboarding_channel_id` to Supabase
- WHEN the Supabase write succeeds
- THEN the Server Action returns success without POSTing to a bot webhook endpoint

## MODIFIED Requirements

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`, `welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`, `goodbye_card_enabled`, and an optional nullable `onboarding_channel_id` in the guild greeting record.

(Previously: greeting columns did not include an onboarding/start channel.)

#### Scenario: Default values for new guild

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN greeting channels and `onboarding_channel_id` are null, templates use defaults, and card toggles are false

#### Scenario: Onboarding channel round-trips

- GIVEN a guild configuration with `onboarding_channel_id` set to channel C
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the camelCase `onboardingChannelId` key and the value is unchanged

### Requirement: CRUD via GuildService

The system MUST provide GuildService/GreetingService methods to read and update greeting configuration including the optional `onboarding_channel_id`.

(Previously: CRUD methods handled greeting channels, toggles, and templates but not an onboarding channel.)

#### Scenario: Update welcome channel

- GIVEN an existing guild configuration
- WHEN an administrator sets `welcome_channel_id`
- THEN subsequent reads return the new channel ID

#### Scenario: Disable welcome card

- GIVEN an existing guild configuration
- WHEN `welcome_card_enabled` is set to false
- THEN welcome cards are no longer sent

#### Scenario: Update onboarding channel via service

- GIVEN an existing guild configuration
- WHEN an administrator sets `onboarding_channel_id`
- THEN subsequent cache-first reads return the configured channel ID

### Requirement: Cache-first reads

The system MUST read greeting configuration, including `onboarding_channel_id`, from cache first and fall back to the database.

(Previously: cache-first reads covered greeting channels, toggles, and templates.)

#### Scenario: Cache invalidation on update

- GIVEN greeting configuration is cached
- WHEN an administrator updates a greeting field
- THEN the cache entry is invalidated or updated

#### Scenario: Onboarding channel cache hit returns configured value

- GIVEN greeting configuration with `onboarding_channel_id` is cached
- WHEN the config is read again for the same guild
- THEN the cached `onboarding_channel_id` is returned without a database query
