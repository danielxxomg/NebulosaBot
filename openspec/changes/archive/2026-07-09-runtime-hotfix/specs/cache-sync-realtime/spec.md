# Delta for Cache Sync Realtime

## ADDED Requirements

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
