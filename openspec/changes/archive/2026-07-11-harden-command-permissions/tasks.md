# Tasks: Harden Command Permissions

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120 (3 files) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Dual-path `is_mod()` with full TDD coverage | PR 1 | Single commit; tests + impl together |

## Phase 1: RED — Failing Tests for Prefix Path

- [x] 1.1 **RED**: Add `test_is_mod_prefix_predicate_exists` to `tests/test_checks.py` — assert `is_mod().prefix_predicate` exists and is callable
- [x] 1.2 **RED**: Add `test_is_mod_prefix_admin_passes` — mock `Context` with admin `Member`; assert `prefix_predicate` returns `True`
- [x] 1.3 **RED**: Add `test_is_mod_prefix_mod_role_passes` — mock `Context` with configured mod role cache + member with role; assert returns `True`
- [x] 1.4 **RED**: Add `test_is_mod_prefix_regular_user_raises_missing_role` — mock `Context`, configured mod role, user lacks it; assert raises `commands.MissingRole`
- [x] 1.5 **RED**: Add `test_is_mod_prefix_dm_raises_no_private_message` — mock `Context` with `guild=None`; assert raises `commands.NoPrivateMessage`
- [x] 1.6 **RED**: Add `test_is_mod_prefix_unconfigured_raises_check_failure` — mock `Context`, no mod role cache, non-admin; assert raises `commands.CheckFailure`
- [x] 1.7 **RED**: Add `test_is_mod_dual_registration` — apply `@is_mod()` to a hybrid command, inspect `cmd.checks` and `app_command.checks` are non-empty (integration wiring)
- [x] 1.8 **Verify RED**: Run `uv run pytest tests/test_checks.py -k prefix -v` — confirm all 7 new tests FAIL because prefix gate is missing

## Phase 2: GREEN — Implement Dual-Path `is_mod()`

- [x] 2.1 Add `_resolve_mod_role_id_from_bot(bot, guild_id)` to `bot/utils/checks.py` — shared resolver used by both interaction and context paths (JD-B-003)
- [x] 2.2 Refactor `_resolve_mod_role_id` to delegate to `_resolve_mod_role_id_from_bot`
- [x] 2.3 Add `async def _prefix_predicate(ctx: commands.Context) -> bool` to `bot/utils/checks.py` — DM guard (`NoPrivateMessage`), admin pass, mod-role resolution, deny-by-default (`CheckFailure`), missing role (`MissingRole`)
- [x] 2.4 Modify `is_mod()` decorator to return `commands.check(_prefix_predicate)(app_commands.check(predicate)(func))` — matching `is_admin()` dual-gate pattern
- [x] 2.5 Expose `prefix_predicate` on the decorator: `decorator.prefix_predicate = _prefix_predicate`
- [x] 2.6 **Verify GREEN**: Run `uv run pytest tests/test_checks.py -v` — all 23 tests PASS

## Phase 3: Regression & Coverage

- [x] 3.1 Run `uv run pytest` — confirm all 1504 tests remain green (no regressions)
- [x] 3.2 Run `uv run pytest --cov` — coverage 88.12% (above 75% gate)
- [x] 3.3 Review: verify `is_mod_check()` unchanged (button-callback contract preserved)
