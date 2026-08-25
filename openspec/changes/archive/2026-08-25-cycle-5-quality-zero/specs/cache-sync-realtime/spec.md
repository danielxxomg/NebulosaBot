# Delta for cache-sync-realtime

> Change: `cycle-5-quality-zero`. Scope: subscriber extends to `member` + `economy_config`; the documented-deferral requirement is superseded; echo suppression wired into member/economy RPC mutators BEFORE publication; poll fallback gains an incremental option.

## ADDED Requirements

### Requirement: Member and economy_config subscription

The subscriber MUST extend coverage to the `member` and `economy_config` tables (INSERT/UPDATE/DELETE). `_extract_guild_id` MUST resolve both tables from `record["guildId"]`, coercing numeric ids to string for cache-key consistency. Invalidation MUST follow the existing pattern: `cache.invalidate_guild(guild_id)`.

#### Scenario: Member CDC event invalidates guild cache

- GIVEN a CDC event fires for the `member` table
- WHEN the record is processed
- THEN `_extract_guild_id` returns `str(record["guildId"])` and `cache.invalidate_guild()` is called

#### Scenario: Economy config CDC event invalidates guild cache

- GIVEN a CDC event fires for the `economy_config` table
- WHEN the record is processed
- THEN `_extract_guild_id` returns `str(record["guildId"])` and `cache.invalidate_guild()` is called

#### Scenario: DELETE events use old_record

- GIVEN a DELETE CDC event for `member` or `economy_config`
- WHEN the record object is empty or missing identifiers
- THEN the guild id is resolved from `old_record["guildId"]`

### Requirement: Echo suppression wired before publication

Every RPC mutator in `member_db` and `economy_db` MUST invoke the injected `self._on_write(table, guild_id)` hook (recent-writes marking) so bot-originated writes are recorded before any CDC echo can arrive. This wiring MUST land BEFORE the publication migration adds `member`/`economy_config` to the Realtime publication (hard ordering — inverting it lets every own RPC write bounce back as an unfiltered echo event).

#### Scenario: RPC mutator marks recent write

- GIVEN the bot calls a `member_db` or `economy_db` RPC mutator for guild G
- WHEN the write completes
- THEN the recent-writes set contains `{table}:G` before any CDC echo could arrive

#### Scenario: Echo of own write is skipped

- GIVEN the bot wrote to `member` 2 seconds ago
- WHEN the CDC echo arrives for that table/guild
- THEN invalidation is skipped per the existing Self-echo filtering semantics

#### Scenario: Hard ordering is verifiable in history

- GIVEN the slice's commit history is inspected
- WHEN the `_on_write` wiring commit is compared with the publication ALTER commit
- THEN the wiring precedes the ALTER

## MODIFIED Requirements

### Requirement: Realtime subscriber lifecycle

The bot SHALL connect to Supabase Realtime via `acreate_client` (async) on startup and subscribe to INSERT/UPDATE/DELETE events on `guild`, `greeting_config`, `ticket`, `ticket_note`, `member`, and `economy_config` tables. The subscriber MUST start in `setup_hook` and stop on `cog_unload` or shutdown. Connection status MUST be tracked via the `on_subscribe(status, err)` callback using `RealtimeSubscribeStates`.

#### Scenario: Subscriber starts on bot startup

- GIVEN the bot is starting up
- WHEN `setup_hook` executes
- THEN a Supabase Realtime channel is created and subscribed to all 6 tables
- AND the subscription callback is registered

#### Scenario: Subscriber stops on shutdown

- GIVEN the Realtime subscriber is active
- WHEN `cog_unload` or bot shutdown occurs
- THEN the channel is unsubscribed and the async client is closed

#### Scenario: Subscription status tracked

- GIVEN the subscriber has connected
- WHEN `on_subscribe` is called with `status=SUBSCRIBED`
- THEN the subscriber logs a success message and begins processing CDC events

### Requirement: Poll fallback

