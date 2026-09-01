# Tasks: Watchdog Adoption — Wire 5 loops to WatchdogCog

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~280 (40 prod + 240 test) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (S1 single slice, ~19% of 1500) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Wire 5 census loops to Watchdog + AST guard (S1 single slice) | PR 1 | `uv run pytest tests/test_watchdog_adoption.py tests/test_ops_observability.py -v` | `uv run pytest --cov=bot --random-order-seed=42` + `git diff master --stat -- bot/` non-empty | Revert `bot/cogs/watchdog.py`, `bot/bot.py`, `bot/cogs/core.py`, `bot/cogs/sentinel.py`, `bot/cogs/tickets.py`, `tests/test_watchdog_adoption.py` |

## Phase 1: RED — Guard + Wiring Tests (TDD)

- [ ] 1.1 Create `tests/test_watchdog_adoption.py` — AST guard scanning `bot/**/*.py` excl. `bot/cogs/watchdog.py`/`bot/core/realtime.py` requiring `register("name"`+`heartbeat("name"` per `@tasks.loop`, self-test with synthetic missing-pair loop asserting detector fails; plus wiring tests: heartbeat per tick via `MagicMock` watchdog, watchdog-absent safe (`get_cog` None → no exception), gated-off `patch(TICKET_TIMER_ENABLED, False)`→no register, gated-on→register, `resource_log_loop.is_running()` after `CoreCog.cog_load`, `_check_once` WARNING via `caplog` at 2× interval — run `uv run pytest tests/test_watchdog_adoption.py -v` → expect RED (wiring absent)

## Phase 2: GREEN — Wiring Production Loops (D1/D2)

- [ ] 2.1 Add `bot/cogs/watchdog.py:get_watchdog(bot)` helper (`return bot.get_cog("Watchdog")|None`) and move `bot.cogs.watchdog` to `EXTENSIONS[0]` in `bot/bot.py:53` (D1 load-order: helper + reorder)
- [ ] 2.2 Add `bot/cogs/core.py` `cog_load` (atomic `resource_log_loop.start()` then `get_watchdog(self.bot).register("resource_log_loop", 300)` inside `if not is_running()` gate) and heartbeat `wd=get_watchdog(self.bot); if wd: wd.heartbeat("resource_log_loop")` as first line of `resource_log_loop:124` body; mirror `bot/cogs/sentinel.py:89-90` — after `decay_expiry_loop.start()` add `register("decay_expiry_loop", 3600)` inside same `hasattr`+`is_running` gate and heartbeat top-of-body at `:162` (D2 inline pattern, preserves `Loop._error`)
- [ ] 2.3 Modify `bot/cogs/tickets.py:98-106` gates — add `register("auto_close_stale_tickets", 3600)` and `register("integrity_sweep_loop", 3600)` inside their ungated `if not is_running()` blocks, and `register("scheduled_close_loop", 60)` INSIDE compound `if not is_running() and TICKET_TIMER_ENABLED` gate; add 3 heartbeats top-of-body at `:108`, `:187`, `:223` via `get_watchdog` no-op guard

## Phase 3: Gate Verification

- [ ] 3.1 Verify gates: `uv run pytest --cov=bot --random-order --random-order-seed=42` suite green + cov ≥80.50% + `uv run ty check` 0 + `uv run ruff check .` 0 + `uv run vulture bot/ --min-confidence 80` 0 + `sha256sum tests/test_ops_observability.py` vs `master` byte-identical (KEEP) + `test_zero_hybrid_guard.py`/comma invariants green + `git diff master --stat -- bot/` EXPECTED non-empty (cite stat) + record ledger files/lines/collected/cov
