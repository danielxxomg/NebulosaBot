# Tasks: Tooling Rigor Upgrade

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 850–1250 (config ~50, debt-clearing ~800–1200) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Config upgrade + test guards | PR 1 | Enable rules in pyproject.toml, pre-commit, CI, Makefile; add validation tests; broad `noqa`/debt allowances so gates pass immediately |
| 2 | Auto-fixable ruff violations | PR 2 | `ruff check --fix`; remove broad allowances replaced by real fixes; ~86 auto-fixable lines |
| 3 | Manual fixes — core + services | PR 3 | `bot/core/`, `bot/services/`, `bot/bot.py`; targeted `noqa` or rewrites for remaining violations |
| 4 | Manual fixes — cogs + listeners + utils | PR 4 | `bot/cogs/`, `bot/listeners/`, `bot/utils/` |
| 5 | Test fixes + final gate verification | PR 5 | `tests/` debt, remove all broad suppressions, `ruff check` + `mypy --strict` + `pre-commit` + `pytest` all green |

## Phase 1: Test Guards (RED)

- [x] 1.1 Write `tests/test_ruff_config.py`: validate pyproject.toml ruff select includes all 14 new groups, max-complexity=15, per-file ignores for tests
- [x] 1.2 Write `tests/test_mypy_config.py`: validate strict=true, no global disable_error_code, per-file overrides exist for known debt modules
- [x] 1.3 Write `tests/test_precommit_config.py`: validate hook order (ruff check → ruff format → mypy), `files: ^(bot/|tests/)` pattern
- [x] 1.4 Write `tests/test_ci_config.py`: validate matrix includes 3.13, fail-fast disabled, coverage gate 75
- [x] 1.5 Write `tests/test_makefile_config.py`: validate `make cov` target passes `--cov-fail-under=75`

## Phase 2: Config Edits (GREEN for Phase 1 tests)

- [x] 2.1 `pyproject.toml`: add 14 ruff groups to `[tool.ruff.lint]` select, set `max-complexity=15`, add `per-file-ignores` for `tests/`
- [x] 2.2 `pyproject.toml`: set `[tool.mypy] strict = true`, remove global `disable_error_code`, add `[[tool.mypy.overrides]]` for `bot.bot`
- [x] 2.3 `pyproject.toml`: set `addopts = "--cov=bot --cov-fail-under=75"`
- [x] 2.4 `.pre-commit-config.yaml`: replace file allowlists with `files: "^(bot/|tests/)"` on ruff check, ruff format, mypy hooks
- [x] 2.5 `.github/workflows/ci.yml`: add `3.13` to matrix, pass `--cov-fail-under=75` to pytest
- [x] 2.6 `Makefile`: align `test` and `cov` targets with `--cov-fail-under=75`

## Phase 3: Auto-fix Ruff Violations

- [ ] 3.1 Run `uv run ruff check --fix bot/ tests/` to apply 86 safe+unsafe auto-fixes
- [ ] 3.2 Verify `uv run ruff check bot/ tests/` — document remaining violation count per rule group
- [ ] 3.3 Add broad `# noqa` or per-file ignores for remaining violations as temporary debt markers

## Phase 4: Manual Debt Clearing — Core & Services

- [ ] 4.1 Fix ruff violations in `bot/core/` (realtime.py, gateway.py, cache.py, supabase.py)
- [ ] 4.2 Fix ruff violations in `bot/services/` (guild_service.py, xp_service.py, warn_service.py)
- [ ] 4.3 Fix ruff violations in `bot/bot.py`
- [ ] 4.4 Apply targeted `[[tool.mypy.overrides]]` for modules with justified attr-defined debt
- [ ] 4.5 Remove temporary `noqa` markers replaced by real fixes in this batch

## Phase 5: Manual Debt Clearing — Cogs, Listeners, Utils

- [ ] 5.1 Fix ruff violations in `bot/cogs/` (moderation.py, tickets.py, sentinel.py, xp.py, etc.)
- [ ] 5.2 Fix ruff violations in `bot/listeners/` (xp_listener.py, join_listener.py)
- [ ] 5.3 Fix ruff violations in `bot/utils/` (embeds.py, converters.py, config.py)
- [ ] 5.4 Remove temporary `noqa` markers replaced by real fixes in this batch

## Phase 6: Test Fixes + Final Verification

- [ ] 6.1 Fix ruff/mypy violations in `tests/` (test_xp_listener.py, test_guild_service.py, etc.)
- [ ] 6.2 Remove ALL temporary broad suppressions; only narrow justified `noqa`/overrides remain
- [ ] 6.3 Run `uv run ruff check bot/ tests/` — zero violations
- [ ] 6.4 Run `uv run mypy --strict bot/ tests/` — passes with scoped overrides only
- [ ] 6.5 Run `uv run pre-commit run --all-files` — all hooks pass
- [ ] 6.6 Run `uv run pytest` — all tests pass, coverage ≥75%
