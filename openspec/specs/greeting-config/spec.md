# Greeting Configuration Specification

## Purpose

Define guild greeting settings: welcome/goodbye channels, message templates, and card toggles.

## Requirements

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

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`, `welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`, `goodbye_card_enabled`, and an optional nullable `onboarding_channel_id` in the guild greeting record.

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

#### Scenario: Cache invalidation on update

- GIVEN greeting configuration is cached
- WHEN an administrator updates a greeting field
- THEN the cache entry is invalidated or updated

#### Scenario: Onboarding channel cache hit returns configured value

- GIVEN greeting configuration with `onboarding_channel_id` is cached
- WHEN the config is read again for the same guild
- THEN the cached `onboarding_channel_id` is returned without a database query

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

### Requirement: Global welcome guard is authoritative

`welcome_enabled` MUST be evaluated before card-toggle and CTA logic. When `False`, `dispatch_welcome()` MUST send no message, card, or CTA regardless of `welcome_card_enabled`, `welcome_message`, or `onboarding_channel_id`.

#### Scenario: Globally disabled ignores card toggle and message

- GIVEN `welcome_enabled` False, `welcome_card_enabled` True, welcome channel set, `welcome_message` non-empty
- WHEN a member joins
- THEN no message or card is sent

#### Scenario: Globally disabled ignores resolvable CTA

- GIVEN `welcome_enabled` False and `onboarding_channel_id` resolves
- WHEN a member joins
- THEN no CTA or message is sent

### Requirement: Whitespace normalization for welcome text emptiness

For the card-disabled text path, `welcome_message` is empty when it is `None`, an empty string, or whitespace-only. Emptiness MUST be decided on the **formatted** content: format the template via the standard localization and variable-replacement pipeline, then strip leading/trailing whitespace (spaces, tabs, newlines, carriage returns); the message is empty iff the stripped result is `None` or a zero-length string. A bare truthiness check on the raw template MUST NOT be the emptiness gate, because a template that becomes whitespace-only after variable substitution MUST be treated as empty.

#### Scenario: None message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `None`
- WHEN a member joins and the card-disabled text path runs
- THEN no message is sent, even when `onboarding_channel_id` resolves

#### Scenario: Empty-string message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `""`
- WHEN a member joins and the card-disabled text path runs
- THEN no message is sent, even when `onboarding_channel_id` resolves

#### Scenario: Whitespace-only message is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `"   \n\t "`
- WHEN a member joins and the card-disabled text path runs
- THEN the stripped formatted content is zero-length and no message is sent

#### Scenario: Template becoming whitespace-only after formatting is empty

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` `" {member_nick} "`, member nick resolves to empty
- WHEN a member joins and the card-disabled text path runs
- THEN the formatted `"  "` strips to zero-length and no message is sent

### Requirement: Disabled card text-only path isolates CTA resolution

When `welcome_card_enabled` is `False` and the normalized message is non-empty, the system MUST send exactly the formatted text-only message and MUST NOT append, prepend, or substitute any CTA. It MUST NOT call the CTA resolver on this path and MUST NOT send a CTA-only message. Invalid, missing, or inaccessible `onboarding_channel_id` MUST NOT block, alter, or suppress the non-empty text-only message.

#### Scenario: Non-empty message sends text only, no CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN exactly one text-only message is sent with no attachment and no CTA suffix

#### Scenario: Invalid CTA channel does not block non-empty text

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` invalid/inaccessible
- WHEN a member joins
- THEN exactly one text-only message is sent and no CTA is sent

#### Scenario: Missing CTA channel does not block non-empty text

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` non-empty, `onboarding_channel_id` `None`
- WHEN a member joins
- THEN exactly one text-only message is sent

### Requirement: Disabled card silence when message is empty

When `welcome_card_enabled` is `False` and the normalized message is empty, the system MUST send nothing regardless of `onboarding_channel_id` validity, accessibility, or resolution. An empty card-disabled message MUST NOT produce a CTA-only message.

#### Scenario: Empty message sends nothing despite resolvable CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` empty/whitespace-only, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN no message, card, or CTA is sent

#### Scenario: Empty message sends nothing despite invalid CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` empty, `onboarding_channel_id` invalid/inaccessible
- WHEN a member joins
- THEN nothing is sent

