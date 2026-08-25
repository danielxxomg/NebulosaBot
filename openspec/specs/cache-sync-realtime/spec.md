# Cache Sync Realtime Specification

## Purpose

Replace inbound webhook (Cloudflare Tunnel + HMAC) with outbound Supabase Realtime CDC for cache invalidation. Same invalidation semantics, zero public exposure.

## Requirements

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

### Requirement: Cache invalidation on CDC events

When a CDC event fires, the bot MUST extract the identifier from the payload's `record` object and invalidate the corresponding cache entry. The CDC payload contains `record`, `old_record`, `type`, `table`, and `schema` fields.

#### Scenario: Guild table change invalidates guild config cache

- GIVEN a CDC event fires for the `guild` table
- WHEN the `record` object is read
- THEN `cache.invalidate_guild(record["id"])` is called with the guild id as string

#### Scenario: Greeting config change invalidates greeting cache

- GIVEN a CDC event fires for the `greeting_config` table
- WHEN the `record` object is read
- THEN `cache.invalidate_guild(record["guildId"])` is called

#### Scenario: Ticket change invalidates ticket cache

- GIVEN a CDC event fires for the `ticket` table
- WHEN the `record` object is read
- THEN `cache.invalidate_guild(record["guildId"])` is called

#### Scenario: Ticket note change invalidates ticket cache

- GIVEN a CDC event fires for the `ticket_note` table
- WHEN the `record` object is read
- THEN the bot resolves the `guildId` from the related ticket and calls `cache.invalidate_guild()`

#### Scenario: DELETE event uses old_record

- GIVEN a CDC event with `type=DELETE`
- WHEN the `record` object is empty or missing identifiers
- THEN the bot reads from `old_record` instead

<!-- BEGIN DELTA: cycle-5-quality-zero (cache-sync-realtime) -->
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
<!-- END DELTA: cycle-5-quality-zero (cache-sync-realtime) -->

### Requirement: Payload table resolution

The system MUST resolve the source table for a CDC event. When the payload includes a `table` field, use it directly. When `table` is `None` or absent, resolve from the channel subscription filter that registered the callback.

#### Scenario: Payload includes table field

- GIVEN a CDC event with `table="guild"`
- WHEN processed
- THEN the system uses `"guild"` as the source table

#### Scenario: Payload omits table field

- GIVEN a CDC event with `table=None` or missing
- WHEN processed
- THEN the system resolves the table from the subscription filter

#### Scenario: Unresolvable table

- GIVEN a CDC event with no `table` and no matching subscription filter
- WHEN processed
- THEN the system SHALL log a warning and skip the event

### Requirement: Reconnection and health check

supabase-py handles WebSocket reconnection internally. The bot SHALL check subscription status every 60 seconds and log the current state. If not `SUBSCRIBED` for >60 seconds, enable poll fallback. The system SHALL log WebSocket close events and reconnections. After N consecutive unhealthy cycles, escalate log level from WARNING to ERROR.

#### Scenario: Healthy subscription logged

- GIVEN status is `SUBSCRIBED`
- WHEN the 60-second health check runs
- THEN a debug log confirms health

#### Scenario: Disconnected triggers poll fallback

- GIVEN status is `CHANNEL_ERROR` or `TIMED_OUT` for >60 seconds
- WHEN the health check runs
- THEN poll fallback is activated and a warning is logged

#### Scenario: Reconnection disables poll fallback

- GIVEN poll fallback is active
- WHEN status returns to `SUBSCRIBED`
- THEN poll fallback is deactivated and reconnection is logged

#### Scenario: WebSocket close event logged

- GIVEN the WebSocket closes unexpectedly
- WHEN the close event is received
- THEN the system SHALL log the close code and reason

#### Scenario: Escalation after repeated unhealthy cycles

- GIVEN N consecutive unhealthy health check cycles
- WHEN the next cycle runs
- THEN the system SHALL log at ERROR level

(Previously: No close/reconnect logging, no escalation)

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

### Requirement: Self-echo filtering

The bot MUST track recent writes in an ephemeral in-memory set (RAM only, not persisted). Entries are keyed by `{table}:{identifier}` with a TTL of ~5 seconds. When a CDC event arrives, the bot checks if it recently wrote to that row; if yes, invalidation is skipped.

#### Scenario: Bot write does not trigger redundant invalidation

- GIVEN the bot wrote to guild G's config 2 seconds ago
- WHEN a CDC event fires for that guild
- THEN the event is found in the recent-writes set
- AND cache invalidation is skipped

#### Scenario: Dashboard write triggers invalidation

- GIVEN the dashboard updated guild G's config via Supabase
- WHEN a CDC event fires for that guild
- THEN the event is NOT found in the recent-writes set
- AND `cache.invalidate_guild(G)` is called

#### Scenario: Expired entry does not filter

- GIVEN a write entry expired (older than 5 seconds)
- WHEN a CDC event arrives for that row
- THEN the entry is not found in the set
- AND cache invalidation proceeds normally

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

(Previously: Watchdog counted only events that passed filtering and triggered cache invalidation)

### Requirement: Resilient close-logging wiring

The Realtime subscriber MUST gracefully handle missing private SDK attributes (e.g. `_on_connect_error`) during `_wire_close_logging`. Failure to wire close logging SHALL NOT abort subscriber startup — health check, poll fallback, and watchdog tasks MUST still be created. Close-logging failures MUST be logged at WARNING level.

(Previously: `_wire_close_logging` accessed `client._on_connect_error` directly; AttributeError aborted `start()` before health/poll/watchdog tasks were created)

#### Scenario: Close-logging skipped when SDK attribute missing

- GIVEN the `realtime-py` SDK version does not expose `_on_connect_error`
- WHEN `_wire_close_logging` runs during subscriber start
- THEN the method catches `AttributeError` and logs a WARNING
- AND the subscriber continues to start normally

#### Scenario: Health/poll/watchdog tasks start despite close-logging failure

- GIVEN `_wire_close_logging` raises `AttributeError`
- WHEN the subscriber start sequence continues
- THEN the health check, poll fallback, and watchdog tasks are created and scheduled

#### Scenario: Close-logging works when SDK attribute present

- GIVEN the `realtime-py` SDK exposes `_on_connect_error`
- WHEN `_wire_close_logging` runs
- THEN the close-logging hook is wired normally (no exception thrown)

#### Scenario: Subscriber starts on bot startup

- GIVEN the bot is starting up
- WHEN `setup_hook` executes
- THEN a Supabase Realtime channel is created and subscribed to all 6 tables
- AND the subscription callback is registered
- AND health/poll/watchdog tasks are scheduled regardless of close-logging outcome

<!-- BEGIN DELTA: cleanup-stability (cache-sync-realtime) -->
<!-- Delta: cleanup-stability → cycle-5-quality-zero — deferred cache scope superseded: member/economy_config now covered -->

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

<!-- END DELTA: cleanup-stability (cache-sync-realtime) -->
