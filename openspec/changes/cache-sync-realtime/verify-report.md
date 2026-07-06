## Verification Report

**Change**: cache-sync-realtime PR 1 (post-fix re-verify)  
**Branch**: cache-sync-realtime-pr1  
**Base**: 66397d4  
**Mode**: Strict TDD  
**Verdict**: FAIL

This post-fix re-verification confirms CRITICAL #1 is resolved: `_on_subscribe` is now a synchronous callback, matching Supabase Python's callback contract. CRITICAL #2 is only partially resolved: `_last_check` now resets on `SUBSCRIBED`, but the poll loop task is still not stopped/cancelled on recovery, despite the spec requiring the poll loop to stop. Runtime tests, coverage, lint, Context7 evidence, local SDK source inspection, and Supabase publication state were checked.

---

### External API / MCP Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| Context7 Supabase Python Realtime docs | ✅ Passed | `/supabase/supabase` docs show Python `def on_subscribe(status, err): ... asyncio.create_task(...)` followed by `await my_channel.subscribe(on_subscribe)`, confirming async work should be scheduled from a sync callback. |
| Local installed SDK source sanity check | ✅ Passed | `uv run python` inspection of `AsyncRealtimeChannel.subscribe` shows signature `callback: Optional[Callable[[RealtimeSubscribeStates, Optional[Exception]], None]]` and direct calls like `callback(RealtimeSubscribeStates.SUBSCRIBED, None)` with no await. |
| Supabase publication status | ✅ Passed | Supabase MCP SQL against project `vozkcckiybebhcclrasa` returned `public.greeting_config`, `public.guild`, `public.ticket`, `public.ticket_note` in `supabase_realtime`. |

---

### Completeness

| Metric | Value |
|--------|-------|
| PR 1 phases in scope | Phases 1-4 |
| PR 1 tasks total | 18 |
| PR 1 tasks checked complete | 18 |
| PR 1 tasks incomplete | 0 |
| PR 2 phases | Phases 5-8 remain unchecked as expected |

Phase 1-4 task boxes are `[x]` in `openspec/changes/cache-sync-realtime/tasks.md`. Phase 5-8 boxes are `[ ]`, matching the PR 1 boundary and intentionally not verified as implementation scope.

---

### Build & Tests Execution

| Command | Result | Evidence |
|---------|--------|----------|
| `uv run pytest --cov-fail-under=70` | ✅ Passed | 615 passed in 8.27s; total coverage 79.10%; required 70% reached. |
| `uv run pytest tests/test_realtime.py -v --no-cov` | ✅ Passed | 67 passed in 0.11s. |
| `uv run pytest tests/test_bot.py -v --no-cov` | ✅ Passed | 11 passed in 0.05s. |
| `uv run ruff check bot/core/realtime.py bot/core/database.py bot/bot.py tests/test_realtime.py tests/test_bot.py` | ✅ Passed | All checks passed. |
| Runtime poll-task sanity check | ❌ Blocking evidence | After `start()`, setting fallback active, then calling `_on_subscribe("SUBSCRIBED", None)`: `_poll_fallback_enabled=False`, `_last_check=epoch`, but `_poll_task.done()==False` and `_poll_task.cancelled()==False`. |

Changed-file coverage from the full run:

| File | Coverage | Rating |
|------|----------|--------|
| `bot/core/realtime.py` | 88% | ⚠️ Acceptable |
| `bot/bot.py` | 75% | ⚠️ Below strict changed-file 80% guidance |
| `bot/core/database.py` | 67% | ⚠️ Below strict changed-file 80% guidance; much of the file is pre-existing surface |

---

### Spec Compliance Matrix

