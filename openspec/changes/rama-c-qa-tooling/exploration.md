# Exploration — rama-c-qa-tooling

- **Change:** `rama-c-qa-tooling`
- **Phase:** Exploration (sdd-explore)
- **Date:** 2026-06-27
- **Store:** OpenSpec
- **Reviewer budget:** 800 lines

## Context

User has a sibling Go project (`bak-cli`) with a strict QA stack: golangci-lint (22 linters), `go test -race -shuffle=on`, fuzz testing, benchmarks, coverage gates (75% global / 80% internal), govulncheck, gosec, Dockerfile.ci, `.githooks/pre-commit`, GitHub Actions matrix CI, GoReleaser. Requested an equivalent strict, TDD-first QA/coverage setup for NebulosaBot to produce a "bulletproof" bot via real simulation of commands, flows, and errors.

## Current state inventory

### Installed (Python)
- pytest 9.1.0, pytest-asyncio 1.4.0 — in `.venv` and `pyproject.toml [project.optional-dependencies.dev]`
- `.gga` — GGA pre-commit code reviewer (`*.py`, strict mode)
- AGENTS.md — has the new `## GGA Review Discipline` section (added this session)

### Missing (Python)
- Linters/formatters: none of ruff, black, isort, flake8
- Type checkers: none of mypy, pyright
- Security: no bandit, no pip-audit
- Coverage: pytest-cov not installed
- Test plugins: pytest-randomly, pytest-benchmark, hypothesis — none
- CI: no `.github/workflows/`, no `Dockerfile`, no `.pre-commit-config.yaml`, no Makefile/Taskfile

### Installed (TypeScript / dashboard)
- vitest 4.x, @testing-library/jest-dom, jsdom
- typescript 5.8.2, eslint 9, eslint-config-next 15
- `npx tsc --noEmit` clean

## Test surface

- Total tests: 257 passing (one-time install pytest-cov required for next phase)
- Test files: 11 (top-level `tests/`, all unit-level)
- Pattern: `MagicMock(spec=...)` + `AsyncMock`; conftest provides `cache`, `mock_db`, `mock_member`, `mock_interaction`, `mock_guild`
- Suite timing: ~2.5 s — CI-friendly

### Coverage gaps (real risk)
After installing pytest-cov and running `./.venv/bin/pytest --cov=bot --cov-report=term-missing`:

| Module                  | Coverage | Risk |
|-------------------------|----------|------|
| bot/cogs/core.py        | 0%       | 130 statements, zero covered |
| bot/cogs/tickets.py     | ~15%     | 1123 lines, persistent views untested |
| bot/core/database.py    | ~16%     | 820 lines, 35+ methods untested |
| bot/cogs/sentinel.py    | ~28%     | 843 lines, most commands untested |
| bot/bot.py              | partial  | error handlers / lifecycle only tested incidentally |

**Overall coverage: ~55%.**

## Real-simulation gaps ("bot a prueba de balas")

All tests today are unit-level. Missing flow tests:

1. **Moderation round trip:** Mod issues `/warn @target reason="spam"` → infraction row created, member warnings increment, log channel embed sent. Covered today: NONE.
2. **Ticket lifecycle:** User opens ticket panel → channel created → user closes via button → transcript generated, status updated. Covered today: NONE.
3. **XP / level-up:** Member sends 10 messages within cooldown window → XP crosses threshold → level-up event fires. Covered today: NONE.

## Candidate tool adoption plan

| Tool              | Catches                              | Tier        | TDD-first integration                                                 | Risk of naive adoption                                          |
|-------------------|---------------------------------------|-------------|------------------------------------------------------------------------|----------------------------------------------------------------|
| ruff              | lint + format + import order          | Mandatory   | `[tool.ruff]` in pyproject.toml, pre-commit hook                       | None — fast, well-integrated                                    |
| mypy              | type-system bugs (`ctx._guild_config`)| Mandatory   | `[tool.mypy]` with relaxations for `ctx.*`; pre-commit hook             | `--strict` would fail; need `disable_error_code = "attr-defined"` |
| bandit            | hardcoded creds, command injection   | Recommended | `[tool.bandit]` config; exclude tests/                                  | Low; few hits in test stubs                                     |
| pip-audit         | vulnerable pinned deps               | Mandatory   | GitHub Actions weekly + on push                                         | Requires uv.lock discipline (lockfile exists)                    |
| pytest-cov        | coverage measurement + gate           | Mandatory   | `addopts = "--cov=bot --cov-fail-under=55"` (ratchet later)             | Gate above current 55% blocks every PR — start at 55              |
| pytest-randomly   | order-dependent flakes                | Recommended | Default enabled in dev deps                                            | WARNING: exposes latent date/time flakes like the economy one. Adopt AFTER deterministic clock fixtures land |
| hypothesis        | property-based / fuzz equivalents     | Recommended | New `tests/property/test_*.py` for math functions (xp_for_level, streak)| Need deterministic input domain; conftest mocks already support it |
| pytest-benchmark  | perf regressions                      | Optional    | Scaffold `tests/bench/test_*.py`                                        | Baseline against Python 3.14 is unstable; defer to 3.12 venv    |
| pre-commit        | enforces all the above on staged files | Mandatory   | New `.pre-commit-config.yaml` (ruff + mypy + bandit + GGA shell hook)    | Coexistence with `.gga`: pre-commit wraps `.gga` as a `language: script` hook — proven pattern |
| GitHub Actions CI | matrix test/lint/typecheck/cov on push+PR | Mandatory | New `.github/workflows/ci.yml` (lint + type + test + cov + bandit + pip-audit) | Cost: matrix Python 3.11 + 3.12 + 3.14 to catch version-specific quirks |
| Docker CI         | Linux reproducibility                 | Optional    | New `Dockerfile.ci` (python:3.12-slim)                                  | Low value over GitHub runner; defer                            |
| asyncio debug     | exposes latent bugs (`-X dev`)        | Recommended | Optional workflow (off default)                                        | Toggle exposes many latent issues; default OFF first            |

