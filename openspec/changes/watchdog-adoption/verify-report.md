```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:6956d3febec9b6bdaa8720b5251c2ebf3648e480a18092300df42e1c5d33c61d
verdict: fail
blockers: 2
critical_findings: 2
requirements: 5/5
scenarios: 11/11
test_command: uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42
test_exit_code: 0
test_output_hash: sha256:dffb6fe04b894e35331f0f5f4334e3024c5b0b2dbd59479d7e927613afd2b3a2
build_command: uv run ty check && uv run ruff check . && uv run ruff format --check . && uv run vulture bot/ --min-confidence 80
build_exit_code: 0
build_output_hash: sha256:cf3e09e9dc1118890ad8af904319979ef76aaa932980e0941a96dfad1dff0784
```

## Verification Report

**Change**: watchdog-adoption (S1 + remediate-2)
**Version**: N/A
**Mode**: Strict TDD
**Revision**: 2 — re-verification after remediate-2; supersedes the admitted v1 FAIL at `sha256:3efef4dee574eb6013f01fb100f4c50dcef12badd5446b8939a9c2c6245dc7fa`
**Evidence HEAD**: `2046358eff2b49679a7a7455a726667953e54c85`
**Base**: `master` at `8a91261c31c29a513f3fdb33f4cd1099d0da5197`

### Completeness

| Metric | Value |
|---|---:|
| Requirements total | 5 |
| Requirements complete | 5 |
| Scenarios total | 11 |
| Scenarios compliant | 11 |
| Tasks total | 5 |
| Tasks complete | 5 |
| Tasks incomplete | 0 |

All five task checkboxes are complete in the authoritative OpenSpec `tasks.md`. Full verification proceeded.

### Build & Tests Execution

| Gate | Exit | Result | Output hash |
|---|---:|---|---|
| `uv run pytest -q --no-cov -p randomly --randomly-seed=8675309` | 0 | 2953 passed, 19 skipped, 19 warnings | `sha256:7b03a8e61447ea4b8448c751b695e12693d0d960769bb35f6ea7dfd7d2f46dee` |
| `uv run pytest -q --no-cov -p randomly --randomly-seed=1234` | 0 | 2953 passed, 19 skipped, 19 warnings | `sha256:87c5c732edfc1ffba13d96bd3644f6090ffeef6e8c548586f3b134f535665fa0` |
| `uv run pytest -q --no-cov -p randomly --randomly-seed=777777` | 0 | 2953 passed, 19 skipped, 19 warnings | `sha256:fce47a30443b24accf0fac3cfd88b5a794819abdbf4093528fbc23bf7b729233` |
| `uv run pytest -q --no-cov -p randomly --randomly-seed=31337` | 0 | 2953 passed, 19 skipped, 19 warnings | `sha256:f57293603e00fd3eacbe7aaf1e5d3ad40688a5ceb289ddf9ce513157c39cd13a` |
| `uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42` | 0 | 2953 passed, 19 skipped, 19 warnings; 80.53% | `sha256:dffb6fe04b894e35331f0f5f4334e3024c5b0b2dbd59479d7e927613afd2b3a2` |
| `uv run pytest --no-cov tests/test_watchdog_adoption.py tests/test_ops_observability.py::TestLoopErrorRouting -vv` | 0 | 16 passed | `sha256:e9827de5a69ddc899b6f75395e0c39b34c387d235bf65d185719afd8a4c1270c` |
| `uv run pytest --collect-only -q --no-cov` | 0 | 2972 collected | `sha256:2d28e1ccc8fce3c0d64521b9661316ed92ac977b0ad2516355a3a613123f44f2` |
| Seven-file KEEP suite (`--no-cov -q`) | 0 | 59 passed, zero warnings | `sha256:f1748c461ec77443e37d881957812568cfc03a4ec69531526a605a88c6ee82f2` |

The order-dependent runtime defect is resolved: seed `8675309`, which reproduced all nine v1 failures, now passes, as do seeds `1234`, `777777`, and fresh seed `31337`.