| Requirement | Scenario / Claim | Runtime Test / Evidence | Result |
|-------------|------------------|-------------------------|--------|
| R1 Lifecycle | Subscriber starts and subscribes to 4 tables | `tests/test_realtime.py::TestSubscriberStart::*` passed; source registers `SUBSCRIBED_TABLES` at `bot/core/realtime.py:321-329`. | ✅ COMPLIANT |
| R1 Lifecycle | Subscriber stops and removes channels/client | `tests/test_realtime.py::TestSubscriberStop::*` passed; `stop()` cancels tasks and removes channels at `bot/core/realtime.py:345-368`. | ✅ COMPLIANT |
| R1 Lifecycle | Subscription status tracked via `on_subscribe(status, err)` | `_on_subscribe` is sync `def` at `bot/core/realtime.py:494`; tests verify sync/non-coroutine and status storage at `tests/test_realtime.py:531-557`. | ✅ COMPLIANT |
| R2 CDC invalidation | `guild`, `greeting_config`, `ticket` invalidate guild cache | `TestCdcDispatch::test_dispatch_invalidates_correct_guild[...]` passed; extraction source at `bot/core/realtime.py:77-94`. | ✅ COMPLIANT |
| R2 CDC invalidation | `ticket_note` resolves guild via cache/DB | `test_ticket_note_resolves_via_ticket_cache` and `test_ticket_note_falls_back_to_db_query` passed; source at `bot/core/realtime.py:421-488`. | ✅ COMPLIANT |
| R2 CDC invalidation | DELETE uses `old_record` | `test_delete_event_uses_old_record` passed; source at `bot/core/realtime.py:64-74`. | ✅ COMPLIANT |
| R3 Reconnection / health | 60s health logging and fallback activation | `TestHealthCheck::*` passed; source at `bot/core/realtime.py:528-547`. | ✅ COMPLIANT |
| R3 Reconnection / health | Reconnection disables fallback | `_on_subscribe("SUBSCRIBED")` sets `_poll_fallback_enabled=False` at `bot/core/realtime.py:506-513`; tests passed. | ✅ COMPLIANT for fallback flag |
| R4 Poll fallback | Ticket `lastActivity` incremental query with ISO timestamp | `test_poll_invalidates_tickets_by_last_activity`, `test_poll_uses_iso_timestamp_not_monotonic` passed; source at `bot/core/realtime.py:553-584`. | ✅ COMPLIANT |
| R4 Poll fallback | Config tables full scan with `.select()` before execution | `test_poll_scans_all_guilds`, `test_poll_calls_select_on_config_tables` passed; source at `bot/core/realtime.py:576-582`. | ✅ COMPLIANT |
| R4 Poll fallback | Poll loop stops and `last_check` resets on WebSocket recovery | `_last_check` resets at `bot/core/realtime.py:511-513`, but `_poll_loop` remains an active infinite task at `bot/core/realtime.py:606-613`; `tests/test_realtime.py:716-727` asserts only flag/reset and does not prove the loop stops. | ❌ FAILING |
| R5 Self-echo filtering | Recent-writes set, ~5s TTL, skip own CDC echo | `TestRecentWriteSet::*`, `TestSelfEchoFiltering::*`, `TestTicketSelfEcho::*` passed; source at `bot/core/realtime.py:110-149` and `bot/core/realtime.py:433-448`. | ✅ COMPLIANT |
| R5 Self-echo filtering | Production write integration | `bot/bot.py:280-283` wires `Database._on_write`; write hooks exist at `bot/core/database.py:144-145`, `313-314`, `366-367`, `921-922`. | ⚠️ PARTIAL / non-blocking |
| R6 Migration prerequisite | 4 tables published | Supabase MCP SQL returned exactly `greeting_config`, `guild`, `ticket`, `ticket_note`. | ✅ COMPLIANT |
| R6 Migration prerequisite | 30s zero-event watchdog warning | `TestMigrationWatchdog::*` passed; source at `bot/core/realtime.py:619-633`. | ✅ COMPLIANT |

**Compliance summary**: 13 compliant, 1 partial/non-blocking, 1 failing.

---

### Correctness (Static Evidence)

| Area | Status | Notes |
|------|--------|-------|
| Supabase async client | ✅ Implemented | `create_realtime_client()` uses `acreate_client(..., AsyncClientOptions(schema="public"))` at `bot/core/database.py:23-37`. |
| Channel registration | ✅ Implemented | One `cache-sync` channel registers all 4 tables at `bot/core/realtime.py:319-329`. |
| Subscription status callback | ✅ Fixed | `_on_subscribe` is a regular `def` at `bot/core/realtime.py:494`; no async work is needed in the current callback body. |
| CDC callback handoff | ✅ Implemented | `_cdc_callback()` is sync and schedules `_handle_cdc()` with strong task references at `bot/core/realtime.py:398-410`. |
| DELETE fallback | ✅ Implemented | `_record_for_event()` uses `old_record` for `DELETE`. |
| Poll timestamp | ✅ Implemented | `_poll_once()` uses `datetime.now(UTC).isoformat()`, not monotonic time. |
| Poll query ordering | ✅ Implemented | Ticket/config queries call `.select()` before filters/execution. |
| Poll recovery reset | ⚠️ Partial | `_last_check` resets to epoch, but the existing poll loop task is not stopped/cancelled. |
| Error logging | ✅ Implemented | Error paths use `logger.exception()` / warnings, with intentional debug drop when no event loop exists during shutdown. |

