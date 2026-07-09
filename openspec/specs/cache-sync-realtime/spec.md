# Cache Sync Realtime Specification

## Purpose

Replace inbound webhook (Cloudflare Tunnel + HMAC) with outbound Supabase Realtime CDC for cache invalidation. Same invalidation semantics, zero public exposure.

## Requirements

### Requirement: Realtime subscriber lifecycle

The bot SHALL connect to Supabase Realtime via `acreate_client` (async) on startup and subscribe to INSERT/UPDATE/DELETE events on `guild`, `greeting_config`, `ticket`, and `ticket_note` tables. The subscriber MUST start in `setup_hook` and stop on `cog_unload` or shutdown. Connection status MUST be tracked via the `on_subscribe(status, err)` callback using `RealtimeSubscribeStates`.

#### Scenario: Subscriber starts on bot startup

- GIVEN the bot is starting up
- WHEN `setup_hook` executes
- THEN a Supabase Realtime channel is created and subscribed to all 4 tables
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

When the WebSocket is down, the bot MUST poll Supabase every 30 seconds to detect changes. The `ticket` table has a `lastActivity` (timestamptz) column suitable for incremental queries. Config tables (`guild`, `greeting_config`) lack `updated_at` columns; the poll SHALL query all guild IDs from `guild` and invalidate their caches.

#### Scenario: Poll detects recent ticket activity

- GIVEN the poll fallback is active
- WHEN the poll queries `SELECT "guildId" FROM ticket WHERE "lastActivity" > $last_check`
- THEN `cache.invalidate_guild()` is called for each returned guild_id
- AND `last_check` is updated to the current timestamp

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

Before the subscriber can receive events, the migration `ALTER PUBLICATION supabase_realtime ADD TABLE guild, greeting_config, ticket, ticket_note;` MUST be applied. The watchdog MUST count RECEIVED events (incremented at the top of `_handle_cdc` before any filtering), not PROCESSED events. If no CDC events are received within 30 seconds of `SUBSCRIBED`, log a warning. The migration is idempotent.

#### Scenario: Migration applied — events received

- GIVEN the migration has been applied
- WHEN the bot subscribes and a dashboard write occurs
- THEN CDC events are received within 5 seconds
- AND the watchdog counter increments even if the event is later skipped

#### Scenario: Migration not applied — warning logged

- GIVEN the migration has NOT been applied
- WHEN 30 seconds pass after `SUBSCRIBED` with zero events
- THEN a warning is logged about missing publication

#### Scenario: Watchdog counts skipped events

- GIVEN a CDC event arrives but is filtered (self-echo, no guild_id)
- WHEN processed
- THEN the watchdog counter still increments
- AND no migration warning is logged

#### Scenario: Idempotent migration safe to re-run

- GIVEN the migration was already applied
- WHEN the migration SQL is executed again
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
- THEN a Supabase Realtime channel is created and subscribed to all 4 tables
- AND the subscription callback is registered
- AND health/poll/watchdog tasks are scheduled regardless of close-logging outcome
