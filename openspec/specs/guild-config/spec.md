# Guild Configuration Specification

## Purpose

Define guild settings storage, cache-first reads, and default creation on join.

## Requirements

### Requirement: Default values

The system MUST create guild records with default prefix `nb!` and language `es`.

#### Scenario: New guild defaults

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN prefix is `nb!`, language is `es`, and active is true

### Requirement: Cache-first reads

The system MUST read guild configuration from cache first and fall back to the database.

#### Scenario: Cache hit

- GIVEN the configuration is cached
- WHEN a command requests the guild prefix
- THEN the value is returned from cache

#### Scenario: Cache miss

- GIVEN the configuration is not cached
- WHEN a command requests the guild prefix
- THEN the value is loaded from the database and stored in cache

### Requirement: CRUD

The system MUST support create, read, update, and delete of guild configuration.

#### Scenario: Update prefix

- GIVEN an existing guild configuration
- WHEN an administrator updates the prefix to `!`
- THEN subsequent reads return `!`

#### Scenario: Soft delete

- GIVEN an active guild configuration
- WHEN the configuration is deleted
- THEN active is set to false

### Requirement: Default on join

The system MUST create a default guild configuration when the bot joins a new guild.

#### Scenario: Guild join

- GIVEN the bot is added to a guild not present in the database
- WHEN the guild join event fires
- THEN a new Guild record is inserted with default values

### Requirement: Panel persistence fields

The system MUST store the deployed ticket panel message ID and channel ID in the guild configuration.

#### Scenario: Panel deployment persisted

- GIVEN `/ticket_panel` deploys a panel message
- WHEN the deployment succeeds
- THEN `ticketPanelMessageId` and `ticketPanelChannelId` are updated in the guild record and cache

#### Scenario: Panel lookup on startup

- GIVEN a guild has stored panel IDs
- WHEN the bot starts
- THEN the panel message is located and the persistent view is re-registered

#### Scenario: Missing panel message

- GIVEN stored panel IDs point to a deleted message
- WHEN the bot starts
- THEN the stale IDs are cleared and a warning is logged

### Requirement: Dashboard config sync via Realtime CDC

Dashboard guild config writes MUST NOT call any inbound bot webhook. Cache invalidation MUST rely on outbound Supabase Realtime CDC (`cache-sync-realtime`). The Server Action MUST complete after the Supabase write succeeds regardless of bot connectivity.

#### Scenario: Config write does not call webhook

- GIVEN the dashboard writes a guild config change to Supabase
- WHEN the Supabase write succeeds
- THEN the Server Action returns success without POSTing to a bot webhook endpoint

#### Scenario: Bot invalidates via Realtime

- GIVEN the bot Realtime subscriber is connected
- WHEN Supabase emits a `guild` UPDATE for guild G
- THEN the bot invalidates the guild cache for G

### Requirement: Concurrent guild backfill on startup

`on_ready` guild backfill MUST use `asyncio.gather()` instead of sequential awaits. Backfill MUST handle concurrent guild config fetches without race conditions.

(Previously: sequential for-loop with await per guild)

#### Scenario: Multiple guilds backfilled concurrently

- GIVEN the bot is a member of 5 guilds at startup
- WHEN `on_ready` fires
- THEN all 5 `ensure_guild_exists` calls run concurrently via `asyncio.gather()`

#### Scenario: Large guild count bounded

- GIVEN the bot is a member of 100+ guilds
- WHEN `on_ready` fires
- THEN `asyncio.gather()` completes without overwhelming Supabase (rate limits apply at client level)
