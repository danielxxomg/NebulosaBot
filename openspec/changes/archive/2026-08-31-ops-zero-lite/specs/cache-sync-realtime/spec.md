# Delta for cache-sync-realtime

## ADDED Requirements

### Requirement: CDC echo guard — external-only invalidation [PRESERVED]

The system MUST preserve the shipped CDC echo suppression (verified: `bot/core/db/member_db.py:61-62`, `bot/core/db/economy_db.py:49-50,102-103,133-134,179-180` via `self._on_write` → `RealtimeCacheSubscriber.mark_recent_write` at `bot/core/realtime.py:527`; `RecentWriteSet` TTL 5s at `:144`; `_handle_cdc` check at `:589` via `recent_writes.contains`; `SUBSCRIBED_TABLES` includes `member, economy_config` at `:54-55`; `_extract_guild_id` at `:122`). Self-echoes MUST NOT call `cache.invalidate_guild`; external events MUST still invalidate. Regression guard: `tests/test_database.py:1968 TestMemberEconomyOnWriteHooks` + `:2065 test_hook_marks_recent_writes_set_for_echo_skip` MUST stay green.

#### Scenario: External CDC invalidates

- GIVEN dashboard updated `member` for guild G directly in Supabase
- WHEN CDC arrives for `member` with `record.guildId=G` not in `RecentWriteSet`
- THEN `cache.invalidate_guild(G)` is called

#### Scenario: Self-write echo is suppressed (negative)

- GIVEN bot called `update_member_xp(G, ...)` which invoked `_on_write("member", G)` → `RecentWriteSet.mark`
- WHEN CDC echo arrives for same `G` within 5s TTL
- THEN `_handle_cdc` finds `contains==True` and skips `invalidate_guild`

#### Scenario: Expired self-write re-invalidates

- GIVEN self-write entry expired (>5s, lazy eviction on `contains`)
- WHEN CDC arrives for same key
- THEN invalidation proceeds

### Requirement: Publication remains extended via 026 — idempotence invariant [PRESERVED]

The system MUST keep `supabase_realtime` publication extended to `member, economy_config` as shipped in `migrations/026_realtime_member_economy_config.sql` (canonical DO-block `duplicate_object` SQLSTATE 42710 pattern from `migrations/007_realtime_publication.sql`; publication ADD does NOT support `IF NOT EXISTS` natively). Any future publication DDL MUST preserve the 007 DO-block pattern; `ADD COLUMN IF NOT EXISTS` guards `updatedAt`; `CREATE OR REPLACE` + `DROP TRIGGER IF EXISTS` guards triggers. No `migrations/030_*.sql` is required. DDL MUST remain re-runnable with zero duplicate-object errors. Hard ordering is already satisfied: hook wiring landed in `027b636` before `026`.

#### Scenario: Existing publication re-run is idempotent

- GIVEN publication already contains `member, economy_config`
- WHEN `026` DO-block re-executes
- THEN no error (duplicate_object silently skipped)

#### Scenario: guild_id filtering enforced

- GIVEN CDC poll or DB query for guild G
- WHEN executed
- THEN `WHERE guildId = G` scopes results; cross-guild leak fails

#### Scenario: Zero-hybrid and ',' trigger untouched

- GIVEN change is applied
- WHEN `bot/bot.py:_noop_prefix` and `TicketsCog.on_message` (`bot/cogs/tickets.py:241`) are inspected
- THEN prefix surface stays `[]` and `,` timer debounce remains functional

### Requirement: Cache module comment accuracy [NET-NEW]

The system MUST fix the stale header in `bot/core/cache.py:9-10` that claims `Deferred: member, economy_config — Realtime invalidation currently not wired; TTL-only`. The line MUST be updated to reflect the shipped wired state (e.g. remove Deferred claim; list `member, economy_config` as realtime-invalidated alongside `guild, greeting_config, ticket, ticket_note`).

#### Scenario: Stale comment removed

- GIVEN `bot/core/cache.py` header is read
- WHEN inspected
- THEN no `Deferred`/`not wired` claim about `member, economy_config` remains and the realtime-invalidated list includes them