**Coverage**: 80.53% / configured threshold 80.00% / spec floor 80.50% → ✅ above both thresholds.

#### Quality/build gates

| Gate | Exit | Result |
|---|---:|---|
| `uv run ty check` | 0 | All checks passed |
| `uv run ruff check .` | 0 | All checks passed |
| `uv run ruff format --check .` | 0 | 989 files already formatted |
| `uv run vulture bot/ --min-confidence 80` | 0 | No findings |

Combined build output hash: `sha256:cf3e09e9dc1118890ad8af904319979ef76aaa932980e0941a96dfad1dff0784`.

### Spec Compliance Matrix

| Requirement | Scenario | Runtime/source evidence | Result |
|---|---|---|---|
| Watchdog adoption invariant | Five census loops wired | Focused run passed `test_guard_requires_register_and_heartbeat` and all five heartbeat-per-tick tests; exact current literals are listed below | ✅ COMPLIANT |
| Watchdog adoption invariant | Preserves `Loop._error` logging | `TestLoopErrorRouting::test_raised_loop_body_is_logged` passed in the focused run; no loop-body exception wrapper was added | ✅ COMPLIANT |
| Watchdog adoption invariant | AST guard blocks future loops | `test_guard_requires_register_and_heartbeat`, `test_self_test_detector_flags_missing_pair`, and `test_watchdog_and_realtime_excluded` passed | ✅ COMPLIANT |
| Dead-loop activation | Resource loop running after cog load | `test_resource_log_loop_running_after_cog_load` passed; `CoreCog.cog_load` starts then registers in one gate | ✅ COMPLIANT |
| Load-order safety | Watchdog absent path safe | `test_watchdog_absent_is_safe_noop` passed and proved business logic completes with `get_cog` returning `None` | ✅ COMPLIANT |
| Load-order safety | Watchdog present path registers | Helper/order/registration tests and `test_check_once_warning_at_2x` passed | ✅ COMPLIANT |
| Gated-loop semantics | Gated-off produces no warnings | `test_gated_off_no_register_for_scheduled_close` passed; unregistered loops are absent from `_check_once` candidates | ✅ COMPLIANT |
| Gated-loop semantics | Gated-on registers normally | `test_gated_on_registers_scheduled_close` and `test_check_once_warning_at_2x` passed | ✅ COMPLIANT |
| Guard and KEEP | KEEP byte-identical | Current and `master` SHA256 are both `7113667034365c6bca9b4b94dcf7543a404fb8ab15829b4a32f2a2e029b75cfb`; all seven KEEP files passed (59 tests) | ✅ COMPLIANT |
| Guard and KEEP | Adoption guard green and exercisable | Guard/self-test passed and `test_check_once_warning_at_2x` captured a WARNING containing `resource_log_loop` | ✅ COMPLIANT |
| Guard and KEEP | Coverage gate holds | Seed-42 coverage is 80.53%; all four independent randomized orders pass 2953/19 | ✅ COMPLIANT |
| Re-verification acceptance (non-counted) | Remediate-2 isolation | Four full-suite seeds, including former failing seed `8675309`, pass after removing `sys.modules` eviction from `test_dynamic_discovery_order_resilience` | ✅ RESOLVED |

**Compliance summary**: 11/11 spec scenarios compliant; 5/5 requirements complete. The non-counted remediation acceptance check also passes.

### Exact Wiring Evidence

