# Apply Progress: QA Coverage & Dead Code Cleanup — PR 3 (Final)

## Status: COMPLETE (all PRs)

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 6.1 | `tests/test_member_model.py` | Unit | ✅ 1294/1294 | ✅ Written (datetime parsing expectation) | ✅ 7/7 passed | ✅ 3 cases (string→dt, None, existing dt) | ✅ round-trip test added |
| 7.1 | `tests/test_database.py` | Facade | ✅ 1294/1294 | ✅ Written (guild_id param + guildId filter) | ✅ 4/4 passed | ➖ Single scenario | ➖ None needed |
| 7.2 | `tests/test_database.py` | Facade | ✅ 1294/1294 | N/A (no existing test; facade test in 9.4) | ✅ via 9.4 | ➖ | ➖ |
| 8.2 | `tests/test_database.py` | Facade | ✅ 1294/1294 | ✅ Written (updated sig + guildId filter assert) | ✅ 4/4 passed | ➖ Single scenario | ➖ None needed |
| 8.4 | `tests/test_infraction_service.py` | Unit | ✅ 1294/1294 | ✅ Written (guild_id in assertion) | ✅ passed | ➖ Single scenario | ➖ None needed |
| 8.5 | `tests/test_sentinel_cog.py` | Unit | ✅ 1294/1294 | ✅ Written (guild_id in assertion) | ✅ passed | ➖ Single scenario | ➖ None needed |
| 9.1 | `tests/test_ticket_category_db.py` | Facade | N/A (new) | ✅ Written (7 tests) | ✅ 7/7 passed | ✅ 2 test classes (count + update) | ➖ None needed |
| 9.2 | `tests/test_ticket_db.py` | Facade | N/A (new) | ✅ Written (11 tests) | ✅ 11/11 passed | ✅ 3 test classes (stale + channels + activity) | ➖ None needed |
| 9.3 | `tests/test_greeting_db.py` | Facade | N/A (new) | ✅ Written (4 tests) | ✅ 4/4 passed | ✅ 2 cases (persist + on_write) | ➖ None needed |
| 9.4 | `tests/test_infraction_db.py` | Facade | N/A (new) | ✅ Written (4 tests) | ✅ 4/4 passed | ✅ 3 cases (active=false, guildId, id) | ➖ None needed |
| 10.1 | Full suite | Regression | ✅ 1294/1294 | N/A | ✅ 1327 passed, 3 skipped, 0 warnings | N/A | ✅ ruff clean on PR2 files, mypy clean |
| 11.1 | `tests/test_sentinel_behavior.py` | Unit | ✅ 1327/1327 | ✅ Written (4 tests: warn escalation, bot/self/higher-role deny) | ✅ 4/4 passed | ✅ 4 cases (escalation + 3 deny paths) | ✅ Removed unused import |
| 12.1 | Full suite | Regression | ✅ 1327/1327 | N/A | ✅ 1331 passed, 3 skipped, 0 warnings | N/A | ✅ ruff clean, mypy clean |

## Test Summary

- **Total tests written**: 37 new tests across all PRs (PR1: 4, PR2: 29, PR3: 4)
- **Total tests passing**: 1331 (1294 baseline + 37 new)
- **Layers used**: Unit (8), Facade (29)
- **Approval tests**: None — no refactoring tasks
- **Pure functions created**: 1 (`_parse_dt` helper in member.py)

## Files Changed

### PR 1 (merged)
| File | Action | What Was Done |
|------|--------|---------------|
| `tests/test_economy_config_model.py` | Created | EconomyConfig round-trip and defaults |
| `tests/test_member_model.py` | Created | Member datetime parsing/ISO serialization and defaults |
| `tests/test_core_help_builder.py` | Created | Internal help builders and context-prefix fallback |
| `tests/test_brand.py` | Modified | Added production-source hex-literal contract scan |
| `tests/test_manual.py` | Modified | Added order-independent runtime command discovery assertion |

### PR 2 (merged)
| File | Action | What Was Done |
|------|--------|---------------|
| `bot/models/member.py` | Modified | Added `_parse_dt()` helper; `from_db_row` now parses ISO strings |
| `bot/core/db/ticket_category_db.py` | Modified | `count_open_tickets_by_category` requires `guild_id` param |
| `bot/core/db/infraction_db.py` | Modified | `deactivate_infraction` requires `guild_id` param |
| `bot/cogs/tickets.py` | Modified | `delete_category` passes `gid` to `count_open_tickets_by_category` |
| `bot/services/infraction_service.py` | Modified | `unwarn()` passes `guild_id` to `deactivate_infraction` |
| `tests/test_member_model.py` | Modified | Updated for datetime parsing; added round-trip test |
| `tests/test_database.py` | Modified | `TestCountOpenTicketsByCategory` updated for new signature |
| `tests/test_infraction_service.py` | Modified | `deactivate_infraction` assertion updated |
| `tests/test_sentinel_cog.py` | Modified | `deactivate_infraction` assertion updated |
| `tests/test_ticket_category_db.py` | Created | 7 tests: count_open + update_field_defs |
| `tests/test_ticket_db.py` | Created | 11 tests: get_stale + get_channel_ids + update_activity |
| `tests/test_greeting_db.py` | Created | 4 tests: upsert persists + on_write hook |
| `tests/test_infraction_db.py` | Created | 4 tests: active=false + guildId + id filters |

### PR 3 (this PR)
| File | Action | What Was Done |
|------|--------|---------------|
| `tests/test_sentinel_behavior.py` | Created | 4 behavioral tests: warn auto-escalation, bot/self/higher-role target denial |

## Deviations from Design

None — implementation matches design.

## Issues Found

None.

## Commit

```
test(qa): add sentinel behavior tests for warn/mute/kick/validate_target
```

## All Tasks Complete

All 91 lines of tasks.md are now `[x]` — no remaining tasks.
