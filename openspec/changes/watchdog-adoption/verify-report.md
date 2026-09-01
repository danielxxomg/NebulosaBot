```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:3efef4dee574eb6013f01fb100f4c50dcef12badd5446b8939a9c2c6245dc7fa
verdict: fail
blockers: 1
critical_findings: 2
requirements: 4/5
scenarios: 10/11
test_command: uv run pytest -q --randomly-seed=8675309
test_exit_code: 1
test_output_hash: sha256:b193ad7b7ea0fe6b23e353806484c9a9d144653d1bdcf0592134cf82e41fa7ec
build_command: uv run ty check && uv run ruff check . && uv run ruff format --check . && uv run vulture bot/ --min-confidence 80
build_exit_code: 0
build_output_hash: sha256:a681d4fb439d1beeba494284ce649b83b6044ba89f1f7eb1fd5f1279a69bffdc
```

## Verification Report

**Change**: watchdog-adoption (S1)
**Version**: N/A
**Mode**: Strict TDD
**Evidence HEAD**: `8d82073d7f4e3e70067fd9b169c2139b39decef4` (`ac7a3f0` amended lineage)
**Base**: `master` at `8a91261c31c29a513f3fdb33f4cd1099d0da5197`

### Completeness

| Metric | Value |
|---|---:|
| Requirements total | 5 |
| Requirements complete | 4 |
| Scenarios total | 11 |
| Scenarios compliant | 10 |
| Tasks total | 5 |
| Tasks complete | 5 |
| Tasks incomplete | 0 |

All five task checkboxes are complete in `tasks.md`. Full verification proceeded.

### Build & Tests Execution

| Gate | Exit | Result | Output hash |
|---|---:|---|---|
| `uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42` | 0 | 2953 passed, 19 skipped, 19 warnings; 80.58% | `sha256:428d4d7d2f1fd0444db918f30c45231b5509f20cf2e4b71d36da2bf604909a83` |
| `uv run pytest -q --randomly-seed=8675309` | 1 | **9 failed**, 2944 passed, 19 skipped; 80.55% | `sha256:b193ad7b7ea0fe6b23e353806484c9a9d144653d1bdcf0592134cf82e41fa7ec` |
| `uv run pytest --no-cov tests/test_watchdog_adoption.py tests/test_ops_observability.py::TestLoopErrorRouting -vv` | 0 | 16 passed | `sha256:e9827de5a69ddc899b6f75395e0c39b34c387d235bf65d185719afd8a4c1270c` |
| `uv run pytest --collect-only -q --no-cov` | 0 | 2972 collected | `sha256:36359d95ff5601e3c45b1cde25833a8ca4ea02e4e504ac96e3d444ce43ae13ec` |
| `uv run pytest --no-cov tests/test_ops_observability.py -q` | 0 | 13 passed | `sha256:9d33c8640dbbf31be16f695b885c13586520e5c5c5afe98b9fade87344640ab6` |
| `uv run pytest --no-cov tests/test_zero_hybrid_guard.py tests/test_comma_timer_invariant.py -q` | 0 | 5 passed | `sha256:d5ea3026d04f19f104863235b07ad89b777a6a3ce74e7188fce8732186d35d34` |

The requested seed-42 suite and coverage gate pass, but the independent alternate randomized order is red. The failing randomized run contains two ticket-panel patch-order failures and seven ticket timer/debounce fixture-order failures in `tests/test_tickets_cog.py`; therefore the claimed random-order gate is not reproducibly green.

**Coverage**: 80.58% / threshold 80.00% / spec floor 80.50% → ✅ above both thresholds on seed 42.

#### Quality/build gates

