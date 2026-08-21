# Delta for Greeting Configuration

Cycle 2 of 3. Adds a nullable `theme_id` greeting-config column (migration
`021+`, not `019` which is already taken by subtickets/notes) to select the
greeting card theme (`default` or `gaming_neon`). The dashboard gets a
`GreetingThemeSelector` and writes flow through the existing Realtime CDC path
(hybrid: the dashboard `/welcome` preview AND the bot cache both observe the
change). A new 60-second greeting avatar cache MUST be guild-scoped via
`cache_key(guild_id, "greeting_avatar")`. The migration is additive and
nullable; the live `schema_migrations` table MUST be validated before apply.

## ADDED Requirements

### Requirement: theme_id column is additive and nullable

The system MUST add an optional nullable `theme_id` (text) column to
`greeting_config` via an additive, backwards-compatible migration numbered
`021` or higher (NOT `019`, which is taken by `019_subtickets_notes.sql`). The
column MUST default to null (theme = `default`). Existing rows MUST remain
valid: pre-migration rows read back `theme_id` as null and render with the
default theme. The migration identity MUST be checked against the live
`schema_migrations` table before apply (Cycle 1 + prior staging drift on
2026-08-19). `DROP COLUMN`/`DROP INDEX` MUST be the rollback path (additive
nullable, reversible).

#### Scenario: Existing rows remain valid after migration

- GIVEN an existing `greeting_config` row without a `theme_id` column
- WHEN the additive `021+` migration is applied
- THEN the row is preserved and reads back `theme_id` as null

#### Scenario: New guild defaults to null theme_id

- GIVEN the bot joins a guild with no existing record
- WHEN the default greeting configuration is created
- THEN `theme_id` is null and the default theme renders

#### Scenario: Migration identity checked live

- GIVEN the `021+` migration file is staged
- WHEN the migration is about to apply
- THEN the live `schema_migrations` table is queried and the migration is applied only if its version is not already recorded

#### Scenario: Rollback drops the nullable column

- GIVEN the `021+` migration was applied
- WHEN the rollback runs (`DROP COLUMN theme_id` and any associated index)
- THEN the column is removed, existing rows remain valid, and reads fall back to the default theme

### Requirement: theme_id round-trips through the model

`GreetingConfig` MUST include `theme_id: str | None = None`. `from_db_row`
SHALL map `row["themeId"]` and `to_db_dict` SHALL include
`"themeId": self.theme_id`. Round-trips MUST preserve a null and a non-null
value unchanged.

#### Scenario: Deserialize config with theme_id

- GIVEN a DB row with `themeId = "gaming_neon"`
- WHEN `GreetingConfig.from_db_row(row)` is called
- THEN `config.theme_id == "gaming_neon"`

#### Scenario: Deserialize config without theme_id

- GIVEN a DB row with `themeId = null` or missing
- WHEN `GreetingConfig.from_db_row(row)` is called
- THEN `config.theme_id is None`

#### Scenario: Serialize config with theme_id

- GIVEN a `GreetingConfig` with `theme_id = "gaming_neon"`
- WHEN `config.to_db_dict()` is called
- THEN the dict includes `"themeId": "gaming_neon"`

#### Scenario: Serialize config without theme_id

- GIVEN a `GreetingConfig` with `theme_id = None`
- WHEN `config.to_db_dict()` is called
- THEN the dict includes `"themeId": None`

### Requirement: Greeting avatar cache is guild-scoped with 60s TTL

The system MAY introduce a greeting avatar cache to dedupe avatar fetches.
The cache MUST build its key via `cache_key(guild_id, "greeting_avatar")` so
entries are `{guild_id}:greeting_avatar` and cannot leak across guilds. A bare
`"greeting_avatar"` key MUST NOT be used. The TTL MUST be 60 seconds. The
cache MUST be invalidated by the existing Supabase Realtime CDC flow when
`greeting_config` changes (free, since `greeting_config` is already a
subscribed table). The `cache_key` helper MUST be imported from
`bot.core.cache` and MUST NOT be redefined locally.

#### Scenario: Cache key is guild-scoped

- GIVEN a greeting avatar cache entry for guild G
- WHEN the key is built
- THEN it is `cache_key(gid, "greeting_avatar")` → `{gid}:greeting_avatar`, not the bare entity

#### Scenario: No cross-guild leak

- GIVEN guild A and guild B both cache an avatar
- WHEN the cache is read for guild A
- THEN guild B's entry is not returned

