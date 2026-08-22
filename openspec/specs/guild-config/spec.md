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

<!-- BEGIN DELTA: voice-moderation-permissions (guild-config) -->
## ADDED Requirements

### Requirement: Permission matrix column

The system MUST add a `permissionMatrix` JSONB column to the `guild` table with a NOT NULL default of `'{}'::jsonb`. The migration MUST be additive and idempotent (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), so existing guild rows receive `'{}'::jsonb` and re-applying the migration is a no-op. The `GuildConfig` dataclass MUST expose `permission_matrix: dict[str, list[str]]` (default `dict()`). The `from_db_row`/`to_db_dict` round-trip MUST preserve the matrix under the camelCase key `"permissionMatrix"` alongside all existing fields (`prefix`, `language`, `modRoleId`, `logEnabled`, `logChannelId`, etc.). Unknown permission keys in the matrix (e.g. `{"unknown.perm": ["roleX"]}`) MUST load without error — the `can()` resolver ignores keys not in the `PERMISSIONS` frozenset.

#### Scenario: Migration adds column with default

- GIVEN migration 024 has been applied to a live database
- WHEN a new guild row is inserted without specifying `permissionMatrix`
- THEN the column value is `'{}'::jsonb`

#### Scenario: Round-trip preserves matrix and other fields

- GIVEN a guild row with `prefix='nb!'`, `language='es'`, and `permissionMatrix={"moderation.ban": ["roleA"]}`
- WHEN the row is loaded via `from_db_row` and re-serialized via `to_db_dict`
- THEN the round-trip preserves `prefix`, `language`, and `permissionMatrix` under the camelCase key `"permissionMatrix"`

#### Scenario: Unknown permission keys tolerated

- GIVEN a guild row with `permissionMatrix={"unknown.perm": ["roleX"]}`
- WHEN `from_db_row` loads the row
- THEN no error is raised and `can("unknown.perm", ...)` returns False (ignored)

#### Scenario: Idempotent migration safe to re-run

- GIVEN migration 024 has already been applied
- WHEN the migration SQL is executed again
- THEN no error occurs (IF NOT EXISTS makes it a no-op)

### Requirement: Matrix read from config cache

The system MUST read the permission matrix from the existing `{guild_id}:config` cache entry (via `GuildService.get_config(guild_id)`). The matrix MUST NOT introduce a new cache key (no bare `perm_matrix` entity string — cross-guild leak guard). When a CDC event fires for the `guild` table, `invalidate_guild(guild_id)` MUST evict the config entry including the matrix, so subsequent `can()` calls re-fetch the updated matrix.

#### Scenario: Matrix read from cached config

- GIVEN a guild's config (including matrix) is cached at `{guild_id}:config`
- WHEN `can()` resolves the matrix for a permission check
- THEN it reads from the cached entry without an extra DB fetch

#### Scenario: CDC invalidates matrix with config

- GIVEN a guild's config is cached
- WHEN a Supabase Realtime CDC event fires for the `guild` table (e.g. dashboard updated `permissionMatrix`)
- THEN `invalidate_guild(guild_id)` evicts the config entry (including the matrix) and the next `can()` call re-fetches
<!-- END DELTA: voice-moderation-permissions (guild-config) -->
