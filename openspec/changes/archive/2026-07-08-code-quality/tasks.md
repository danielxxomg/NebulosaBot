# Tasks: Code Quality Consolidation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80 (20 prod + 60 test/CI) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

## Phase 1: TDD — Centralize `"nb!"` Constant

- [x] 1.1 **RED** — Create `tests/test_code_quality_config.py`: write test scanning `bot/**/*.py` asserting `"nb!"` literal exists ONLY in `bot/constants.py`; run, confirm FAIL
- [x] 1.2 **GREEN** — Create `bot/constants.py` with `FALLBACK_PREFIX = "nb!"` (zero imports, UPPER_SNAKE_CASE)
- [x] 1.3 **GREEN** — Update `bot/bot.py`: import `FALLBACK_PREFIX` from `bot.constants`, remove local `_FALLBACK_PREFIX`
- [x] 1.4 **GREEN** — Update `bot/models/guild.py`: import `FALLBACK_PREFIX`, replace both `"nb!"` literals (dataclass default + `from_row`)
- [x] 1.5 **GREEN** — Update `bot/core/db/guild_db.py`: import `FALLBACK_PREFIX`, replace upsert dict literal
- [x] 1.6 **GREEN** — Update `bot/services/guild_service.py`: import `FALLBACK_PREFIX`, replace both occurrences (lines 87, 138)
- [x] 1.7 **GREEN** — Update `bot/cogs/core.py`: import `FALLBACK_PREFIX`, replace `_resolve_prefix` fallback
- [x] 1.8 **REFACTOR** — Run `uv run pytest tests/test_code_quality_config.py -v`; verify test GREEN; run full suite `uv run pytest` — all pass

## Phase 2: TDD — Deduplicate `_resolve_avatar_url`

- [x] 2.1 **RED** — Add test to `tests/test_code_quality_config.py`: scan `bot/**/*.py` asserting `_resolve_avatar_url` def exists ONLY in `bot/services/greeting_service.py`; run, confirm FAIL
- [x] 2.2 **GREEN** — Update `bot/cogs/greetings.py`: delete local `_resolve_avatar_url` definition (~line 188), import from `bot.services.greeting_service`
- [x] 2.3 **REFACTOR** — Run `uv run pytest tests/test_code_quality_config.py -v`; verify test GREEN; run full suite `uv run pytest` — all pass

## Phase 3: CI — Report-Only Quality Workflow

- [x] 3.1 **RED** — Add test to `tests/test_code_quality_config.py`: parse `.github/workflows/code-quality.yml`, assert jscpd + vulture steps exist with `continue-on-error: true`; run, confirm FAIL
- [x] 3.2 **GREEN** — Create `.github/workflows/code-quality.yml`: jscpd (npx, threshold 5% bot/ 10% tests/) + vulture (pip, `bot/` target), both `continue-on-error: true`, triggers on `pull_request`
- [x] 3.3 **REFACTOR** — Run `uv run pytest tests/test_code_quality_config.py -v`; all structural tests GREEN

## Phase 4: Regression & Final Verification

- [x] 4.1 Run `uv run pytest --cov=bot --cov-report=term` — 977 tests pass, coverage 84.13% ≥ 75%
- [x] 4.2 Run `uv run ruff check bot/` — clean
- [x] 4.3 Run `uv run mypy bot/` — clean
- [x] 4.4 Run `uv run bandit -r bot/` — clean
- [x] 4.5 Verify: `grep -r '"nb!"' bot/` returns only `bot/constants.py`
- [x] 4.6 Verify: `grep -r '_resolve_avatar_url' bot/` returns only `bot/services/greeting_service.py`

## Phase 5: Git Hygiene (Optional — Operator Actions)

- [ ] 5.1 Delete 15 merged remote branches (see exploration.md §3 for exact list)
- [ ] 5.2 Drop 3 stale stashes (`stash@{0}`, `stash@{1}`, `stash@{2}`)
- [ ] 5.3 Run `git branch -r` — confirm no stale merged branches remain