#### Scenario: CDC invalidates avatar cache on theme change

- GIVEN the bot Realtime subscriber is connected and the avatar cache holds guild G's entry
- WHEN Supabase emits a `greeting_config` change for guild G (e.g. `theme_id` updated)
- THEN the guild G greeting cache AND avatar cache entries are invalidated so the new theme/avatar is observed

## MODIFIED Requirements

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`, `welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`, `goodbye_card_enabled`, an optional nullable `onboarding_channel_id`, an optional nullable `updatedAt` (timestamptz), and an optional nullable `theme_id` (text, default null → `default` theme) in the guild greeting record.
(Previously: the greeting record stored the welcome/goodbye channels, templates, card toggles, onboarding channel, and updatedAt; it had no `theme_id` field.)

#### Scenario: Default values for new guild

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN greeting channels and `onboarding_channel_id` are null, templates use defaults, card toggles are false, `updatedAt` is null, and `theme_id` is null (default theme)

#### Scenario: Onboarding channel round-trips

- GIVEN a guild configuration with `onboarding_channel_id` set to channel C
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the camelCase `onboardingChannelId` key and the value is unchanged

#### Scenario: updatedAt round-trips

- GIVEN a guild configuration with `updatedAt` set to a timestamp T
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the `updatedAt` key and the value equals T

#### Scenario: theme_id round-trips

- GIVEN a guild configuration with `theme_id` set to `"gaming_neon"`
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the camelCase `themeId` key and the value equals `"gaming_neon"`

### Requirement: New caches use guild-scoped keys

Any new cache introduced for greeting rendering (e.g. a Cycle 2 greeting avatar cache) MUST build its key via the `cache_key(guild_id, entity)` helper so entries are scoped `{guild_id}:{entity}` and cannot leak across guilds. A bare entity key MUST NOT be used. The Cycle 2 greeting avatar cache (`cache_key(gid, "greeting_avatar")`, 60s TTL) is governed by this requirement; the `cache_key` helper MUST be imported from `bot.core.cache` and MUST NOT be copied into a service module.
(Previously: governed any cache added during the Cycle 1 split; Cycle 1 introduced none.)

#### Scenario: Cache key is guild-scoped

- GIVEN a new greeting cache is introduced
- WHEN a key is built for guild G and entity E
- THEN the key is `{guild_id}:{entity}` via `cache_key(gid, E)`, not the bare entity

#### Scenario: No cross-guild leak

- GIVEN guild A and guild B cache entries for the same entity
- WHEN the cache is read for guild A
- THEN guild B's entry is not returned

### Requirement: Dashboard greeting config sync via Realtime CDC

Dashboard greeting config writes — including `theme_id` — MUST NOT call any inbound bot webhook. Cache invalidation MUST rely on outbound Supabase Realtime CDC (`cache-sync-realtime`). The dashboard `/welcome` preview and the bot greeting cache are BOTH observers of the same CDC stream; the dashboard MAY refetch on CDC, and the bot MUST invalidate its guild cache on CDC. This keeps `theme_id` consistent across bot and dashboard without a coupling webhook.
(Previously: required dashboard greeting writes to use Realtime only; did not name the `theme_id` field or the dashboard-AND-bot dual observer contract.)

#### Scenario: Greeting config write does not call webhook

- GIVEN the dashboard writes a greeting config change (including `theme_id`) to Supabase
- WHEN the Supabase write succeeds
- THEN the Server Action returns success without POSTing to a bot webhook endpoint

#### Scenario: Bot invalidates via Realtime

- GIVEN the bot Realtime subscriber is connected
- WHEN Supabase emits a greeting_config change for guild G
- THEN the bot invalidates the greeting cache (and avatar cache) for G

#### Scenario: Dashboard observes CDC for theme preview

- GIVEN the dashboard `/welcome` page is open and the bot cache holds guild G's config
- WHEN Supabase emits a `greeting_config` change for guild G
- THEN the bot invalidates its cache AND the dashboard MAY refetch so the `/welcome` preview reflects the new `theme_id`

## Scope boundary

This delta adds the `theme_id` column, model round-trip, avatar cache, and
dashboard+bot CDC observer contract. The neon *rendering* is specified in
`welcome-goodbye`; the neon palette tokens are specified in `brand-tokens`.
The migration is `021+`; `019` is already taken. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
`bot/utils/time.py` and `bot/utils/timeparse.py` MUST NOT be merged.
