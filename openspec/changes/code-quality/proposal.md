# Proposal: Code Quality Consolidation

## Intent

NebulosaBot has strong QA gates but is blind to duplication, dead code, and accumulated git debris. This cycle removes known duplication hotspots, adds lightweight CI detection tools, and cleans up stale branches/stashes — all within a tight review budget (~20 lines of code change).

## Scope

### In Scope
- Centralize `"nb!"` fallback prefix: move `_FALLBACK_PREFIX` to `bot/constants.py`, import in 4 files (~8 lines)
- Deduplicate `_resolve_avatar_url`: delete from `bot/cogs/greetings.py`, import from `bot/services/greeting_service.py` (~7 lines)
- Add jscpd + vulture to CI as **report-only** (default OFF for hard fail)
- Git hygiene: delete 15 merged remote branches, drop 3 stale stashes
- Document layering debt (tickets.py: 14 direct DB calls, sentinel.py: 5 direct DB calls) as backlog notes

### Out of Scope
- Layering refactor (tickets.py/sentinel.py DB bypass — too large for 400-line review budget)
- SELECT * cleanup (defer until scale demands it)
- UX features, RPC/RLS, migrations, bot-ux labels

## Capabilities

This change is pure refactor + infrastructure — no spec-level behavior changes.

### New Capabilities
None

### Modified Capabilities
None

## Approach

1. Create `bot/constants.py` with `FALLBACK_PREFIX = "nb!"` (UPPER_SNAKE_CASE per AGENTS.md)
2. Update `bot/bot.py`, `bot/models/guild.py`, `bot/core/db/guild_db.py`, `bot/services/guild_service.py`, `bot/cogs/core.py` to import from constants
3. Delete `_resolve_avatar_url` from `bot/cogs/greetings.py:188`, import from `bot/services/greeting_service.py:229`
4. Add `.github/workflows/code-quality.yml` with jscpd (npx) + vulture steps, `continue-on-error: true`
5. Run git cleanup commands (branch delete + stash drop) as documented chore tasks
6. Verify: all 957 tests pass, coverage ≥ 75%, ruff/mypy/bandit clean

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/constants.py` | New | Houses `FALLBACK_PREFIX` constant |
| `bot/bot.py` | Modified | Import from constants instead of local `_FALLBACK_PREFIX` |
| `bot/models/guild.py` | Modified | Import `FALLBACK_PREFIX` for default + from_row |
| `bot/core/db/guild_db.py` | Modified | Import `FALLBACK_PREFIX` for upsert dict |
| `bot/services/guild_service.py` | Modified | Import `FALLBACK_PREFIX` (2 sites) |
| `bot/cogs/core.py` | Modified | Import `FALLBACK_PREFIX` for `_resolve_prefix` |
| `bot/cogs/greetings.py` | Modified | Delete `_resolve_avatar_url`, import from service |
| `.github/workflows/code-quality.yml` | New | Report-only jscpd + vulture CI step |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Circular import from `bot.constants` | Low | Constants module has zero internal imports |
| jscpd noise from test boilerplate | Medium | Use per-directory thresholds (5% bot/, 10% tests/) |
| vulture false positives on discord.py | Medium | Whitelist with `# noqa: vulture`, iterate after first run |

## Rollback Plan

Revert the single PR. Each change is atomic — constant imports are drop-in replacements, avatar helper is a one-line import swap. CI step uses `continue-on-error: true` so it never blocks merges. Git cleanup is irreversible but branches are already merged with 0 unique commits.

## Dependencies

- None (jscpd via npx, vulture via pip — no new persistent infra)

## Success Criteria

- [ ] `"nb!"` literal appears in exactly 1 production file (`bot/constants.py`)
- [ ] `_resolve_avatar_url` exists in exactly 1 file (`bot/services/greeting_service.py`)
- [ ] `uv run pytest` passes (957+ tests, ≥ 75% coverage)
- [ ] CI workflow runs jscpd + vulture without blocking PRs
- [ ] 15 merged branches deleted, 3 stashes dropped