| Gate | Exit | Result | Output hash |
|---|---:|---|---|
| `uv run ty check` | 0 | All checks passed | `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff check .` | 0 | All checks passed | `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff format --check .` | 0 | 988 files already formatted | `sha256:2a31b861f353d42f14e50e34ae21ed01f792f7a58519d4fbebdb1f19675913b7` |
| `uv run vulture bot/ --min-confidence 80` | 0 | No findings | `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Spec Compliance Matrix

| Requirement | Scenario | Runtime/source evidence | Result |
|---|---|---|---|
| Watchdog adoption invariant | Five census loops wired | Passing `test_guard_requires_register_and_heartbeat` plus five passing heartbeat-per-tick tests; exact register/heartbeat literals listed below | ✅ COMPLIANT |
| Watchdog adoption invariant | Preserves `Loop._error` logging | `tests/test_ops_observability.py::TestLoopErrorRouting::test_raised_loop_body_is_logged` passed; production diff adds no loop-body `try/except` | ✅ COMPLIANT |
| Watchdog adoption invariant | AST guard blocks future loops | Passing `test_guard_requires_register_and_heartbeat`, `test_self_test_detector_flags_missing_pair`, and `test_watchdog_and_realtime_excluded` | ✅ COMPLIANT |
| Dead-loop activation | Resource loop running after cog load | Passing `test_resource_log_loop_running_after_cog_load`; `CoreCog.cog_load` starts then registers in one gate | ✅ COMPLIANT |
| Load-order safety | Watchdog absent path safe | Passing `test_watchdog_absent_is_safe_noop` proves business logic completes with `get_cog` returning `None` | ✅ COMPLIANT |
| Load-order safety | Watchdog present path registers | Passing `test_get_watchdog_helper_exists`, `test_extensions_order_watchdog_first`, registration tests, and `test_check_once_warning_at_2x` | ✅ COMPLIANT |
| Gated-loop semantics | Gated-off produces no warnings | Passing `test_gated_off_no_register_for_scheduled_close`; an unregistered loop is absent from `_check_once` warning candidates | ✅ COMPLIANT |
| Gated-loop semantics | Gated-on registers normally | Passing `test_gated_on_registers_scheduled_close` and `test_check_once_warning_at_2x` | ✅ COMPLIANT |
| Guard and KEEP | KEEP byte-identical | Current and `master` SHA256 both `7113667034365c6bca9b4b94dcf7543a404fb8ab15829b4a32f2a2e029b75cfb`; file excluded from `git diff master --name-only`; all 13 current KEEP tests pass | ✅ COMPLIANT |
| Guard and KEEP | Adoption guard green and exercisable | Guard/self-test pass and `test_check_once_warning_at_2x` captures a WARNING containing `resource_log_loop` | ✅ COMPLIANT |
| Guard and KEEP | Coverage gate holds | Seed-42 coverage is 80.58%, but the mandated alternate random order has 9 failures; the requirement says all gates must stay green | ❌ FAILING |

**Compliance summary**: 10/11 scenarios compliant; 4/5 requirements complete.

### Exact Wiring Evidence

| Loop | Register literal | Heartbeat literal | Ordering |
|---|---|---|---|
| `resource_log_loop` | `bot/cogs/core.py:128` — `wd.register("resource_log_loop", 300)` | `bot/cogs/core.py:145` — `wd.heartbeat("resource_log_loop")` | First executable body block, before `_log_resource_usage()` |
| `decay_expiry_loop` | `bot/cogs/sentinel.py:95` — `wd.register("decay_expiry_loop", 3600)` | `bot/cogs/sentinel.py:177` — `wd.heartbeat("decay_expiry_loop")` | Before DB/service guard and guild iteration |
| `scheduled_close_loop` | `bot/cogs/tickets.py:116` — `wd.register("scheduled_close_loop", 60)` | `bot/cogs/tickets.py:122` — `wd.heartbeat("scheduled_close_loop")` | Before ticket polling; register shares `TICKET_TIMER_ENABLED` gate |
| `auto_close_stale_tickets` | `bot/cogs/tickets.py:104` — `wd.register("auto_close_stale_tickets", 3600)` | `bot/cogs/tickets.py:204` — `wd.heartbeat("auto_close_stale_tickets")` | Before logging and service work |
| `integrity_sweep_loop` | `bot/cogs/tickets.py:110` — `wd.register("integrity_sweep_loop", 3600)` | `bot/cogs/tickets.py:243` — `wd.heartbeat("integrity_sweep_loop")` | Before logging and integrity work |

All five sites use the literal `if wd:` guard. The production diff contains no added exception wrapper around any loop body. The `bot/cogs/watchdog.py` diff adds only `get_watchdog`; `WatchdogCog.register`, `heartbeat`, `_check_once`, and `_check` signatures and bodies are unchanged from `master`.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Watchdog adoption invariant | ✅ Implemented | Five production loops have exact interval registration and top-of-body heartbeat; watchdog `_check` remains the sole excluded production loop. |
| Dead-loop activation | ✅ Implemented | New `CoreCog.cog_load` starts and registers `resource_log_loop`; unload cancellation remains intact. |
| Load-order safety | ✅ Implemented | `get_watchdog` is absent-safe and `EXTENSIONS[0]` is `bot.cogs.watchdog` at `bot/bot.py:54`. |
| Gated-loop semantics | ✅ Implemented | `scheduled_close_loop.start()` and registration share the line-111 `TICKET_TIMER_ENABLED` condition. |
| Guard and KEEP | ❌ Gate regression | Guard, KEEP, coverage, type, lint, format, and dead-code checks pass; alternate randomized order fails. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — helper plus `EXTENSIONS[0]` | ✅ Yes | Both mechanisms are present and have passing tests. |
| D2 — inline literal wiring | ✅ Yes | Five literal pairs use `wd = get_watchdog(...)` and `if wd:`. |
| D3 — AST guard | ✅ Yes | AST scan excludes watchdog/realtime and has a non-tautological synthetic self-test. |
| D4 — unit and preserved error-routing tests | ✅ Yes | 15 adoption tests and preserved `TestLoopErrorRouting` pass in the focused run. |
| D5 — coverage plan | ⚠️ Partial | Overall coverage and all added executable lines are covered, but independent random order is red. |
| D6 — revert-only rollback, no DDL | ✅ Yes | No migration or SQL file is changed; watchdog remains logging-only. |

### TDD Compliance

The primary TDD evidence is the real commit sequence: RED `a2c88b5` (only `tests/test_watchdog_adoption.py`, 15 tests, 11 failures witnessed and recorded in Engram #5016) → GREEN `7bc11fa` (five production files, 49 insertions/1 reorder deletion) → style `b83ad7f` → task/ledger amendment at current `8d82073` (`ac7a3f0` lineage).

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Engram #5016 contains the TDD Cycle Evidence table and RED failure count. |
| All task rows have test/gate evidence | ✅ | 5/5 task rows map to the adoption test file or full gates. |
| RED confirmed | ✅ | RED commit adds only the test file; its 15 tests exist now and the recorded pre-wiring run had 11 failures. |
| GREEN confirmed | ✅ | All 15 adoption tests plus preserved `Loop._error` test pass in the focused run. |
| Triangulation adequate | ✅ | 15 adoption cases cover 11 scenarios, including absent/present, gated off/on, and warning paths. |
| Safety net for modified files | ✅ | Seed-42 full suite passes and five changed production files are exercised; test file was new at RED. |

**TDD compliance**: 6/6 checks passed. The final verification failure is an independent full-suite order-isolation gate, not a missing RED→GREEN cycle.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 15 | 1 | pytest, pytest-asyncio, `unittest.mock` |
| Framework integration (preserved) | 1 | 1 | discord.py `tasks.loop`, pytest |
| E2E | 0 | 0 | Not applicable |
| **Total relevant focused tests** | **16** | **2** | |

### Changed File Coverage

Coverage is from the passing seed-42 full suite. Branch coverage is not configured.

| File | Line % | Branch % | Uncovered lines | Rating |
|---|---:|---:|---|---|
| `bot/bot.py` | 78% | N/A | 216, 224, 260-261, 306, 323-324, 337-338, 361-362, 366-385, 400, 413-415, 420, 424, 426-427, 454-469, 498-511, 555-556, 567-568, 583, 645-654, 663-664, 672-673, 726, 749-755, 762-763, 773-777, 784, 815-821 | ⚠️ Low |
| `bot/cogs/core.py` | 55% | N/A | 32, 36-42, 72-79, 82-96, 99-105, 150, 205, 211, 231-245, 269-281, 300-309, 344-399, 409, 414, 456-457, 465-468, 472-475, 477-478 | ⚠️ Low |
| `bot/cogs/sentinel.py` | 71% | N/A | 79-80, 102-104, 108-112, 133, 139-140, 145, 148, 156-158, 163-164, 179, 185-186, 201-202, 219-220, 272-273, 302-303, 331, 338-339, 348-356, 359-360, 363-364, 415, 421-422, 425-433, 445-446, 448-449, 502, 516-518, 524-525, 533-534, 537-538, 540-541, 582, 588-590, 593-594, 596-597, 634, 644-646, 651-652, 660-661, 664-665, 667-668, 748, 761-763, 768-769, 777-778, 781-782, 784-785, 866, 877-893, 896-897, 899-900, 942, 953-969, 972-973, 975-976, 1029-1030, 1038-1047, 1068, 1105, 1131-1133, 1135-1136, 1141-1142, 1145-1146, 1148-1149, 1216, 1218-1219, 1222-1231, 1250-1260, 1263-1264, 1266-1267, 1277-1278, 1295, 1300, 1353 | ⚠️ Low |
| `bot/cogs/tickets.py` | 84% | N/A | 80, 130-132, 136-137, 149, 153, 156-157, 185-186, 188-193, 195-196, 208-209, 211-212, 217-219, 224-225, 228-229, 246-247, 269-270, 276-277, 280, 290, 293, 323, 326-328, 359-361, 370-371, 385-386, 405, 412-414, 418-419, 439-440, 737, 741 | ⚠️ Acceptable |
| `bot/cogs/watchdog.py` | 85% | N/A | 55, 63-64, 68, 72, 80 | ⚠️ Acceptable |

**Weighted changed-production-file coverage**: 73% (1186/1621 statements). All executable lines added by this change are covered; the below-80 file percentages are inherited whole-file coverage and remain strict-TDD warnings.

### Assertion Quality

The new test file contains 32 assertion sites and 42 mock/patch construction sites (1.31×, below the 2× warning threshold). No tautology, orphan empty assertion, assertion-free production path, ghost loop, smoke-only test, or unpaired type-only assertion was found. `hasattr`/`callable` checks in `test_get_watchdog_helper_exists` are accompanied by concrete return-value assertions.

**Assertion quality**: ✅ All assertions verify real behavior.

### Ledger Verification

`git log -1 --format=%B` contains the Ledger, Gates, KEEP, TDD, and Refs blocks.

| Ledger claim | Commit body | Fresh measurement | Result |
|---|---:|---:|---|
| Tracked files under `tests/` | 180 → 181 | 181 | ✅ Match |
| `tests/` lines | 60,939 → 61,305 | 61,305 | ✅ Match |
| Collected tests | 2,957 → 2,972 | 2,972 | ✅ Match |
| Seed-42 passed | 2,938 → 2,953 | 2,953 | ✅ Match |
| Seed-42 coverage | 80.50% → 80.58% | 80.58% | ✅ Match |
| Production delta | 5 files, +49 lines | 5 files, 49 insertions/1 deletion | ✅ Match |
| KEEP SHA256 | `71136670…` | `7113667034365c6bca9b4b94dcf7543a404fb8ab15829b4a32f2a2e029b75cfb` | ✅ Match |
| “seed 42 + random-order green” | Green | Alternate seed: 9 failures | ❌ **CRITICAL divergence** |

### Invariants

| Invariant | Evidence | Result |
|---|---|---|
| Zero new hybrid commands | Added-line count is 0; zero-hybrid guard passes | ✅ |
| Ticket comma trigger intact | `bot/cogs/tickets.py:279` still uses `content.startswith(",")`; three comma invariant tests pass | ✅ |
| No new user-facing hardcoded strings | Production diff adds only loop identifiers, extension path, docstrings, and English log messages | ✅ |
| `get_watchdog` is live | Five production imports/call sites; Vulture exits 0 | ✅ |
| No migrations | `git diff master --name-only` contains no migration or SQL path | ✅ |
| KEEP preserved | Byte-identical SHA256 and 13/13 file tests pass | ✅ |
| Watchdog API stable | Existing API methods are untouched by the diff | ✅ |
| Loop error routing stable | Focused `TestLoopErrorRouting` passes and no body wrapper was added | ✅ |

### Quality Metrics

**Linter**: ✅ Ruff check and format check pass.
**Type checker**: ✅ Ty passes with zero diagnostics.
**Dead code**: ✅ Vulture exits 0.
**Coverage**: ✅ Overall floor passes; ⚠️ three changed production files remain below 80% whole-file coverage.

### Issues Found

**CRITICAL**

1. The fresh alternate random-order suite (`--randomly-seed=8675309`) exits 1 with 9 failures in `tests/test_tickets_cog.py`. This violates task 3.1 and the “all gates green” clause of requirement 5.
2. The commit-body ledger states “seed 42 + random-order green,” but the fresh alternate-order evidence is red. The mandated ledger consistency check therefore fails.

**WARNING**

1. Strict changed-file coverage is below 80% for `bot/bot.py` (78%), `bot/cogs/core.py` (55%), and `bot/cogs/sentinel.py` (71%), although all added executable lines are covered and overall coverage is 80.58%.

**SUGGESTION**: None.

### Verdict

**FAIL**

The implementation-specific 10 scenarios, strict RED→GREEN evidence, deterministic suite, coverage, static gates, wiring, KEEP, and invariants are sound, but archive admission is blocked by a reproducible nine-test alternate-order failure and the resulting ledger contradiction.
