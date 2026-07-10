# Proposal: Type-Strict Cogs

## Intent

Narrow the blanket `bot.cogs.*` mypy override disabling 7 error codes across 8 cog modules. The wildcard hides ~11 real type bugs and 51 `type-arg` violations. Per AGENTS.md, cogs MUST be strict-typed. Mirrors archived `type-strict-services`.

## Scope

### In Scope
- Fix 51 `type-arg`: `Context` → `Context[Any]` across 8 cog files (mechanical)
- Fix 11 real `arg-type`: `User | Member` narrowing (sentinel), `datetime | None` guard (utility), `int | None` guard (greetings)
- Inline-suppress 25 `arg-type` stub limitations with `# type: ignore[arg-type]` + rationale
- Update/remove 7 stale `# type: ignore[override]` comments (`unused-ignore`)
- Narrow `pyproject.toml` override to `["untyped-decorator"]` (drop 6 codes)
- Full mypy + pytest verification

### Out of Scope
- `is_admin()` / `is_mod()` return-type fix (`bot/utils/checks.py`) — out of cogs scope
- discord.py `hybrid_command` stub redesign — external, unfixable here
- Per-module overrides — one justified wildcard only

## Capabilities

None — pure type-safety refactor. No behavior changes, no new features, no modified requirements.

## Approach

**Approach 2 from exploration** — narrow to `untyped-decorator` only, fix everything else.

`untyped-decorator` cannot be fixed inline (`hybrid_command` decorator strips types). Wildcard justified — mirrors `bot.bot` keeping `attr-defined`.

1. `Context` → `Context[Any]` in 8 cogs (51 fixes)
2. `isinstance(ctx.author, discord.Member)` before `log_moderation_action` (sentinel — 8 errors)
3. None guards: `format_dt` (utility), `member_count or 0` (greetings)
4. Update/remove 7 stale `# type: ignore[override]`
5. Inline `# type: ignore[arg-type]  # hybrid_command stub limitation` on 25 decorator lines
6. Narrow override to `["untyped-decorator"]`
7. Verify: `uv run mypy bot/cogs/` + `uv run pytest`

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | Narrow override to `["untyped-decorator"]` |
| `bot/cogs/sentinel.py` | Modified | `Context[Any]` + `ctx.author` narrowing (35) |
| `bot/cogs/tickets.py` | Modified | `Context[Any]` + inline suppress (33) |
| `bot/cogs/greetings.py` | Modified | `Context[Any]` + guards + stale ignores (27) |
| `bot/cogs/stellar.py` | Modified | `Context[Any]` + stale ignores (10) |
| `bot/cogs/utility.py` | Modified | `Context[Any]` + None guard (7) |
| `bot/cogs/ocio.py` | Modified | `Context[Any]` (4) |
| `bot/cogs/core.py` | Modified | Inline suppress (4) |
| `bot/cogs/setup.py` | Modified | `Context[Any]` + inline suppress (2) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 25 inline ignores stale if discord.py stubs improve | Low | `unused-ignore` enabled → mypy flags them |
| Runtime regression from annotation-only changes | Very Low | Full pytest must pass |
| `ctx.author` guard too narrow in non-guild context | Low | Only where guild context is guaranteed |

## Rollback Plan

Revert `pyproject.toml` to restore all 7 error codes in the wildcard override. All other changes are annotation/type-only with zero runtime impact — individual cogs can be reverted independently.

## Dependencies

- None — all changes within the bot codebase

## Success Criteria

- [ ] `bot.cogs.*` override narrowed to `["untyped-decorator"]` in `pyproject.toml`
- [ ] `uv run mypy bot/cogs/` passes with zero errors
- [ ] `uv run pytest` — all tests pass
- [ ] No per-module overrides added for cogs