| Loop | Register literal | Heartbeat literal | Ordering |
|---|---|---|---|
| `resource_log_loop` | `bot/cogs/core.py:128` — `wd.register("resource_log_loop", 300)` | `bot/cogs/core.py:145` — `wd.heartbeat("resource_log_loop")` | Before `_log_resource_usage()` |
| `decay_expiry_loop` | `bot/cogs/sentinel.py:95` — `wd.register("decay_expiry_loop", 3600)` | `bot/cogs/sentinel.py:177` — `wd.heartbeat("decay_expiry_loop")` | Before DB/service guards and guild iteration |
| `scheduled_close_loop` | `bot/cogs/tickets.py:116` — `wd.register("scheduled_close_loop", 60)` | `bot/cogs/tickets.py:122` — `wd.heartbeat("scheduled_close_loop")` | Before ticket polling; registration shares `TICKET_TIMER_ENABLED` gate |
| `auto_close_stale_tickets` | `bot/cogs/tickets.py:104` — `wd.register("auto_close_stale_tickets", 3600)` | `bot/cogs/tickets.py:204` — `wd.heartbeat("auto_close_stale_tickets")` | Before logging and service work |
| `integrity_sweep_loop` | `bot/cogs/tickets.py:110` — `wd.register("integrity_sweep_loop", 3600)` | `bot/cogs/tickets.py:243` — `wd.heartbeat("integrity_sweep_loop")` | Before logging and integrity work |

`bot/cogs/watchdog.py` changes only add module helper `get_watchdog`; existing `WatchdogCog.register`, `heartbeat`, `_check_once`, `_check`, lifecycle, and setup bodies are byte-identical to `master` in the diff.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Watchdog adoption invariant | ✅ Implemented | Five production loops use exact interval registration and top-of-body heartbeat; watchdog `_check` remains excluded. |
| Dead-loop activation | ✅ Implemented | `CoreCog.cog_load` starts and registers `resource_log_loop`; unload cancellation remains intact. |
| Load-order safety | ✅ Implemented | `get_watchdog` is absent-safe and `EXTENSIONS[0]` is `bot.cogs.watchdog` at `bot/bot.py:54`. |
| Gated-loop semantics | ✅ Implemented | `scheduled_close_loop.start()` and registration share the line-111 `TICKET_TIMER_ENABLED` condition. |
| Guard and KEEP | ✅ Implemented | Guard, KEEP, coverage, randomized suites, type, lint, format, and dead-code gates pass. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — helper plus `EXTENSIONS[0]` | ✅ Yes | Both mechanisms are present and runtime-tested. |
| D2 — inline literal wiring | ✅ Yes | Five literal pairs use `wd = get_watchdog(...)` and `if wd:`. |
| D3 — AST guard | ✅ Yes | AST scan excludes watchdog/realtime and has a synthetic missing-pair self-test. |
| D4 — unit and preserved error-routing tests | ✅ Yes | 15 adoption tests and the preserved `Loop._error` test pass. |
| D5 — coverage plan | ✅ Yes | Overall coverage is 80.53% and all added executable production lines are covered. |
| D6 — revert-only rollback, no DDL | ✅ Yes | No migration or SQL path changed; watchdog remains logging-only. |

### TDD Compliance

The implementation lineage remains RED `a2c88b5` (15 adoption tests, 11 failures before wiring) → GREEN `7bc11fa` → style `b83ad7f` → task/report commit `5637825` → remediate-2 `2046358`. Engram #5016 records both the original RED→GREEN cycle and the nine-failure isolation reproduction.

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Engram #5016 contains task-level RED/GREEN evidence and remediate-2 reproduction. |
| All tasks have tests | ✅ | 5/5 task rows map to adoption tests or full gates. |
| RED confirmed (tests exist) | ✅ | `tests/test_watchdog_adoption.py` exists with 15 tests; RED commit `a2c88b5` preceded production wiring. |
| GREEN confirmed (tests pass) | ✅ | All 15 adoption tests and preserved error-routing test pass now. |
| Triangulation adequate | ✅ | Absent/present, gated off/on, five loops, warning threshold, and guard self-test are distinct cases. |
| Safety net for modified files | ✅ | Four randomized full suites and seed-42 coverage pass at HEAD. |

**TDD lifecycle evidence**: 6/6 checks passed. **Strict TDD overall**: ❌ FAIL because the mandatory assertion-quality audit found a new tautological assertion in remediate-2.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 15 | 1 | pytest, pytest-asyncio, `unittest.mock` |
| Documentation integration | 12 | 1 | pytest, runtime cog discovery |
| Framework integration (preserved) | 1 | 1 | discord.py `tasks.loop`, pytest |
| E2E | 0 | 0 | Not available |
| **Total relevant tests** | **28** | **3** | |

