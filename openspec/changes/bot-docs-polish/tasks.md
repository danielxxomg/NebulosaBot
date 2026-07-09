# Tasks: Bot Docs Polish

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

> ~600 lines are Spanish docs (low burnout). Code changes ~300 lines across 6 cogs. 3-slice split keeps each PR under 400 code lines.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Avatar TDD fix + tests | PR 1 | `utility.py` + `test_utility_cog.py` |
| 2 | Description polish + annotations across 5 cogs | PR 2 | String-only edits |
| 3 | Spanish manual | PR 3 | Docs-only |

---

## Phase 1: Avatar Fix (TDD)

- [x] 1.1 RED — `tests/test_utility_cog.py`: change 3 assertions from `embed.thumbnail.url` → `embed.image.url`, assert `?size=1024`
- [x] 1.2 GREEN — `bot/cogs/utility.py`: `set_thumbnail(url=avatar_url)` → `set_image(url=f"{avatar_url}?size=1024")`
- [x] 1.3 Verify — `uv run pytest tests/test_utility_cog.py` green

## Phase 2: Description Polish + Annotations

- [x] 2.1 `bot/cogs/sentinel.py` — Add trailing period to all 9 command descriptions
- [x] 2.2 `bot/cogs/tickets.py` — Add periods; add missing `description=` for `configure_fields`, `subticket`, `reopen`, `transfer`, `note` and subcommands
- [x] 2.3 `bot/cogs/stellar.py` — Add period to `daily`, `coins`, `leaderboard`, `rank`
- [x] 2.4 `bot/cogs/greetings.py` — Add periods/descriptions for test commands, welcome/goodbye groups, subcommands
- [x] 2.5 `bot/cogs/setup.py` — Add period; add `@app_commands.describe()` for `ticket_category`, `mod_role`, `log_channel`, `language`
- [x] 2.6 Verify — `uv run pytest` green; spot-check all `description=` end with period

## Phase 3: Spanish Manual

- [x] 3.1 Create `docs/MANUAL.md` with outline: Vista general, Inicio rápido, Config, Estado del bot, Casos de uso (users), Casos de uso (mod/admin), Comandos, Deuda conocida
- [x] 3.2 Write §1–§4 (overview, quick start, config, bot state); reference `/help`
- [x] 3.3 Write §5–§6 use cases — task → command → result format
- [x] 3.4 Write §7 command reference tables (invocation, params, audience, result); include all commands + ticket groups/subcommands
- [x] 3.5 Write §8 known debt
- [x] 3.6 Review — all 47 commands appear; all required sections present per spec

## Phase 4: Final Verification

- [x] 4.1 `uv run pytest` — all green (1146 passed, 3 skipped)
- [x] 4.2 `docs/MANUAL.md` exists, non-empty, has required headings (9 sections)
- [x] 4.3 Grep: no `description=` missing trailing period on commands
