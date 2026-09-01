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

<!-- BEGIN DELTA: watchdog-adoption (ops-observability) -->
## ADDED Requirements

### Requirement: Watchdog adoption invariant — every production tasks.loop MUST register+heartbeat

The system MUST wire every production `@tasks.loop` in `bot/` except `bot/cogs/watchdog.py:57` (`_check` 30s) to `WatchdogCog.register` (`bot/cogs/watchdog.py:29`) and `heartbeat` (`bot/cogs/watchdog.py:35`). Register SHALL use the declared interval; heartbeat SHALL be top-of-body; wiring MUST preserve `Loop._error` logging semantics. Watchdog MUST detect stalls via `time.monotonic` at 2× interval via `_check_once` (`bot/cogs/watchdog.py:39`) and log WARNING only (observe-only).

#### Scenario: Five census loops wired

- GIVEN census `core.py:124` (resource_log_loop 5m), `sentinel.py:162` (decay_expiry_loop 1h started `:90`), `tickets.py:108` (scheduled_close_loop 60s), `:187` (auto_close_stale_tickets 1h), `:223` (integrity_sweep_loop 1h)
- WHEN each loop body executes
- THEN `register(name, interval_s)` and `heartbeat(name)` were called per tick

#### Scenario: Preserves Loop._error logging

- GIVEN any wired loop body raises `RuntimeError`
- WHEN exception propagates
- THEN `Loop._error` still logs via `logging` at ERROR with exc_info and `TestLoopErrorRouting` stays green

#### Scenario: AST guard blocks future loops

- GIVEN a new production `@tasks.loop` added under `bot/` outside `watchdog.py`
- WHEN `tests/test_watchdog_adoption.py` AST scan runs (mirror `test_zero_hybrid_guard.py`)
- THEN test FAILS unless paired `register`+`heartbeat`; `:57` and `realtime.py` raw `Task`s excluded

### Requirement: Dead-loop activation — resource_log_loop gains cog_load start

The system MUST start `CoreCog.resource_log_loop` (`bot/cogs/core.py:124`) via `cog_load` because registered-but-never-started would satisfy stall condition (`now - last > 2*interval` since `register` at `watchdog.py:33` seeds `monotonic`) and emit WARNING every `watchdog.py:57` (30s). Activation and registration MUST be atomic.

#### Scenario: Resource loop running after cog load

- GIVEN `CoreCog` loaded and `bot.wait_until_ready` done (`core.py:135-137` `before_loop`)
- WHEN `cog_load` completes
- THEN `resource_log_loop.is_running()` is True and `cog_unload` (`core.py:150-153`) still cancels

### Requirement: Load-order safety — registration MUST NOT crash when watchdog not yet loaded

The system MUST allow `register`/`heartbeat` from loop owners loaded before `WatchdogCog` without crash or `None` dereference. Heartbeat before watchdog loads SHALL be safe no-op or buffered then flushed. Cog behavior MUST be unchanged when watchdog absent. Mechanism left OPEN for design (`bot/bot.py:53-63` move `watchdog` to `EXTENSIONS[0]` OR `get_watchdog(bot)` no-op helper + lazy heartbeat) but invariant MUST hold regardless of `EXTENSIONS` order (watchdog 9th today, owners 1st-3rd) and `cog_load` sites (`sentinel.py:89-90`, `tickets.py:98-106`).

#### Scenario: Watchdog absent path safe

- GIVEN `WatchdogCog` not loaded (`bot.get_cog("Watchdog")` is None)
- WHEN wired loop body calls `heartbeat` top-of-body
- THEN no exception and business logic completes

#### Scenario: Watchdog present path registers

- GIVEN `WatchdogCog` loaded
- WHEN wired loop starts or heartbeats
- THEN loop registered with interval and `_check_once` can WARNING after 2× interval

### Requirement: Gated-loop semantics — TICKET_TIMER_ENABLED off MUST NOT register

The system MUST NOT register `TicketsCog.scheduled_close_loop` (`bot/cogs/tickets.py:108` gated `:104-105` `if TICKET_TIMER_ENABLED` from `bot/config.py:228`) when `TICKET_TIMER_ENABLED` is False. Never-started but registered loop would permanently satisfy `now - last > 2*60` and spam WARNINGs every `watchdog.py:57` (30s). Registration SHALL be conditional on the same gate as `start()`.

#### Scenario: Gated-off produces no warnings

- GIVEN `TICKET_TIMER_ENABLED` is False
- WHEN watchdog runs `_check_once` (`bot/cogs/watchdog.py:39`) repeatedly
- THEN no WARNING for `scheduled_close_loop`

#### Scenario: Gated-on registers normally

- GIVEN `TICKET_TIMER_ENABLED` is True and `scheduled_close_loop` running
- WHEN watchdog checks after 2×60s without heartbeat
- THEN it MAY log WARNING with loop name/interval and no Discord mutation

### Requirement: Guard and KEEP — ops-observability evidence preserved and extended

The system MUST keep `tests/test_ops_observability.py` byte-identical (live-spec evidence `ops-zero-lite`). New coverage MUST live in `tests/test_watchdog_adoption.py`. All gates MUST stay green: `seed42+random` deterministic, `ty`/`ruff`/`vulture` 0, coverage ≥80.50% (baseline `8a91261` 2938/19 80.50%) with ~40 new prod lines covered same commit.

#### Scenario: KEEP byte-identical

- GIVEN `tests/test_ops_observability.py` bytes
- WHEN compared to `ops-zero-lite` archived version
- THEN SHA256 identical

#### Scenario: Adoption guard green and exercisable

- GIVEN all five loops wired
- WHEN wired loop stalled beyond 2× interval
- THEN `tests/test_watchdog_adoption.py` (AST guard + `_check_once` injection) green and WARNING exercisable

#### Scenario: Coverage gate holds

- GIVEN adoption adds ~40 prod lines
- WHEN `uv run pytest --cov=bot` runs same commit
- THEN coverage ≥80.50% and no gate regresses

<!-- END DELTA: watchdog-adoption (ops-observability) -->