---

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Separate async client only for Realtime | ✅ Yes | Sync `Database` remains for normal data access. |
| One channel with four Postgres handlers | ✅ Yes | `SUBSCRIBED_TABLES` registers `guild`, `greeting_config`, `ticket`, `ticket_note`. |
| Sync callbacks schedule async work | ✅ Yes | CDC callback schedules async handler; subscribe callback is sync and performs only non-blocking status updates/logging. |
| 60s health and >60s poll fallback | ✅ Mostly | Logic exists and tests pass. |
| Poll fallback starts only when unhealthy; stops and resets on recovery | ❌ No | `_poll_task` is created at startup (`bot/core/realtime.py:332`) and `_poll_loop` remains alive forever until `stop()` (`bot/core/realtime.py:606-613`). Recovery only flips `_poll_fallback_enabled` and resets `_last_check`. |
| Self-echo in-memory TTL dict | ✅ Yes | `RecentWriteSet` implements lock-guarded TTL with lazy eviction. |

---

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Apply-progress memory #656 contains a TDD Cycle Evidence table. |
| All PR 1 tasks have tests | ✅ | `tests/test_realtime.py` and `tests/test_bot.py` cover lifecycle, CDC, self-echo, health, poll, watchdog, and wiring. |
| RED confirmed (test files exist) | ✅ | Reported files exist. Historical RED execution cannot be re-run from current green state. |
| GREEN confirmed | ✅ | Full suite and targeted suites pass now. |
| Triangulation adequate | ⚠️ | The sync subscribe regression was added, but poll recovery testing is incomplete: `test_poll_stops_on_recovery` does not assert `_poll_task.done()` or cancellation. |
| Safety net for modified files | ✅ | Full test suite passed. |

**TDD Compliance**: 5/6 checks passed; one warning for incomplete poll-loop stop assertion.

---

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit / component-boundary | 67 | `tests/test_realtime.py` | pytest, pytest-asyncio, unittest.mock |
| Bot lifecycle unit | 11 | `tests/test_bot.py` | pytest, pytest-asyncio, unittest.mock |
| Integration | Existing suite only | `tests/integration/*` | pytest |
| E2E | 0 | 0 | Not applicable |

---

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `bot/core/realtime.py` | 88% | n/a | coverage report did not include line ranges | ⚠️ Acceptable |
| `bot/bot.py` | 75% | n/a | coverage report did not include line ranges | ⚠️ Low for changed-file guidance |
| `bot/core/database.py` | 67% | n/a | coverage report did not include line ranges | ⚠️ Low; largely pre-existing file surface |

**Average changed file coverage**: ~76.7%.

---

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|------|------|-----------|-------|----------|
| `tests/test_realtime.py` | 716-727 | `test_poll_stops_on_recovery` asserts only `_poll_fallback_enabled is False` and `_last_check == epoch` | Test name/spec says poll stops, but it does not assert the poll task stopped/cancelled. This allowed the remaining R4 failure through. | WARNING |

**Assertion quality**: 0 CRITICAL, 1 WARNING.

---

### Quality Metrics

**Linter**: ✅ No errors (`ruff check` passed).  
**Type Checker**: ➖ Not run; no explicit type-check command was required/provided for this verify slice.

---

### AGENTS.md Compliance

| Rule Area | Result | Evidence |
|-----------|--------|----------|
| No `print()` runtime output | ✅ | `grep` found no Python `print(` matches. |
| No bare `except:` | ✅ | `grep` found only a docstring mention in `tests/test_tickets_cog.py`, not executable code. |
| Type hints on public functions/classes | ✅ | New public functions/classes have annotations. |
| Async/await usage | ✅ | Async operations are awaited; sync SDK callbacks hand off/schedule async work where needed. |
| Logging for errors | ✅ | Realtime/database/bot errors use logging. |
| Error embed usage | ✅ | Existing command error handlers use `error_embed()` at `bot/bot.py:394` and `bot/bot.py:426`. |
| Tests mock external APIs | ✅ | Discord/Supabase interactions are mocked in PR 1 tests. |

