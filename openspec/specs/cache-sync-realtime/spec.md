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

### Requirement: Reconnection and health check

supabase-py handles WebSocket reconnection internally. The bot SHALL check subscription status every 60 seconds and log the current state (`SUBSCRIBED`, `CHANNEL_ERROR`, or `TIMED_OUT`). If the status is not `SUBSCRIBED` for more than 60 seconds, the poll fallback MUST be enabled.

#### Scenario: Healthy subscription logged

- GIVEN the subscription status is `SUBSCRIBED`
- WHEN the 60-second health check runs
- THEN a debug log confirms the subscription is healthy

#### Scenario: Disconnected subscription triggers poll fallback

- GIVEN the subscription status is `CHANNEL_ERROR` or `TIMED_OUT`
- WHEN the status has been non-`SUBSCRIBED` for over 60 seconds
- THEN the poll fallback is activated
- AND a warning is logged

#### Scenario: Reconnection disables poll fallback

- GIVEN the poll fallback is active due to a disconnected WebSocket
- WHEN the subscription status returns to `SUBSCRIBED`
- THEN the poll fallback is deactivated

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

### Requirement: Migration prerequisite

Before the subscriber can receive events, the migration `ALTER PUBLICATION supabase_realtime ADD TABLE guild, greeting_config, ticket, ticket_note;` MUST be applied. On startup, if no CDC events are received within 30 seconds of a successful subscription, the bot SHOULD log a warning suggesting the migration may not have been applied. The migration is idempotent.

#### Scenario: Migration applied — events received

- GIVEN the migration has been applied
- WHEN the bot subscribes and a dashboard write occurs
- THEN CDC events are received within 5 seconds

#### Scenario: Migration not applied — warning logged

- GIVEN the migration has NOT been applied
- WHEN 30 seconds pass after `SUBSCRIBED` status with zero CDC events
- THEN a warning is logged: "No CDC events received — check that supabase_realtime publication includes the required tables"

#### Scenario: Idempotent migration safe to re-run

- GIVEN the migration was already applied
- WHEN the migration SQL is executed again
- THEN no error occurs (adding an already-published table is a no-op)
