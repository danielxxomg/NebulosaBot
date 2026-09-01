# Design: Watchdog Adoption — Wire 5 loops to WatchdogCog

## Technical Approach

Reuse `WatchdogCog.register:29`/`heartbeat:35` without API change. Wire 5 census loops (`core:124` 300s, `sentinel:162` 3600s, `tickets:108` 60s, `:187` 3600s, `:223` 3600s) via register in `cog_load` (after `start()`, same `TICKET_TIMER_ENABLED` gate) and heartbeat as first line of each loop body through a no-op `get_watchdog(bot)` helper. Move `bot.cogs.watchdog` to `EXTENSIONS[0]` (prod tick-zero coverage) plus helper (test isolation). AST guard (`tests/test_watchdog_adoption.py` mirroring `test_zero_hybrid_guard.py`) fails on new `@tasks.loop` without pair. Keep `tests/test_ops_observability.py` byte-identical.

## Architecture Decisions

### D1 — Load-order mechanism

| Option | Tradeoff | Decision |
|---|---|---|
| (a) `EXTENSIONS[0]` only | Tick-zero coverage; breaks isolated cog tests | Rejected |
| (b) `get_watchdog` no-op only | Test-safe; first tick unobserved | Rejected |
| (a)+(b) | 6-line helper +1 reorder; passes both orders | **Chosen** |

**Choice**: `EXTENSIONS[0]` in `bot/bot.py:53-63` + module helper `get_watchdog(bot)` in `bot/cogs/watchdog.py` (`bot.get_cog("Watchdog")|None`); heartbeat is no-op when `None`. Helper required regardless because unit tests construct cogs with `MagicMock` bot lacking Watchdog; reorder alone doesn't fix that.

### D2 — Wiring pattern

| Option | Tradeoff | Decision |
|---|---|---|
| Per-cog `_heartbeat(name)` | DRY; hides literal from guard | Rejected |
| Inline `wd=get_watchdog(...); if wd: wd.heartbeat("loop")` | Visible literal for guard | **Chosen** |

Register after `start()` inside same `is_running()` gate (atomic). Heartbeat first statement of loop body, before any business logic. Core: new `cog_load` (`start` then `register` 300s). Sentinel `:89-90`: register 3600s after `start()` in existing `hasattr`+`is_running` gate. Tickets `:98-106`: two ungated registers inside their gates, `scheduled_close_loop` register inside compound `and TICKET_TIMER_ENABLED` gate.

### D3 — AST guard design

| Option | Tradeoff | Decision |
|---|---|---|
| Regex scan | Fast; false positives | Rejected |
| AST walk + name-literal pairing | Precise; self-testable | **Chosen** |

Scan `bot/**/*.py` excluding `bot/cogs/watchdog.py` and `bot/core/realtime.py` (raw Tasks). For each `@tasks.loop` `FunctionDef`, require file contains both `register("name"` and `heartbeat("name"`. Self-test: parse synthetic loop lacking pair and assert detector fails — proves non-tautological. Mirrors `test_zero_hybrid_guard.py`.

### D4 — Test plan

| Layer | Cover | File |
|---|---|---|
| Unit | AST guard + self-test; absent/present paths; heartbeat per tick | `tests/test_watchdog_adoption.py` |
| Keep | `Loop._error` logging | `tests/test_ops_observability.py::TestLoopErrorRouting` |

`test_watchdog_adoption.py`: AST guard + self-test, wiring tests with `MagicMock` watchdog via `bot.get_cog` (heartbeat per direct body call), gated-off no-register, `resource_log_loop.is_running()` after `cog_load`, watchdog-absent safe path.

### D5 — Coverage plan

~40 new prod lines (`watchdog` helper 5 + `bot.py` 1 + `core` 7 + `sentinel` 4 + `tickets` 12 + 5 heartbeats 10). Each covered: helper/gates via `cog_load` tests, heartbeats via direct body calls with mocked watchdog, `caplog` WARNING on `_check_once` 2× interval, gated-off via `patch(TICKET_TIMER_ENABLED, False)`. Baseline 80.50% headroom 0.50pp held.

### D6 — Rollback

| Option | Tradeoff | Decision |
|---|---|---|
| Feature flag | Branch cost; observe-only | Rejected |
| `git revert` | Single revert; no DDL | **Chosen** |

Watchdog is logging-only (WARNING, no Discord mutation).

## Data Flow

```
cog_load ──start()──► Loop
    └─register(name,interval)──► WatchdogCog
Loop tick ──heartbeat(name)──► monotonic
_check (30s) ──_check_once──► 2×? ──WARNING──► logging only
```

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/cogs/watchdog.py` | Modify | Add `get_watchdog(bot)` helper |
| `bot/bot.py:53` | Modify | Move watchdog to `EXTENSIONS[0]` |
| `bot/cogs/core.py` | Modify | New `cog_load` start+register + heartbeat |
| `bot/cogs/sentinel.py` | Modify | Register+heartbeat for `decay_expiry_loop` |
| `bot/cogs/tickets.py` | Modify | 3 registers + 3 heartbeats (gated) |
| `tests/test_watchdog_adoption.py` | Create | AST guard + wiring tests |
| `tests/test_ops_observability.py` | Keep | Byte-identical |

## Interfaces / Contracts

```python
def get_watchdog(bot: NebulosaBot) -> WatchdogCog | None:
    return bot.get_cog("Watchdog")  # type: ignore[return-value]


wd = get_watchdog(self.bot)
if wd:
    wd.register("loop_name", interval_s)  # cog_load after start
    wd.heartbeat("loop_name")  # loop body first line
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | AST blocks unregistered loop | `ast.parse` + rglob |
| Unit | Absent safe, present registers, heartbeat per tick | `MagicMock` watchdog |
| Unit | Gated-off/on + WARNING at 2× | `patch` + `_check_once` caplog |
| Unit | Running after `cog_load` | `is_running`/`cancel` mocks |
| Keep | `Loop._error` logged | Existing `TestLoopErrorRouting` |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR, executable-file, or process-integration boundary.

## Migration / Rollout

No migration. Single slice ~280 ln, `git revert` rollback. Observe-only; no DDL.

## Open Questions

- [x] `core.py` has `cog_load`? **No** — only `cog_unload:150-153`; new `cog_load` before it mirrors `SentinelCog:81-91`. Verified 2026-08-31.
- [x] Sentinel ordering? Single loop `:162` started `:89-90`; register after `start()` in same gate preserves `before_loop`/`cog_unload`.
- [x] Tickets shape `:98-106`? Three `if not is_running()` gates; `scheduled_close_loop` compound `and TICKET_TIMER_ENABLED` — register inside that gate.
