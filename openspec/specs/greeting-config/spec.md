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

### Requirement: Dashboard greeting config sync via Realtime CDC

Dashboard greeting config writes MUST NOT call any inbound bot webhook. Cache invalidation MUST rely on outbound Supabase Realtime CDC (`cache-sync-realtime`).

#### Scenario: Greeting config write does not call webhook

- GIVEN the dashboard writes a greeting config change to Supabase
- WHEN the Supabase write succeeds
- THEN the Server Action returns success without POSTing to a bot webhook endpoint

#### Scenario: Bot invalidates via Realtime

- GIVEN the bot Realtime subscriber is connected
- WHEN Supabase emits a greeting_config change for guild G
- THEN the bot invalidates the greeting cache for G

### Requirement: Welcome dispatch respects card toggle

`dispatch_welcome()` MUST check `config.welcome_card_enabled` before generating a greeting card. When `welcome_card_enabled` is `True`, the existing card-generation path is used. When `False`, only a text-only message is sent if `welcome_message` is non-empty; if `welcome_message` is also empty, nothing is sent.

#### Scenario: Welcome card sent when toggle enabled

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, and `welcome_card_enabled` is `True`
- WHEN a member joins the guild
- THEN `ImageService.generate_greeting_card()` is called via `asyncio.to_thread` and the resulting `.png` file is sent to the welcome channel with optional text overlay

#### Scenario: Welcome text-only when toggle disabled and message set

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, `welcome_card_enabled` is `False`, and `welcome_message` is non-empty
- WHEN a member joins the guild
- THEN a text-only message (formatted from `welcome_message` template) is sent to the welcome channel with no file attachment

#### Scenario: Welcome nothing when toggle disabled and no message

- GIVEN `welcome_enabled` is `True`, `welcome_channel_id` is set, `welcome_card_enabled` is `False`, and `welcome_message` is empty or null
- WHEN a member joins the guild
- THEN no message is sent to the welcome channel

### Requirement: Goodbye dispatch respects card toggle

`dispatch_goodbye()` MUST check `config.goodbye_card_enabled` before generating a greeting card. When `goodbye_card_enabled` is `True`, the existing card-generation path is used. When `False`, only a text-only message is sent if `goodbye_message` is non-empty; if `goodbye_message` is also empty, nothing is sent.

#### Scenario: Goodbye card sent when toggle enabled

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, and `goodbye_card_enabled` is `True`
- WHEN a member leaves the guild
- THEN `ImageService.generate_greeting_card()` is called via `asyncio.to_thread` and the resulting `.png` file is sent to the goodbye channel with optional text overlay

#### Scenario: Goodbye text-only when toggle disabled and message set

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, `goodbye_card_enabled` is `False`, and `goodbye_message` is non-empty
- WHEN a member leaves the guild
- THEN a text-only message (formatted from `goodbye_message` template) is sent to the goodbye channel with no file attachment

#### Scenario: Goodbye nothing when toggle disabled and no message

- GIVEN `goodbye_enabled` is `True`, `goodbye_channel_id` is set, `goodbye_card_enabled` is `False`, and `goodbye_message` is empty or null
- WHEN a member leaves the guild
- THEN no message is sent to the goodbye channel

### Requirement: Top-level greeting guard still applies

The `welcome_enabled` / `goodbye_enabled` top-level guards MUST be checked before the card toggle. When `welcome_enabled` is `False`, `dispatch_welcome()` MUST return immediately regardless of `welcome_card_enabled`. Same for goodbye.

#### Scenario: Welcome disabled at top level ignores card toggle

- GIVEN `welcome_enabled` is `False` and `welcome_card_enabled` is `True`
- WHEN a member joins the guild
- THEN no message or card is sent (dispatch returns early)
