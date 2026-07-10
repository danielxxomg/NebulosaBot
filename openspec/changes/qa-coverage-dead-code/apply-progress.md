# Apply Progress: QA Coverage & Dead Code Cleanup — PR 1

## Status: COMPLETE (PR 1 boundary)

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_economy_config_model.py` | Unit | ✅ 1272/1272 | ✅ Written (tests reference production code) | ✅ 4/4 passed | ✅ 2 test classes (from_db_row + to_db_dict) | ➖ None needed |
| 1.2 | `tests/test_member_model.py` | Unit | ✅ 1272/1272 | ✅ Written (tests current behavior) | ✅ 6/6 passed | ✅ 2 test classes (from_db_row + to_db_dict) | ➖ None needed |
| 2.1 | `tests/test_brand.py` | Unit | ✅ 1272/1272 | ✅ Written (hex scan test) | ✅ 9/9 passed | ➖ Single scenario | ➖ None needed |
| 3.1 | `tests/test_core_help_builder.py` | Unit | N/A (new) | ✅ Written (mock bot/cog) | ✅ 10/10 passed | ✅ 3 test classes (resolve_prefix + build_embed + build_pages) | ✅ Import sort fixed |
| 4.1 | `tests/test_manual.py` | Unit | ✅ 1272/1272 | ✅ Written (dynamic discovery) | ✅ 1/1 passed | ➖ Single scenario | ➖ None needed |
| 5.1 | Full suite | Regression | ✅ 1294/1294 | N/A | ✅ 1294 passed, 3 skipped, 0 warnings | N/A | ✅ ruff clean on new files |

## Test Summary

- **Total tests written**: 22 new tests (4 + 6 + 1 + 10 + 1)
- **Total tests passing**: 1294 (1272 baseline + 22 new)
- **Layers used**: Unit (22)
- **Approval tests**: None — no refactoring tasks in PR1
- **Pure functions created**: 1 (`_discover_hybrid_commands` helper in test_manual.py)

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `tests/test_economy_config_model.py` | Created | EconomyConfig from_db_row/to_db_dict round-trip + defaults (4 tests) |
| `tests/test_member_model.py` | Created | Member from_db_row/to_db_dict current behavior + defaults (6 tests) |
| `tests/test_brand.py` | Modified | Added hex-scan test: no hardcoded hex in production embed colors (1 test) |
| `tests/test_core_help_builder.py` | Created | Help builder internals: _resolve_prefix, _build_cog_help_embed, _build_help_pages (10 tests) |
| `tests/test_manual.py` | Modified | Added dynamic hybrid command discovery test (1 test) |

## Deviations from Design

1. **Task 1.2 scope reduced**: Original spec asked for datetime parsing tests. Per orchestrator boundary ("if Member datetime tests need production fix, that is PR2"), tests verify CURRENT behavior (strings pass through, datetime instances serialize correctly). Production fix deferred to PR2.

2. **Task 1.3 deferred**: `bot/models/member.py` production fix (datetime.fromisoformat parsing) is PR2 scope per orchestrator boundary. Not implemented in PR1.

## Issues Found

None — zero production changes, all tests green on existing code.

## Commit

```
test(qa): add model, brand hex-scan, help builder, and manual discovery tests
```
