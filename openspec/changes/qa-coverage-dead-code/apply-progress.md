# Apply Progress: QA Coverage & Dead Code Cleanup — PR 2

## Status: COMPLETE (PR 2 boundary)

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

## Test Summary

- **Total tests written**: 33 new tests (4 member + 4 count_open + 7 ticket_category + 11 ticket + 4 greeting + 4 infraction + -1 existing updated)
- **Total tests passing**: 1327 (1294 baseline + 33 new)
- **Layers used**: Unit (4), Facade (29)
- **Approval tests**: None — no refactoring tasks
- **Pure functions created**: 1 (`_parse_dt` helper in member.py)

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/models/member.py` | Modified | Added `_parse_dt()` helper; `from_db_row` now parses ISO strings via `datetime.fromisoformat()` |
| `bot/core/db/ticket_category_db.py` | Modified | `count_open_tickets_by_category` now requires `guild_id` param + `guildId` filter |
| `bot/core/db/infraction_db.py` | Modified | `deactivate_infraction` now requires `guild_id` param + `guildId` filter |
| `bot/cogs/tickets.py` | Modified | `delete_category` passes `gid` to `count_open_tickets_by_category` |
| `bot/services/infraction_service.py` | Modified | `unwarn()` passes `guild_id` to `deactivate_infraction` |
| `tests/test_member_model.py` | Modified | Updated to expect datetime parsing; added round-trip test and existing-dt passthrough test |
| `tests/test_database.py` | Modified | `TestCountOpenTicketsByCategory` updated for `(guild_id, category_id)` signature + guildId filter assert |
| `tests/test_infraction_service.py` | Modified | `deactivate_infraction` assertion updated to expect `(guild_id, infraction_id)` |
| `tests/test_sentinel_cog.py` | Modified | `deactivate_infraction` assertion updated to expect `(guild_id, infraction_id)` |
| `tests/test_ticket_category_db.py` | Created | 7 tests: count_open (guild+category+status+count_exact), update_field_defs (id+guild) |
| `tests/test_ticket_db.py` | Created | 11 tests: get_stale (guild+time+status), get_channel_ids (guild+status), update_activity (channel+timestamp) |
| `tests/test_greeting_db.py` | Created | 4 tests: upsert persists, on_write hook, skip when None, raises without connect |
| `tests/test_infraction_db.py` | Created | 4 tests: active=false, guildId filter, id filter, raises without connect |

## Deviations from Design

None — implementation matches design.

## Issues Found

None.

## Commit

```
fix(db): guild-scope facade methods + model datetime parsing + facade tests
```

## Remaining Tasks (PR 3)

- [ ] 11.1 Create `tests/test_sentinel_behavior.py` — sentinel behavior tests
- [ ] 12.1 PR 3 verification — full suite green, commit
