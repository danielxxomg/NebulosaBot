# Proposal: watchdog-adoption

## Intent
Fix verify INFO "no loop registers with WatchdogCog — registry empty" (`8a91261`). Wire every prod `@tasks.loop` to `WatchdogCog` (register/heartbeat, 2×→WARNING) so stalls are watched. Add AST guard blocking future unregistered loops. No API change.

## Scope

### In Scope
- Register+heartbeat 5 prod loops via `watchdog.py:29,35`
- Fix load-order (`EXTENSIONS[0]` or no-op `get_watchdog`+lazy heartbeat)
- Guard `tests/test_watchdog_adoption.py` AST excl. `watchdog.py:57`
- KEEP `test_ops_observability.py` byte-identical

### Out of Scope
- API changes, DDL, dashboard, `,`-debounce
- `RealtimeCacheSubscriber` raw `Task`s (`realtime.py:396,709,798,829`) — not loops, deferred

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `ops-observability`: every prod loop MUST register+heartbeat; WARNING exercisable. Delta in change folder.

## Approach
Single slice ~280 ln vs 1500. Reuse `register` `:29-33` + `heartbeat` `:35-37`. Watchdog to `bot/bot.py:53 EXTENSIONS[0]` or no-op helper when `get_cog None`. Wire `core.py:124`, `sentinel.py:162`, `tickets.py:108,187,223`; `before_loop`/`cog_unload` unchanged.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/bot.py:53` | Modified | EXTENSIONS order / lookup |
| `core.py:124` | Modified | 5m — add missing `cog_load` start |
| `sentinel.py:162` | Modified | 1h |
| `tickets.py:108,187,223` | Modified | 60s+1h+1h |
| `test_watchdog_adoption.py` | New | AST guard |
| `test_ops_observability.py` | KEEP | byte-identical |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Timing HIGH — cog_load before watchdog | High | EXTENSIONS-first; lazy heartbeat |
| Heartbeat breaks Loop._error | Med | Top-of-body; keep TestLoopErrorRouting green |
| Cov 80.50% headroom 0.50pp | High | ~40 ln covered same commit |

## Rollback Plan
`git revert <sha>`; watchdog `:57` observe-only; no DDL.

## Dependencies
Baseline `8a91261` 2938/19 80.50% ty/ruff/vulture 0.

## Success Criteria
- [ ] 5 loops wired (census; `:57` excluded)
- [ ] WARNING exercisable via `_check_once:39`
- [ ] Guard green; new loop without pair fails
- [ ] KEEP green + gates seed42+random+ty/ruff/vulture0+cov≥80.50
- [ ] `bot/` diff expected

## Review Workload Forecast

| Slice | Forecast | vs1500 | Chained | Gates |
|-------|----------|--------|---------|-------|
| S1 | ~280 ln | 19% | No | seed42+random+ty0/ruff0/vulture0+cov≥80.50 |

Decision: No. Chained: No. 400-line risk: Low.

## Gates per Slice
Suite green + ty/ruff/vulture0 + cov≥80.50 + seed42 + KEEP + bot/ diff.

## Loop Census — `grep @tasks.loop bot/` 2026-08-31

| File:Line | Loop | Interval | start |
|-----------|------|----------|-------|
| `core.py:124` | resource_log_loop | 5m | MISSING* |
| `sentinel.py:162` | decay_expiry_loop | 1h | :90 |
| `tickets.py:108` | scheduled_close_loop | 60s | :105† |
| `tickets.py:187` | auto_close_stale_tickets | 1h | :99 |
| `tickets.py:223` | integrity_sweep_loop | 1h | :102 |
| `watchdog.py:57` | _check | 30s | EXCL |

*no start (dead). †gated `TICKET_TIMER_ENABLED`. `realtime.py:396` raw tasks not loops.
