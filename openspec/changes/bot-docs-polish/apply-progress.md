# Apply Progress: Bot Docs Polish

## PR1 — Avatar Fix (TDD) ✅

**Batch scope**: Phase 1 only — avatar embed from thumbnail to set_image
**Chain strategy**: stacked-to-main
**Status**: Complete

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| 1.1 Tests — `embed.image.url` + `?size=1024` | ✅ 3 tests failed: `assert None == '...?size=1024'` | — | — | Done |
| 1.2 Implementation — `set_image(url=f"{avatar_url}?size=1024")` | — | ✅ 11/11 tests pass | — | Done |
| 1.3 Verify — `uv run pytest tests/test_utility_cog.py` | — | ✅ all green | — | Done |

### Files Changed

| File | Action | Lines | What |
|------|--------|-------|------|
| `bot/cogs/utility.py` | Modified | +1/-1 | `set_thumbnail` → `set_image` with `?size=1024` |
| `tests/test_utility_cog.py` | Modified | +9/-9 | 3 assertions: `thumbnail.url` → `image.url` with size param |

### Commit

```
fix(utility): render avatar as large image instead of thumbnail
```

### Deviations from Design

None — implementation matches design exactly.

### Issues Found

None.

---

## PR2 — Description Polish + Annotations ✅

**Batch scope**: Phase 2 — string-only edits across 5 cogs
**Chain strategy**: stacked-to-main
**Status**: Complete

### Tasks Completed

- [x] 2.1 `bot/cogs/sentinel.py` — Added trailing period to all 9 command descriptions
- [x] 2.2 `bot/cogs/tickets.py` — Added periods; added missing `description=` for `configure_fields` group + `set` subcommand, `subticket` group + `create` subcommand, `reopen`, `transfer`, `note` group + `add`/`list`/`delete` subcommands
- [x] 2.3 `bot/cogs/stellar.py` — Added trailing period to `daily`, `coins`, `leaderboard`, `rank`
- [x] 2.4 `bot/cogs/greetings.py` — Added periods to `welcome_test`/`goodbye_test`; added descriptions for `welcome` group + `channel`/`toggle`/`message` subcommands, `goodbye` group + `channel`/`toggle`/`message` subcommands
- [x] 2.5 `bot/cogs/setup.py` — Added trailing period; added `@app_commands.describe()` for `ticket_category`, `mod_role`, `log_channel`, `language`; added missing `app_commands` import
- [x] 2.6 Verified — `uv run pytest` green (1146 passed, 3 skipped); all `description=` strings end with period

### Files Changed

| File | Action | What |
|------|--------|------|
| `bot/cogs/sentinel.py` | Modified | 9 description periods |
| `bot/cogs/tickets.py` | Modified | Periods + 12 new descriptions for groups/subcommands |
| `bot/cogs/stellar.py` | Modified | 4 description periods |
| `bot/cogs/greetings.py` | Modified | Periods + 10 new descriptions for groups/subcommands |
| `bot/cogs/setup.py` | Modified | Period + 4 `@app_commands.describe()` + import |

### Commit

```
docs(cogs): normalize command descriptions and add missing annotations
```

### Deviations from Design

None — implementation matches design exactly.

### Issues Found

None.

---

## PR3 — Spanish Manual ✅

**Batch scope**: Phase 3 + Phase 4 — docs/MANUAL.md creation and verification
**Chain strategy**: stacked-to-main
**Status**: Complete

### Tasks Completed

- [x] 3.1 Create `docs/MANUAL.md` with outline: Vista general, Inicio rápido, Config, Estado del bot, Casos de uso (users), Casos de uso (mod/admin), Comandos, Deuda conocida
- [x] 3.2 Write §1–§4 (overview, quick start, config, bot state); reference `/help`
- [x] 3.3 Write §5–§6 use cases — task → command → result format
- [x] 3.4 Write §7 command reference tables (invocation, params, audience, result); include all commands + ticket groups/subcommands
- [x] 3.5 Write §9 known debt
- [x] 3.6 Review — all 47 commands appear; all 9 required sections present per spec
- [x] 4.1 `uv run pytest` — all green (1146 passed, 3 skipped, 3 warnings)
- [x] 4.2 `docs/MANUAL.md` exists, non-empty, has required headings (9 sections verified)
- [x] 4.3 Grep: no `description=` missing trailing period on command decorators

### TDD Cycle Evidence

N/A — Phase 3+4 is docs-only + verification. No code to test.

### Files Changed

| File | Action | Lines | What |
|------|--------|-------|------|
| `docs/MANUAL.md` | Created | ~430 | Spanish manual with 9 sections covering all commands |

### Command Coverage

| Cog | Commands Documented |
|-----|-------------------|
| Core | `/ping`, `/status`, `/help`, `/sync` (4) |
| Sentinel | `/warn`, `/unwarn`, `/mute`, `/unmute`, `/kick`, `/ban`, `/lock`, `/unlock`, `/modlogs` (9) |
| Tickets | `/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category`, `/configure_fields` (group+set), `/subticket` (group+create), `/reopen`, `/transfer`, `/note` (group+add+list+delete) (14) |
| Stellar | `/daily`, `/coins`, `/leaderboard`, `/rank` (4) |
| Greetings | `/welcome` (group+channel+toggle+message), `/goodbye` (group+channel+toggle+message), `/welcome_test`, `/goodbye_test` (10) |
| Utility | `/avatar`, `/serverinfo`, `/userinfo` (3) |
| Ocio | `/dados`, `/banana` (2) |
| Setup | `/setup` (1) |
| **Total** | **47 commands** |

### Deviations from Design

Minor: the spec and exploration mentioned "28 commands across 7 cogs" but the actual source has 8 cogs and 47 commands (counting groups and subcommands). The manual documents the real source inventory. This is consistent with the design's instruction to "use the command tree in source—not the stale count."

### Issues Found

None.

### Workload / PR Boundary

- **Mode**: chained PR slice (stacked-to-main) — PR 3 of 3
- **Work unit**: PR 3 — Spanish manual + final verification
- **Boundary**: `docs/MANUAL.md` (new file) + task checkbox updates
- **Review budget**: ~430 lines (docs-only, low cognitive burnout)

---

## Summary

| PR | Scope | Status | Tests |
|----|-------|--------|-------|
| PR 1 | Avatar TDD fix | ✅ Complete | 11/11 pass |
| PR 2 | Description polish + annotations | ✅ Complete | 1146 pass |
| PR 3 | Spanish manual + verification | ✅ Complete | 1146 pass |

**All phases complete. Ready for sdd-verify.**
