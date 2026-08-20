# Delta for Greeting Configuration

Cycle 1. Adds an additive `updatedAt` column to `greeting_config` so the
Realtime poll fallback can issue incremental queries instead of full-table
scans, and codifies guild-scoped cache keys for any new caches. No behavior
change to the cache-first read path or to existing dispatch logic.

## ADDED Requirements

### Requirement: updatedAt column is additive

The system MUST add a nullable `updatedAt` (timestamptz) column to
`greeting_config` via an additive, backwards-compatible migration. Existing
rows MUST remain valid: pre-migration rows read back `updatedAt` as null.
Reads and writes MUST flow through the existing cache-first `GreetingConfig`
path. The migration identity MUST be unique and MUST NOT collide with the
existing duplicate `003` migrations; the rename/reconciliation MUST be
validated against the live `schema_migrations` table or shipped as a no-op
reconciliation migration, never as a raw file rename of a deployed migration.

#### Scenario: Existing rows remain valid after migration

- GIVEN an existing `greeting_config` row without an `updatedAt` column
- WHEN the additive migration is applied
- THEN the row is preserved and reads back `updatedAt` as null

#### Scenario: New guild defaults to null updatedAt

- GIVEN the bot joins a guild with no existing record
- WHEN the default greeting configuration is created
- THEN `updatedAt` is null

#### Scenario: Migration identity does not collide

- GIVEN `003_economy_config.sql` and `003_subtitles_notes.sql` both carry the `003` prefix
- WHEN the `updatedAt` migration is added
- THEN it uses a distinct non-`003` prefix and the live `schema_migrations` table is checked before applying

### Requirement: Realtime poll fallback uses incremental updatedAt queries

When the Realtime poll fallback (`cache-sync-realtime`) is active, the bot
MUST query `greeting_config` incrementally using `updatedAt > $last_check`
instead of the full-table `SELECT id FROM guild` scan the S1 fallback used
for config tables. `last_check` MUST be updated after each poll. When
`updatedAt` is null for a row (pre-migration data), the row MUST be included
in the poll result so it is not silently skipped.

#### Scenario: Poll queries by updatedAt

- GIVEN the poll fallback is active
- WHEN the poll queries `greeting_config`
- THEN the query filters on `updatedAt > $last_check` and returns only changed guilds

#### Scenario: Null updatedAt rows are included

- GIVEN a `greeting_config` row has `updatedAt = null`
- WHEN the incremental poll runs
- THEN the row is included (null `updatedAt` is treated as "always changed") and its guild cache is invalidated

#### Scenario: last_check advances after each poll

- GIVEN a poll cycle completes
- WHEN the next poll is scheduled
- THEN `last_check` has been updated to the current timestamp

### Requirement: New caches use guild-scoped keys

Any new cache introduced for greeting rendering (e.g. a Cycle 2 greeting
avatar cache) MUST build its key via the `cache_key(guild_id, entity)` helper
so entries are scoped `{guild_id}:{entity}` and cannot leak across guilds.
A bare entity key MUST NOT be used. Cycle 1 introduces no new greeting
caches; this requirement governs any cache added during the Cycle 1 split.

#### Scenario: Cache key is guild-scoped

- GIVEN a new greeting cache is introduced
- WHEN a key is built for guild G and entity E
- THEN the key is `{guild_id}:{entity}` via `cache_key(gid, E)`, not the bare entity

#### Scenario: No cross-guild leak

- GIVEN guild A and guild B cache entries for the same entity
- WHEN the cache is read for guild A
- THEN guild B's entry is not returned

## MODIFIED Requirements

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`,
`welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`,
`goodbye_card_enabled`, an optional nullable `onboarding_channel_id`, and an
optional nullable `updatedAt` (timestamptz) in the guild greeting record.

(Previously: the column set did not include `updatedAt`; the poll fallback
could not issue incremental queries against `greeting_config`.)

#### Scenario: Default values for new guild

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN greeting channels and `onboarding_channel_id` are null, templates use defaults, card toggles are false, and `updatedAt` is null

#### Scenario: Onboarding channel round-trips

- GIVEN a guild configuration with `onboarding_channel_id` set to channel C
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the camelCase `onboardingChannelId` key and the value is unchanged

#### Scenario: updatedAt round-trips

- GIVEN a guild configuration with `updatedAt` set to a timestamp T
- WHEN the configuration is saved and re-read
- THEN `from_db_row()`/`to_db_dict()` preserve the `updatedAt` key and the value equals T

## Scope boundary

Cycle 2 (Neon) and Cycle 3 (timer, 12h, banana, RLS, voice/moderation,
ScheduledAction, has_perm) are OUT OF SCOPE. This delta adds `updatedAt` and
codifies guild-scoped cache keys; it does not change the dispatch, card-toggle,
or CTA behavior already specified in `greeting-config`.
