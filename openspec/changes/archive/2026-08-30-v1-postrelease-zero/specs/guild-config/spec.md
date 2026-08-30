# Delta for guild-config

## MODIFIED Requirements

### Requirement: Default values

The system MUST create guild records with default `prefix` `nb!` (data-only, persisted for backward compatibility and display; MUST NOT gate command invocation because `get_prefix` resolves to `[]` per `bot-core`) and language `es`. All new guild inserts and migrations adding `prefix`/`permissionMatrix` MUST be idempotent DDL via `IF NOT EXISTS` (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) for live re-runs.

(Previously: prefix described as active command dispatch prefix `nb!`)

#### Scenario: New guild defaults

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN `prefix` is `nb!` (data-only), `language` is `es`, and `active` is true, and no prefix command is invocable (`get_prefix -> []`)

#### Scenario: Prefix is data-only

- GIVEN a guild record with `prefix='nb!'`
- WHEN a user sends `nb!ping` as text
- THEN no command is invoked; prefix field is only read for display/config purposes

### Requirement: Cache-first reads

The system MUST read guild configuration (including `prefix` data-only, `language`, `permissionMatrix`) from cache first via `cache_key(guild_id, "config")` → `{guild_id}:config` and fall back to the database. Cache keys MUST be guild-scoped and MUST NOT leak across guilds. `t()` lookups MUST use the cached `language`.

(Previously: described as reading guild prefix for command dispatch)

#### Scenario: Cache hit

- GIVEN the configuration is cached at `{guild_id}:config`
- WHEN a command requests guild config or `t()` language
- THEN the value is returned from cache without DB fetch

#### Scenario: Cache miss

- GIVEN the configuration is not cached
- WHEN a command requests guild config
- THEN the value is loaded from the database and stored in cache via `cache_key`

#### Scenario: Prefix cache does not enable prefix dispatch

- GIVEN the prefix is cached as `nb!`
- WHEN `get_prefix` is evaluated
- THEN it still resolves to `[]` (slash-only) and no prefix command is invocable

### Requirement: CRUD

The system MUST support create, read, update, and delete of guild configuration. Updates to `prefix` MUST persist as data-only (no dispatch effect) and be validated via idempotent DDL. All user-facing CRUD feedback MUST use `t()`. `permissionMatrix` updates MUST use the 7-key matrix with `IF NOT EXISTS` migration guard.

(Previously: update prefix implied dispatch change to `!`)

#### Scenario: Update prefix data-only

- GIVEN an existing guild configuration
- WHEN an administrator updates the prefix to `!` via dashboard or command
- THEN the stored `prefix` becomes `!` but subsequent slash command dispatch remains via `/command` only (`get_prefix -> []`)

#### Scenario: Soft delete

- GIVEN an active guild configuration
- WHEN the configuration is deleted
- THEN `active` is set to false and cache is invalidated via `cache_key`

#### Scenario: Idempotent DDL safe to re-run

- GIVEN migration adding `prefix` or `permissionMatrix` has been applied
- WHEN the migration SQL is executed again
- THEN no error occurs (`IF NOT EXISTS` makes it a no-op)
