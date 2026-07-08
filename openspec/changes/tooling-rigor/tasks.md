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

- [x] 3.1 Run `uv run ruff check --fix bot/ tests/` to apply auto-fixes (6 violations found, 4 auto-fixed)
- [x] 3.2 Verify `uv run ruff check bot/ tests/` — 2 remaining manual violations fixed (B007, RUF034)
- [x] 3.3 No broad noqa needed — all 6 violations cleared (PR #23 merged)

## Phase 4: Manual Debt Clearing — Core & Services

- [x] 4.1 Fix ruff/mypy violations in `bot/core/` (context.py — 2 mypy strict errors)
- [x] 4.2 Fix ruff/mypy violations in `bot/services/` (logging_service 5, greeting_service 4, image_service 1 = 10 mypy strict errors)
- [x] 4.3 Fix ruff/mypy violations in `bot/bot.py` (10 mypy strict errors)
- [x] 4.4 Apply targeted `[[tool.mypy.overrides]]` for modules with justified attr-defined debt (narrowed: removed bot.utils.* + bot.config overrides, narrowed bot.core/listeners/models)
- [x] 4.5 No temporary noqa markers needed — all fixes are real type narrowing

## Phase 5: Manual Debt Clearing — Cogs, Listeners, Utils

- [x] 5.1 Fix mypy violations in `bot/cogs/` (sentinel 51, greetings 6, stellar 5, utility 2 = 64 mypy strict errors)
- [x] 5.2 Fix mypy violations in `bot/listeners/` (audit_listener 8, xp_listener 5 = 13 mypy strict errors)
- [x] 5.3 Fix mypy violations in `bot/utils/` (covered by removed override — no direct violations)
- [x] 5.4 No temporary noqa markers needed — all fixes are real type narrowing

## Phase 6: Test Fixes + Final Verification

- [x] 6.1 Fix mypy violations in `tests/` (test_xp_listener 52, test_realtime 7, test_stellar_cog 5, test_ocio_cog 5, test_setup_cog 4, test_tickets_cog 3, test_greetings_cog 3, test_precommit_config 1, test_core_cog 1, test_ci_config 1 = 82 mypy strict errors)
- [x] 6.2 Narrow temporary broad suppressions — removed bot.utils.* + bot.config overrides, narrowed bot.core/listeners/models; only justified overrides remain (discord.py attr-defined, MagicMock untyped-decorator)
- [x] 6.3 Run `uv run ruff check bot/ tests/` — zero violations ✅
- [x] 6.4 Run `uv run mypy --strict bot/ tests/` — passes with scoped overrides only ✅ (Success: no issues found in 95 source files)
- [ ] 6.5 Run `uv run pre-commit run --all-files` — all hooks pass (pending verification)
- [x] 6.6 Run `uv run pytest` — all tests pass, coverage 81.72% ≥75% ✅