## Recommended change scope

### IN scope (~400-800 lines)
1. `pyproject.toml` — add `[tool.ruff]`, `[tool.mypy]`, `[tool.bandit]` configs and dev deps for ruff, mypy, bandit, pytest-cov, hypothesis
2. `.pre-commit-config.yaml` (new) — wire ruff check, ruff format, mypy, bandit, GGA shell hook (existing `.gga` becomes a sub-hook)
3. `.github/workflows/ci.yml` (new) — matrix pytest on 3.11 / 3.12 / 3.14, plus mypy, ruff, bandit, pip-audit (weekly scheduled)
4. `Makefile` (new) for local DX (`make lint`, `make test`, `make cov`, `make ci`)
5. `tests/test_config.py` (new) — cover `bot/core/config.py` (0%)
6. `tests/test_database.py` (new) — cover `bot/core/database.py` (~16%); mocking strategies, no real Supabase
7. `tests/integration/test_moderation_flow.py` (new) — moderation round trip (1 flow demonstrator)
8. `tests/integration/test_ticket_flow.py` (new) — ticket lifecycle demonstrator
9. `tests/integration/test_xp_flow.py` (new) — XP/level up demonstrator
10. `tests/property/test_economy_math.py` (new) — hypothesis tests for `compute_xp_for_level`, `compute_level`
11. `tests/conftest.py` (extend) — `frozen_clock` fixture for time-deterministic property tests, plus optional `mock_db_get` factory reducing duplication across cogs

### OUT of scope (defer)
- Dashboard TS QA beyond existing vitest + tsc (separate SDD change if needed)
- Dockerfile.ci (low ROI vs GitHub runner)
- dpytest — current mock-discord pattern works at 257 tests
- Coverage gate above 55% (ratchet in subsequent changes)
- Wiring `on_app_command_error` to `tree.error` (V3 follow-up — separate SDD change)

### Estimate
- ~600 lines total: ~80 lines config (`pyproject.toml` + `.pre-commit-config.yaml`), ~120 lines CI/workflow, ~40 lines Makefile, ~360 lines new tests across 6 new files, bounded.

Fits the 800-line review budget; single PR recommended.

## Risks & open questions

1. **pytest-randomly date-flake resurfacing:** economy test had `timedelta(hours=20)` assumption; adoption of random ordering could expose other date/time bugs. Adopt pytest-randomly AFTER the deterministic clock fixture (`frozen_clock`) lands.
2. **mypy `--strict` would fail:** `bot/bot.py:256-264` uses `# type: ignore[attr-defined]` for `ctx._guild_config`. Need `disable_error_code = "attr-defined"` or refactor to subclass `NebulosaContext` cleanly (deferred to a refactor change).
3. **Coverage gate plateau:** starting at 55% is honest; raising incrementally per PR. Document ratchet strategy in CI README.
4. **GGA + pre-commit co-existence:** `.gga` is a custom shell hook. `pre-commit` framework will invoke the GGA shell script as a `language: script` hook — works for ordering. GGA caches cache results; pre-commit enforces on staged files.
5. **Hypothesis flake risk:** property tests for economy formulas need deterministic datetime inputs (use `frozen_clock` fixture).
6. **CI matrix cost:** Python 3.14 is bleeding edge; matrix could break unexpectedly on dependency updates. Pin Python 3.14 minor version and tighten `uv.lock`.

## Decision deferred to proposal phase

- Whether the change identifier is `rama-c-qa-tooling` vs an alternative naming
- Whether to split into chained PRs (config first, tests second, CI third) or single PR
- Whether `pip-audit` runs weekly only or also on PRs
- Whether `asyncio debug` mode (`-X dev`) is set on or off by default
- Whether to include `tests/bench/` (pytest-benchmark) as scaffolding-only or skip entirely

## Next phase

`sdd-propose` — distill into proposal with intent + scope + approach. Recommend:
- Identifier: `rama-c-qa-tooling`
- Delivery: single PR (~600 lines, under 800-line budget)
- Propose `ask-on-risk` delivery strategy if line count drifts up