### Changed File Coverage

Coverage is from the passing seed-42 full suite. Branch coverage is not configured.

| File | Line % | Branch % | Uncovered lines | Rating |
|---|---:|---:|---|---|
| `bot/bot.py` | 78% | N/A | 216, 224, 260-261, 306, 323-324, 337-338, 361-362, 366-385, 400, 413-415, 420, 424, 426-427, 454-469, 498-511, 555-556, 567-568, 583, 645-654, 663-664, 672-673, 726, 749-755, 762-763, 773-777, 784, 815-821 | ⚠️ Low |
| `bot/cogs/core.py` | 55% | N/A | 32, 36-42, 72-79, 82-96, 99-105, 150, 205, 211, 231-245, 269-281, 300-309, 344-399, 409, 414, 456-457, 465-468, 472-475, 477-478 | ⚠️ Low |
| `bot/cogs/sentinel.py` | 71% | N/A | 79-80, 102-104, 108-112, 133, 139-140, 145, 148, 156-158, 163-164, 179, 185-186, 201-202, 219-220, 272-273, 302-303, 331, 338-339, 348-356, 359-360, 363-364, 415, 421-422, 425-433, 445-446, 448-449, 502, 516-518, 524-525, 533-534, 537-538, 540-541, 582, 588-590, 593-594, 596-597, 634, 644-646, 651-652, 660-661, 664-665, 667-668, 748, 761-763, 768-769, 777-778, 781-782, 784-785, 866, 877-893, 896-897, 899-900, 942, 953-969, 972-973, 975-976, 1029-1030, 1038-1047, 1068, 1105, 1131-1133, 1135-1136, 1141-1142, 1145-1146, 1148-1149, 1216, 1218-1219, 1222-1231, 1250-1260, 1263-1264, 1266-1267, 1277-1278, 1295, 1300, 1353 | ⚠️ Low |
| `bot/cogs/tickets.py` | 84% | N/A | 80, 130-132, 136-137, 149, 153, 156-157, 185-186, 188-193, 195-196, 208-209, 211-212, 217-219, 224-225, 228-229, 246-247, 269-270, 276-277, 280, 290, 293, 323, 326-328, 359-361, 370-371, 385-386, 405, 412-414, 418-419, 439-440, 737, 741 | ⚠️ Acceptable |
| `bot/cogs/watchdog.py` | 85% | N/A | 55, 63-64, 68, 72, 80 | ⚠️ Acceptable |

**Weighted changed-production-file coverage**: 73% (1186/1621 statements). All executable production lines added by this change are covered; below-80 whole-file percentages are inherited strict-TDD warnings.

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|---|---:|---|---|---|
| `tests/test_manual.py` | 339 | `assert shuffled != baseline or len(baseline) <= 1 or baseline == sorted(baseline) or True` | The explicit `or True` makes the assertion unconditional; it was added by remediate-2 and proves nothing. Shuffling an already discovered result also does not exercise cog import order. | CRITICAL |

`tests/test_watchdog_adoption.py` contains no tautology, ghost loop, assertion-free production path, orphan empty assertion, smoke-only test, or unpaired type-only assertion.

**Assertion quality**: 1 CRITICAL, 0 WARNING.

### Ledger Verification

Commit `2046358` contains the requested Ledger block, but one fresh measurement contradicts its line arithmetic.

| Ledger item | Commit body / expected | Fresh measurement | Result |
|---|---:|---:|---|
| Changed files | 1 (`tests/test_manual.py`) | 1 | ✅ Match |
| Tracked Python files under `tests/` | 181 | 181 | ✅ Match |
| `tests/` Python lines | 61,305 − 18 = 61,287 | 61,305 → **61,286** | ❌ Mismatch |
| `test_manual.py` diff | 15 insertions, 33 deletions, net −18 | `git show --numstat`: 18 insertions, 37 deletions, net −19 | ❌ Mismatch |
| Collected tests | 2972 | 2972 | ✅ Match |
| Passed/skipped | 2953 / 19 | 2953 / 19 on all required seeds | ✅ Match |
| Coverage | 80.53% | 80.53% | ✅ Match |
| Seeds | 42, 8675309, 1234, 777777 green | All green; fresh 31337 also green | ✅ Match |
| KEEP SHA256 | `71136670…` unchanged | Full SHA identical to `master` | ✅ Match |

