# Apply Progress: harden-command-permissions

**Mode**: Strict TDD
**Date**: 2026-07-11
**Status**: All tasks complete — ready for verify

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ➖ Single (structural) | ✅ Clean |
| 1.2 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ✅ 2 cases (admin + non-admin) | ✅ Clean |
| 1.3 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ✅ 2 cases (mod role + no role) | ✅ Clean |
| 1.4 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ✅ 2 cases (MissingRole vs CheckFailure) | ✅ Clean |
| 1.5 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ➖ Single (DM guard) | ✅ Clean |
| 1.6 | `tests/test_checks.py` | Unit | ✅ 40/40 | ✅ Written | ✅ Passed | ✅ 2 cases (unconfigured msg check) | ✅ Clean |
| 1.7 | `tests/test_checks.py` | Integration | ✅ 40/40 | ✅ Written | ✅ Passed | ➖ Single (wiring proof) | ✅ Clean |
| 2.1 | N/A (production) | — | — | — | — | — | ✅ Extracted shared resolver |
| 2.2 | N/A (production) | — | — | — | — | — | ✅ Delegated existing resolver |
| 2.3 | N/A (production) | — | — | — | — | — | ✅ Minimal prefix predicate |
| 2.4 | N/A (production) | — | — | — | — | — | ✅ Dual-check composition |
| 2.5 | N/A (production) | — | — | — | — | — | ✅ Attribute exposed |
| 3.1 | Full suite | Regression | — | — | ✅ 1504/1504 | — | — |
| 3.2 | Coverage gate | Regression | — | — | ✅ 88.12% | — | — |
| 3.3 | `tests/test_checks.py` | Unit | — | — | ✅ 8/8 | — | — |

### Test Summary

- **Total tests written**: 7 new tests
- **Total tests passing**: 1504 (full suite), 23 (test_checks.py)
- **Layers used**: Unit (6), Integration (1)
- **Approval tests**: None — no refactoring tasks
- **Pure functions created**: 1 (`_resolve_mod_role_id_from_bot`)

## Completed Tasks

### Phase 1: RED

- [x] 1.1 `test_is_mod_prefix_predicate_exists` — asserts `.prefix_predicate` attribute exists
- [x] 1.2 `test_is_mod_prefix_admin_passes` — admin passes prefix predicate
- [x] 1.3 `test_is_mod_prefix_mod_role_passes` — configured mod role passes prefix predicate
- [x] 1.4 `test_is_mod_prefix_regular_user_raises_missing_role` — MissingRole raised for configured-but-missing
- [x] 1.5 `test_is_mod_prefix_dm_raises_no_private_message` — NoPrivateMessage raised in DMs
- [x] 1.6 `test_is_mod_prefix_unconfigured_raises_check_failure` — CheckFailure when no mod role + non-admin
- [x] 1.7 `test_is_mod_dual_registration` — integration wiring proof (both checks non-empty)
- [x] 1.8 Verify RED confirmed: 7/7 new tests failed as expected

### Phase 2: GREEN

- [x] 2.1 Extracted `_resolve_mod_role_id_from_bot(bot, guild_id)` shared resolver (JD-B-003)
- [x] 2.2 Refactored `_resolve_mod_role_id` to delegate to shared resolver
- [x] 2.3 Added `_prefix_predicate(ctx)` with full DM/admin/role/deny logic
- [x] 2.4 Modified `is_mod()` to return `commands.check(_prefix_predicate)(app_commands.check(predicate)(func))`
- [x] 2.5 Exposed `decorator.prefix_predicate = _prefix_predicate`
- [x] 2.6 Verify GREEN confirmed: 23/23 tests pass

### Phase 3: Regression

- [x] 3.1 Full suite: 1504 passed, 3 skipped
- [x] 3.2 Coverage: 88.12% (above 75% gate)
- [x] 3.3 `is_mod_check()` API unchanged — 8 dedicated tests pass

## Review Ledger Items Addressed

| ID | Action |
|----|--------|
| JD-B-001 | ✅ Non-member prefix denial covered by `test_is_mod_prefix_unconfigured_raises_check_failure` (User without Member raises CheckFailure) |
| JD-B-003 | ✅ Shared resolver `_resolve_mod_role_id_from_bot` extracted — both paths use it |
| JD-B-004 | ✅ `test_is_mod_dual_registration` asserts both `cmd.checks` and `app_command.checks` non-empty |

## Deviations from Design

None — implementation matches design.

## Files Changed

| File | Action | Lines Changed |
|------|--------|---------------|
| `bot/utils/checks.py` | Modified | +65 lines (shared resolver + prefix predicate + dual-check composition) |
| `tests/test_checks.py` | Modified | +90 lines (7 new tests + import) |
| `openspec/changes/harden-command-permissions/tasks.md` | Modified | Task checkboxes updated |
