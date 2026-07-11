# Proposal: Harden Command Permissions

## Intent

Security fix: `is_mod()` in `bot/utils/checks.py` only registers an `app_commands.check` (slash path) — it has NO `commands.check` (prefix path). `is_admin()` correctly dual-gates both paths. Result: 22+ moderation/staff hybrid commands (`!warn`, `!kick`, `!mute`, ticket config, etc.) are executable by ANY user via prefix invocation. This is an authorization bypass.

## Scope

### In Scope
- Add `_prefix_predicate` to `is_mod()` mirroring the proven `is_admin()` dual-path pattern
- Wrap decorator as `commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))`
- Keep deny-by-default for non-admins when mod role is unconfigured (current slash behavior — intentional)
- Expose `prefix_predicate` on the decorator for testability (matches `is_admin()`)
- TDD: tests proving BOTH `cmd.checks` (prefix) and `app_command.checks` (slash) are registered
- Prefix denial messages via existing error handlers (no new UX surfaces)

### Out of Scope
- Permission registry matrix / factory (Approach B) — future hardening
- Discord guild perms enforcement (`kick_members`, `ban_members`) — breaks role-only mod servers
- `unclaim` missing decorator (tickets.py:681) — follow-up
- GreetingsCog body-check `_admin_guard()` refactor — follow-up (low risk, works today)
- Ticket one-per-user `ValueError` race — follow-up
- Close button `NotFound` after channel delete — follow-up

## Capabilities

> Research: `openspec/specs/permission-model/spec.md` exists with `Moderator check`, `Unconfigured moderator role`, and `Ban command requires administrator` requirements.

### New Capabilities
None

### Modified Capabilities
- `permission-model`: `is_mod` requirement MUST enforce on BOTH prefix and slash invocation paths (currently spec describes behavior but implementation only gates slash). Add explicit dual-path enforcement requirement + prefix denial scenarios.

## Approach

Surgical fix to `is_mod()` in `bot/utils/checks.py` — single file, ~15 lines. Mirror `is_admin()`: define `async def _prefix_predicate(ctx)` that guards DM (`NoPrivateMessage`), admin pass, mod-role resolution from cache, deny-by-default when unconfigured, `MissingRole` when configured but lacking. Compose as `commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))`. Reuse `_resolve_mod_role_id` and `_user_has_role` helpers (accept `ctx`/`Member` — minor adapter since helpers currently take `Interaction`). TDD first per `strict_tdd: true`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/utils/checks.py` | Modified | Add `_prefix_predicate` + dual-path wrapper to `is_mod()`; expose `prefix_predicate` |
| `tests/unit/test_checks.py` | Modified | Add dual-path test coverage (prefix predicate exists, denies non-mod, allows admin, allows mod role) |
| `tests/unit/test_sentinel_cog.py` | Modified | Add `test_warn_prefix_check_present` — verify `warn.cmd.checks` non-empty |
| `bot/cogs/sentinel.py` | Unchanged (auto-fixed) | 8 commands inherit dual-gate via `@is_mod()` |
| `bot/cogs/tickets.py` | Unchanged (auto-fixed) | 14 commands inherit dual-gate via `@is_mod()` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Prefix denial UX differs from slash denial | Low | Both raise discord.py exceptions (`CheckFailure`, `MissingRole`); existing cog error handlers catch these |
| `_user_has_role` called with `ctx.author` (Member) vs `interaction.user` | Low | Helper already handles `User` vs `Member` — returns `False` for non-Member |
| Mod role cache miss path returns `None` → deny | Low | Intentional deny-by-default (spec: unconfigured mod role) — documented |

## Rollback Plan

Revert `bot/utils/checks.py` to pre-change commit. No schema, config, or data changes. Affected commands return to prefix-open state (pre-fix) — safe revert, does not break slash path.

## Dependencies

None external.

## Success Criteria

- [ ] `is_mod()` registers BOTH `commands.check` (prefix) and `app_commands.check` (slash)
- [ ] Regular user invoking `!warn` via prefix is denied
- [ ] Admin invoking `!warn` via prefix passes
- [ ] Mod-role user invoking `!warn` via prefix passes
- [ ] Unconfigured-guild non-admin invoking `!warn` via prefix is denied (deny-by-default)
- [ ] All 384 existing tests remain green; new tests prove dual-path registration
- [ ] `uv run pytest` passes with coverage ≥ 0.70

## Proposal question round

> execution_mode: auto — orchestrator encoded product decisions as assumptions. Listed here for user review; not blocking.

1. **Unconfigured mod role**: keep deny-by-default for non-admins? (assumed YES — matches current slash behavior, spec-aligned)
2. **Discord guild perms**: require `kick_members`/`ban_members` as defense-in-depth in this slice? (assumed NO — compatibility risk for role-only mod servers, deferred)
3. **Scope**: surgical `is_mod()` fix only, no permission registry? (assumed YES — Approach A only)
4. **Secondary issues** (`unclaim`, greetings body-check, ticket races): include in this change? (assumed NO — non-goals/follow-ups)