The authoritative ledger command from the archived governance spec, `find tests -name '*.py' -exec wc -l {} +`, reports `61286 total`. Parent-tree measurement at `2046358^` reports `61305`, so the physical delta is −19, not −18.

### Remediation Traceability

| Stage | Evidence | Result |
|---|---|---|
| Verify v1 | `sha256:3efef4dee574eb6013f01fb100f4c50dcef12badd5446b8939a9c2c6245dc7fa`; seed 8675309 produced 9 failures | FAIL admitted |
| Root cause | `tests/test_manual.py` evicted `bot.cogs.*` from `sys.modules`, leaving stale imported cog objects; patches targeted a different `bot.cogs.tickets` module instance | Confirmed by remediate-2 history and diff |
| Remediate-2 | Commit `2046358`; provided remediation evidence `sha256:4e00ac92…`; replaces module eviction/re-import with deterministic double scan | Runtime defect resolved |
| Re-verify v2 | Evidence `sha256:6956d3febec9b6bdaa8720b5251c2ebf3648e480a18092300df42e1c5d33c61d`; four randomized suites green | Runtime acceptance passes; strict audit still blocks |

### Invariants

| Invariant | Evidence | Result |
|---|---|---|
| Zero hybrid command surface | Both repo-wide zero-hybrid guards passed; offender count is 0 | ✅ |
| Ticket comma trigger intact | `bot/cogs/tickets.py:279` still checks `content.startswith(",")`; all 3 comma invariant tests passed | ✅ |
| Seven KEEP files green | 59 passed, zero warnings | ✅ |
| `test_ops_observability.py` byte-identical | Current and `master` SHA256 both `7113667034365c6bca9b4b94dcf7543a404fb8ab15829b4a32f2a2e029b75cfb` | ✅ |
| Vulture zero | Exit 0, no findings | ✅ |
| No `WatchdogCog` API change | Diff adds only module helper `get_watchdog`; existing class methods and signatures are unchanged | ✅ |
| Loop error routing stable | Preserved focused test passed; no exception wrapper added | ✅ |
| Remediate-2 is tests-only | Commit `2046358` changes only `tests/test_manual.py` | ✅ |

### Quality Metrics

**Linter**: ✅ Ruff check passes with zero findings.
**Formatter**: ✅ Ruff format check reports 989 files already formatted.
**Type checker**: ✅ Ty passes with zero diagnostics.
**Dead code**: ✅ Vulture exits 0.
**Coverage**: ✅ Overall/spec floors pass; ⚠️ three changed production files remain below 80% whole-file coverage.

### Issues Found

**CRITICAL**

1. Remediate-2 adds an unconditional assertion at `tests/test_manual.py:339` (`... or True`). Strict TDD's mandatory assertion-quality audit classifies tautologies as CRITICAL, so verification cannot pass even though every runtime suite is green.
2. The remediate-2 Ledger cannot be confirmed: fresh physical line measurement is `61,305 → 61,286` (−19), and Git numstat is `18/37`, while the commit body records −18 and the mandate expects 61,287.

**WARNING**

1. Strict changed-file coverage remains below 80% for `bot/bot.py` (78%), `bot/cogs/core.py` (55%), and `bot/cogs/sentinel.py` (71%), although every executable line added by watchdog-adoption is covered and total coverage is 80.53%.

**SUGGESTION**: None.

### Verdict

**FAIL**

All 5 requirements, all 11 scenarios, four randomized orders, coverage, static gates, KEEP invariants, and the original nine-failure remediation pass. Archive admission remains blocked by the new strict-TDD tautology and the fresh ledger mismatch.