When the WebSocket is down, the bot MUST poll Supabase every 30 seconds to detect changes. Tables carrying a suitable timestamp column support incremental queries filtered by that column against `last_check`: `ticket` uses `lastActivity`; `member` and `economy_config` MAY gain optional `updatedAt` columns enabling incremental polls. Config-style tables lacking such columns (`guild`, `greeting_config`) fall back to querying all guild IDs from `guild` and invalidating their caches.

#### Scenario: Poll detects recent ticket activity

- GIVEN the poll fallback is active
- WHEN the poll queries `SELECT "guildId" FROM ticket WHERE "lastActivity" > $last_check`
- THEN `cache.invalidate_guild()` is called for each returned guild_id
- AND `last_check` is updated to the current timestamp

#### Scenario: Incremental poll uses updatedAt when available

- GIVEN `member` carries the optional `updatedAt` column
- WHEN the poll runs for `member`
- THEN the query filters `"updatedAt" > $last_check` instead of scanning all rows

#### Scenario: Full-scan fallback without updatedAt

- GIVEN `economy_config` lacks the optional `updatedAt` column
- WHEN the poll runs for `economy_config`
- THEN all guild ids are invalidated via the config-table full scan

#### Scenario: Poll invalidates all guild configs

- GIVEN the poll fallback is active
- WHEN the poll queries `SELECT id FROM guild`
- THEN `cache.invalidate_guild()` is called for every guild_id returned

#### Scenario: Poll deactivates on WebSocket recovery

- GIVEN the poll fallback is running
- WHEN the health check confirms `SUBSCRIBED` status
- THEN the poll loop stops and `last_check` is reset

### Requirement: Migration prerequisite — watchdog event counting

Before the subscriber can receive the new tables' events, an idempotent, re-runnable DO-block migration MUST extend the publication: `ALTER PUBLICATION supabase_realtime ADD TABLE member, economy_config;` (alongside the already-published four tables). The watchdog MUST count RECEIVED events (incremented at the top of `_handle_cdc` before any filtering), not PROCESSED events. If no CDC events are received within 30 seconds of `SUBSCRIBED`, log a warning.

#### Scenario: Migration applied — events received

- GIVEN the publication migration has been applied
- WHEN the bot subscribes and a member write occurs externally
- THEN CDC events are received within 5 seconds
- AND the watchdog counter increments even if the event is later skipped

#### Scenario: Migration not applied — warning logged

- GIVEN the extension migration has NOT been applied
- WHEN 30 seconds pass after `SUBSCRIBED` with zero events
- THEN a warning is logged about missing publication

#### Scenario: Watchdog counts skipped events

- GIVEN a CDC event arrives but is filtered (self-echo, no guild_id)
- WHEN processed
- THEN the watchdog counter still increments
- AND no migration warning is logged

#### Scenario: Idempotent migration safe to re-run

- GIVEN the publication migration was already applied
- WHEN the DO-block SQL is executed again
- THEN no error occurs (adding an already-published table is a no-op)

### Requirement: Realtime coverage and deferred cache scope are documented

The cache/Realtime documentation MUST state that CDC coverage includes all six subscribed tables: `guild`, `greeting_config`, `ticket`, `ticket_note`, `member`, and `economy_config`. The former deferral of member/economy coherence MUST be removed — no documentation MAY still describe those entities as outside the Realtime contract.

(Previously: coverage was limited to four tables and member/economy changes were documented as a deferred S2 item.)

#### Scenario: Published table scope is explicit

- GIVEN the Realtime configuration and cache documentation are reviewed
- WHEN the subscribed table list is compared with the contract
- THEN it contains exactly the six supported tables including member/economy_config

#### Scenario: Deferral wording is gone

- GIVEN the same documentation is reviewed
- WHEN searched for the former deferral statement about member/economy changes
- THEN no such deferral remains

#### Scenario: Existing CDC behavior is preserved

- GIVEN a supported table emits INSERT, UPDATE, or DELETE
- WHEN the subscriber handles the event
- THEN the existing guild cache invalidation behavior remains unchanged
