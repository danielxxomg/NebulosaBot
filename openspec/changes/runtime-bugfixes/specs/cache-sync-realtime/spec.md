# Delta for Cache Sync Realtime

## ADDED Requirements

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

## MODIFIED Requirements

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