---

### PR 1 Boundary Check

| Boundary Item | Result | Evidence |
|---------------|--------|----------|
| Webhook code not removed | ✅ | `bot/webhook/auth.py`, `models.py`, `server.py`, `__init__.py` still exist. |
| Dashboard cleanup not done | ✅ | `dashboard/lib/webhook-sync.ts` still exists. |
| `app.py` not simplified | ✅ | PR 2 cleanup was not performed. |
| Webhook config fields not removed | ✅ | Existing webhook config/tests remain. |
| Diff limited to PR 1 + OpenSpec artifacts | ✅ | `git diff --name-status 66397d4...HEAD` lists only `bot/bot.py`, `bot/core/database.py`, `bot/core/realtime.py`, `tests/test_bot.py`, `tests/test_realtime.py`, and OpenSpec artifacts. |

---

### Prior FAIL Report Re-check

| Prior item | Current state | Verdict |
|------------|---------------|---------|
| CRITICAL 1: `_on_subscribe` was async but SDK invokes sync callback | Fixed. Source is sync `def`; Context7 and local SDK source confirm sync callback contract; tests verify non-coroutine callback. | ✅ RESOLVED |
| CRITICAL 2: poll recovery did not reset `_last_check` and did not stop/cancel poll loop | Partially fixed. `_last_check` resets, but the poll task remains alive and is not stopped/cancelled on recovery. | ❌ STILL BLOCKING |
| WARNING: self-echo production wiring partial/non-uniform | Still valid, non-blocking. Hooks cover `guild`, `greeting_config`, `ticket`, `ticket_note`; other writes are unmarked but invalidation is idempotent. | ⚠️ STILL VALID |
| WARNING: changed-file coverage below 80% for bot/database | Still valid. `bot.py` 75%, `database.py` 67%. | ⚠️ STILL VALID |
| WARNING: no live CDC event generated | Still valid. Publication checked via MCP; no live dashboard write was generated. | ⚠️ STILL VALID |
| SUGGESTION: regression test for sync subscribe callback | Added at `tests/test_realtime.py:534-542`; adequate. | ✅ RESOLVED |
| SUGGESTION: poll recovery reset test | Added at `tests/test_realtime.py:569-577` and `716-727`, but it does not assert loop stop/cancel. | ⚠️ PARTIAL |

---

### Issues Found

**CRITICAL**

1. `bot/core/realtime.py:606-613` keeps `_poll_loop` running as an infinite background task; recovery in `_on_subscribe("SUBSCRIBED")` at `bot/core/realtime.py:506-513` only sets `_poll_fallback_enabled=False` and resets `_last_check`. The spec requires “the poll loop stops and `last_check` is reset” (`spec.md:106-110`), and the prior blocking issue explicitly required the poll loop to deactivate properly, not merely skip work behind a flag. A runtime sanity check confirmed `_poll_task.done()==False` and `_poll_task.cancelled()==False` after recovery.

**WARNING**

1. `tests/test_realtime.py:716-727` is named `test_poll_stops_on_recovery`, but it does not assert that `_poll_task` stops/cancels. It only asserts fallback flag false and `_last_check` reset, so it does not cover the failing spec clause.
2. Self-echo production wiring is partial/non-uniform. `Database._on_write` is wired for `upsert_guild`, `upsert_greeting_config`, `insert_ticket`, and `insert_ticket_note`, but other write/update/delete methods do not mark recent writes. This is non-blocking because redundant invalidation is idempotent.
3. Changed-file coverage remains below the strict changed-file 80% guidance for `bot/bot.py` (75%) and `bot/core/database.py` (67%), though project coverage exceeds the configured 70% gate.
4. No live CDC event was generated during verification; R6 migration publication state was verified through Supabase MCP and watchdog behavior through unit tests.

**SUGGESTION**

1. Add/repair a regression test that starts the subscriber, enables fallback, simulates `SUBSCRIBED`, and asserts the poll-loop task is stopped/cancelled or otherwise replaced by an explicit inactive task state that satisfies the spec.

---

### Final Verdict

**FAIL** — The sync subscription callback bug is fixed and all required test/lint commands pass, but PR 1 still fails the R4 poll recovery scenario because the poll loop task does not stop/cancel on WebSocket recovery. Do not proceed to PR 2 until this blocking spec mismatch is resolved or the spec/design is explicitly amended to allow a permanently running dormant poll task.
