# Proposal: Type-Strict Services

## Intent

Remove the blanket `bot.services.*` mypy override that silently disables 5 error codes across all 10 service modules. Services are the business-logic layer — per AGENTS.md, they MUST be strict-typed. The current override is inherited debt from earlier cycles.

## Scope

### In Scope
- Remove `[[tool.mypy.overrides]]` wildcard for `bot.services.*` from `pyproject.toml`
- Fix 16 fixable errors at source (3 root causes: cache returns, bare `dict`, missing annotations)
- Inline-suppress 4 stub-limitation errors with `# type: ignore[code]` + rationale
- Full mypy + test suite verification (1375 tests)

### Out of Scope
- Making `TTLCache` generic (`TTLCache[T]`) — deferred to a future core refactor cycle
- Adding `dict[str, Any]` to DB layer return types (`bot/core/db/*`) — deferred; DB has its own override
- Adding per-module overrides for services — all errors resolved at source

## Capabilities

None — this is a pure type-safety refactor. No behavior changes, no new features, no modified requirements.

## Approach

**Approach 2 from exploration** — fix all errors at the source, inline-suppress stub limitations.

1. **Cache `no-any-return` (3 errors)**: `cast()` at call sites in `guild_service.py`, `greeting_service.py`, `economy_service.py`
2. **Bare `dict` → `dict[str, Any]` (8 errors)**: Update service-level signatures in `economy_service.py`, `ticket_service.py`, `ticket_invariants.py`
3. **Missing annotations (3 errors)**: Add type hints to `_format_template`, `_send_text_only_if_message`, `_resolve_avatar_url` in `greeting_service.py`
4. **`arg-type` for `int | None` (2 errors)**: Narrow with `member_count or 0` in `greeting_service.py`
5. **Stub limitations (4 errors)**: `# type: ignore[attr-defined]` for `Image.LANCZOS`, `# type: ignore[arg-type]` for `message.channel` union in `logging_service.py`
6. **Remove wildcard** from `pyproject.toml` line 135-137
7. **Verify**: `uv run mypy bot/services/` + `uv run pytest`

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | Remove `bot.services.*` mypy override (lines 135-137) |
| `bot/services/guild_service.py` | Modified | `cast()` at cache return (1 line) |
| `bot/services/greeting_service.py` | Modified | `cast()` + annotations + `int \| None` fix (6 errors) |
| `bot/services/economy_service.py` | Modified | `cast()` + `dict[str, Any]` signatures (5 errors) |
| `bot/services/logging_service.py` | Modified | Inline `# type: ignore` for stub (2 errors) |
| `bot/services/ticket_service.py` | Modified | `dict[str, Any]` signatures (3 errors) |
| `bot/services/ticket_invariants.py` | Modified | `dict[str, Any]` signatures (2 errors) |
| `bot/services/image_service.py` | Modified | Inline `# type: ignore` for Pillow stub (2 errors) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `cast()` hides real type mismatches at cache sites | Low | Pragmatic compromise; future cycle can make TTLCache generic |
| Runtime regression from annotation-only changes | Very Low | Full test suite (1375 tests) must pass |
| DB layer still returns bare `dict` | N/A | Out of scope — `bot.core.*` has its own override |

## Rollback Plan

Revert `pyproject.toml` to restore the wildcard override. All other changes are annotation/type-only with zero runtime impact — any individual file can be reverted independently without breaking behavior.

## Dependencies

- None — all changes are within the bot codebase

## Success Criteria

- [ ] `bot.services.*` wildcard override removed from `pyproject.toml`
- [ ] `uv run mypy bot/services/` passes with zero errors
- [ ] `uv run pytest` — all 1375 tests pass
- [ ] No per-module overrides added for services
