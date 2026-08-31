# ops-observability Specification

## Purpose

Env-gated exception observability and stall watchdog with zero Discord mutations.

## Requirements

### Requirement: Sentry env-gated init [NET-NEW]

The system MUST init Sentry via `SENTRY_DSN` only when the env var is non-empty; when absent/empty the process MUST boot without error and emit no PII.

#### Scenario: DSN present captures

- GIVEN `SENTRY_DSN` is set to a valid DSN
- WHEN bot boots
- THEN `sentry_sdk.init(dsn)` is called and unhandled exceptions are captured

#### Scenario: DSN absent no-op

- GIVEN `SENTRY_DSN` is unset or empty
- WHEN bot boots
- THEN no Sentry init occurs and boot succeeds

#### Scenario: No PII sent

- GIVEN Sentry is enabled
- WHEN an exception with user content is captured
- THEN payload MUST NOT contain token, guild secrets, or raw message content

### Requirement: Watchdog observe+log only [NET-NEW]

The system MUST provide `bot/cogs/watchdog.py` (`WatchdogCog`) that detects stalled `tasks.loop` instances via `logging` at WARNING/ERROR only. It MUST NOT call kick/mute/move/DM/send or mutate Discord state (AGENTS.md listeners rule).

#### Scenario: Stall detected logs warning

- GIVEN a registered `tasks.loop` (e.g. `TicketsCog.scheduled_close_loop`, `integrity_sweep_loop`, `RealtimeCacheSubscriber._health_loop`) has not ticked within 2× its interval
- WHEN watchdog checks
- THEN it logs WARNING with loop name/guild scope and takes no Discord action

#### Scenario: No mutation from watchdog

- GIVEN watchdog is running
- WHEN any health check fires
- THEN no `discord.Member`/`Channel` mutation APIs are invoked (verify via mock — zero calls)

### Requirement: tasks.loop error routing stays on logging [PRESERVED]

The system MUST preserve that `tasks.loop` unhandled exceptions route via `logging` (verified: `discord.py Loop._error` at `tasks/__init__.py:415` does `_log.error(..., exc_info=exception)`; default `_call_loop_function('error')` on line 139-141 re-raises after `await _error`; no `print`/`sys.stderr` branch exists; bot's `bot/cogs/tickets.py` loops at `:108,187,223` already wrap per-guild/per-ticket bodies in `try/except` with `logger.exception`). The audit #4711 (2026-08-23, pre clean-1.0) claim that `tickets.py:217 RuntimeError` bypasses logging to `stderr` is NOT reproducible in current tree and MUST NOT be treated as net-new.

#### Scenario: Raised loop body is logged

- GIVEN a `tasks.loop` body raises `RuntimeError` (e.g. missing `ticket_service`)
- WHEN the exception propagates
- THEN `Loop._error` logs via `logging` at ERROR with exc_info — no stderr/print path

#### Scenario: No print/stderr usage

- GIVEN `bot/cogs/tickets.py` and `bot/bot.py` are scanned
- WHEN searching for `print(` or `sys.stderr`
- THEN zero runtime `print`/`stderr` calls exist for error paths (AGENTS.md)
