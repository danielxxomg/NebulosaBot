# Proposal: type-strict-core-listeners

## Intent

Clear all 42 mypy strict errors across `bot.core.*`, `bot.listeners.*`, and `bot.bot` so their three per-file override blocks can be removed from `pyproject.toml`. Zero behavioral change. Mirrors archived `type-strict-models` / `type-strict-cogs`.

## Scope

### In Scope
- Fix 36 `type-arg`: bare `dict` → `dict[str, Any]` across 13 `bot/core/` files
- Fix 2 `no-any-return` in `context.py`: `cast()` on `self.bot.db` / `self.bot.cache`
- Fix 2 `attr-defined` in `bot/bot.py`: `assert isinstance(ctx, NebulosaContext)`
- Fix 1 `assignment` in `xp_listener.py`: narrow `target_channel` type
- Fix 1 `arg-type` in `audit_listener.py`: `isinstance` guard on `before.channel`
- Remove 3 `[[tool.mypy.overrides]]` blocks (`bot.core.*`, `bot.listeners.*`, `bot.bot`)

### Out of Scope
- `bot.cogs.*` (`untyped-decorator` override stays)
- `tests.*` (separate tech debt)
- Protocol-based bot typing (Approach 2 — deferred)
- `NebulosaContext` runtime import of `NebulosaBot` (circular — `type: ignore[type-arg]` on class def stays)

## Capabilities

### New Capabilities
None — pure type-safety refactor.

### Modified Capabilities
- `pyproject-toml-qa-config`: Three override blocks (`bot.core.*`, `bot.listeners.*`, `bot.bot`) SHALL be removed. Surviving overrides: `bot.cogs.*` (untyped-decorator), `tests.*`. The "Mypy configuration present" requirement MUST reflect surviving overrides. The "attr-defined suppressed per-file" scenario is replaced — `bot.bot` no longer needs suppression after `isinstance` narrowing.

## Approach

**Approach 1 from exploration** — three mechanical tiers:

1. **Tier 1 (36 type-arg):** `dict` → `dict[str, Any]`, `list[dict]` → `list[dict[str, Any]]`. Context class def keeps `# type: ignore[type-arg]` (circular import). All files already import `Any`.
2. **Tier 2 (4 errors):** `cast()` in `context.py` properties + `assert isinstance(ctx, NebulosaContext)` in `bot.py`.
3. **Tier 3 (2 listeners):** One `isinstance` guard each in `xp_listener` and `audit_listener`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/core/{realtime,context,i18n}.py` | Modified | 11 errors — type-arg + 2 casts |
| `bot/core/db/*.py` (10 files) | Modified | 27 type-arg — bare `dict` return types |
| `bot/listeners/{xp,audit}_listener.py` | Modified | 2 errors — type-narrowing guards |
| `bot/bot.py` | Modified | 2 attr-defined — assert isinstance |
| `pyproject.toml` | Modified | Remove 3 override blocks |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `cast` is a type lie | Low | `setup_hook()` initializes services before commands |
| `isinstance` guard wrongly excludes channels | Low | DMs already filtered; guild channels are `GuildChannel` |
| `type: ignore[type-arg]` on Context stale | Low | `unused-ignore` flags if stubs improve |

## Rollback Plan

Re-add the 3 override blocks to `pyproject.toml`. All other changes are annotation/cast/assert-only — zero runtime impact.

## Success Criteria

- [ ] `mypy --strict --python-version 3.11 bot/core/ bot/listeners/ bot/bot.py` reports 0 errors
- [ ] Full strict mypy error count drops by 42
- [ ] Only `bot.cogs.*` and `tests.*` overrides remain
- [ ] `uv run pytest` — all tests pass unchanged
