# Delta for Guild Configuration

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