### Requirement: Localization and formatting preserved for text-only welcomes

The card-disabled text path MUST preserve the localization, variable replacement, and template formatting used by the card-enabled path for non-empty messages. CTA suppression and emptiness normalization MUST NOT alter token substitution, locale selection, or formatting of the sent payload.

#### Scenario: Localization applied to non-empty text-only message

- GIVEN `welcome_enabled` True, `welcome_card_enabled` False, `welcome_message` a localized template with member variables
- WHEN a member joins
- THEN the sent message uses the resolved locale and replaces member variables as the card-enabled path would

### Requirement: Card-enabled CTA behavior preserved

The card-enabled path (`welcome_card_enabled` True) MUST remain unchanged. The existing CTA-only exception — card-enabled welcome with an empty template and a resolvable onboarding channel producing a CTA-only message — MUST continue to hold. CTA resolution, composition, and the resolver MUST NOT be modified for the card-enabled path.

#### Scenario: Card enabled with empty message and resolvable CTA is CTA-only

- GIVEN `welcome_enabled` True, `welcome_card_enabled` True, `welcome_message` empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN a CTA-only message is sent

#### Scenario: Card enabled with message appends localized CTA

- GIVEN `welcome_enabled` True, `welcome_card_enabled` True, `welcome_message` non-empty, `onboarding_channel_id` resolvable
- WHEN a member joins
- THEN a greeting card with the formatted message and a localized CTA suffix is sent

### Requirement: Card-disabled path requires no migration or new configuration

The card-disabled text path MUST be automatic and silent for existing guilds. It MUST NOT introduce its own migrations, new configuration fields, or user-facing notices. CTA suppression on the card-disabled text path MUST require no opt-in or admin action. (The overall change introduces an additive `onboarding_channel_id` migration and configuration field; this requirement scopes the silent-card-disabled behavior to the service path only.)

#### Scenario: Existing persisted rows remain runtime-compatible

- GIVEN a pre-change `greeting_config` row that omits fields introduced by this change and an existing guild configuration
- WHEN `GreetingService` loads the row and dispatches the welcome
- THEN the row remains readable with existing defaults, no greeting-config write occurs, no migration/config field is required by the service, and no user-facing notice is emitted

#### Scenario: CTA suppression is silent with no admin notice

- GIVEN an existing guild with `welcome_card_enabled` False, empty `welcome_message`, resolvable `onboarding_channel_id`
- WHEN the change is deployed and a member joins
- THEN the bot silently sends nothing and emits no user-facing notice

### Requirement: Bounded static typing cleanup with no runtime impact

The change MUST resolve exactly the eight pre-existing mypy diagnostics: seven in `bot/services/greeting_service.py` (channel narrowing, explicit annotations, and removed/moved inaccurate unused ignores) plus the generic `Command` type-argument diagnostic at `bot/core/i18n.py:294`. The cleanup MUST be limited to explicit type annotations, safe Discord channel narrowing, and removing/moving inaccurate unused ignores; it MUST NOT alter runtime behavior, control flow, or sent payloads. The cleanup MUST NOT perform broad type changes across the codebase or touch unrelated files. Running the focused mypy command `uv run mypy bot/services/greeting_service.py` MUST produce no diagnostics, and because mypy follows imports, this MUST include the `bot/core/i18n.py:294` diagnostic surfaced through the service.

#### Scenario: Focused mypy is clean including imported i18n diagnostic

- GIVEN the eight pre-existing mypy diagnostics are unresolved
- WHEN `uv run mypy bot/services/greeting_service.py` is run after the bounded cleanup
- THEN the command exits with no diagnostics and the `bot/core/i18n.py:294` generic `Command` diagnostic is also clear

#### Scenario: Bounded cleanup preserves runtime behavior and full test safety

- GIVEN the cleanup edits only annotations, safe channel narrowing, and unused ignores in `bot/services/greeting_service.py` and the single `Command` annotation at `bot/core/i18n.py:294`
- WHEN `uv run pytest tests/test_greeting_service.py -v --no-cov` and `uv run pytest` are run
- THEN the guard and full suite pass exactly as before, no sent payload or control-flow changes occur, and no unrelated file is modified
