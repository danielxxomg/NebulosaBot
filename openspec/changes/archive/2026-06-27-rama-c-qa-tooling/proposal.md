# Proposal: rama-c-qa-tooling

## Intent

Integrate a strict TDD-first QA and coverage stack for NebulosaBot — linters, type checker, security scanner, coverage gate, property tests, integration flows, CI pipeline, and pre-commit enforcement — mirroring the user's Go project (`bak-cli`) discipline. Goal: a "bulletproof" bot proven by real simulation across unit, integration, and property-test layers, with CI as the enforcement gate.

## Scope

### In Scope

**PR1 — Bootstrap (~250 lines)**
- `pyproject.toml` — add `[tool.ruff]`, `[tool.mypy]`, `[tool.bandit]`, pytest `addopts` gate at 55%, `filterwarnings`, dev deps (ruff, mypy, bandit, pytest-cov, hypothesis, pytest-randomly)
- `.pre-commit-config.yaml` (new) — ruff check, ruff format, mypy, bandit, GGA shell hook (`language: script`)
- `Makefile` (new) — `lint`, `type`, `test`, `cov`, `ci` targets
- `.github/workflows/ci.yml` (new) — Python 3.11/3.12/3.14 matrix, `PYTHONASYNCIODEBUG=1`, pytest --cov, mypy, ruff, bandit, pip-audit (push + weekly)
- `tests/conftest.py` — extend with `frozen_clock` fixture
- `tests/property/test_economy_math_smoke.py` (new) — 2-3 hypothesis proof-of-pattern tests

**PR2 — Coverage #1 (~400 lines)**
- `tests/test_config.py` (new) — units for `bot/core/config.py` (0% → 80%)
- `tests/test_database.py` (new) — units for `bot/core/database.py` (16% → 45%)
- Coverage gate raised to **60%**

**PR3 — Coverage #2 + Integration (~700 lines)**
- `tests/integration/test_moderation_flow.py` (new) — `/warn` round trip (cog → service → mocked DB → log embed)
- `tests/integration/test_ticket_flow.py` (new) — panel open → channel create → close → transcript
- `tests/integration/test_xp_flow.py` (new) — 10 messages → XP threshold → level-up event
- `tests/test_sentinel_cog.py` (extend) — sentinel 28% → 60%
- `tests/test_tickets_cog.py` (extend/new) — tickets 15% → 55%
- `tests/property/test_economy_math.py` (extend) — full hypothesis battery for `compute_xp_for_level`, `compute_level`
- Coverage gate raised to **70% strict**

### Out of Scope
- Dashboard TS QA beyond existing vitest + tsc (defer to `rama-d-dashboard-qa`)
- `Dockerfile.ci` (low ROI vs GitHub runner)
- dpytest — current mock-discord pattern works at 257 tests
- Coverage gate above 70% (ratchet in subsequent changes)
- Wiring `on_app_command_error` to `tree.error` (defer to `rama-a-app-error-wiring`)
- pytest-benchmark (Python 3.14 unstable baseline)

## Capabilities

### New Capabilities
- `qa-ci-pipeline`: GitHub Actions matrix CI — lint, typecheck, security, coverage, pip-audit on push/PR + weekly scheduled
- `qa-pre-commit`: Pre-commit framework wrapping ruff, mypy, bandit, and existing GGA shell hook
- `qa-property-tests`: Hypothesis property-based tests for economy math functions (`compute_xp_for_level`, `compute_level`)
- `qa-integration-flows`: Full round-trip integration tests for moderation, ticket, and XP flows
- `qa-config-coverage`: Unit tests for `bot/core/config.py` (0% → 80%)
- `qa-database-coverage`: Unit tests for `bot/core/database.py` (16% → 45%)

### Modified Capabilities
- `pyproject.toml`: add linter/type-checker/security configs, pytest gate, dev deps, filterwarnings
- `tests/conftest.py`: extend with `frozen_clock` deterministic datetime fixture
- `.pre-commit-config.yaml` (new): enforcement layer for all QA tools
- `Makefile` (new): local DX targets
- `.github/workflows/ci.yml` (new): CI enforcement

## Approach

**Why chained PRs over single PR:** ~1350 lines total exceeds the 800-line review budget. Three force-chained child PRs (PR1→PR2→PR3, tracker branch `rama-c-qa-tooling` merges to master only at archive) keep each slice reviewable with focused context. PR1 bootstraps tooling, PR2 fills coverage gaps, PR3 adds integration flows — each builds on the previous gate.

**Ratchet gate progression (55 → 60 → 70):** Starting at the honest 55% baseline prevents blocking every PR on day one. Each slice raises the floor: PR1 holds 55%, PR2 pushes to 60% with config+database coverage, PR3 reaches 70% with integration flows and extended cog tests. Incremental ratcheting avoids "big bang" coverage debt.

**pytest-randomly + frozen_clock in PR1:** Adopting random test ordering up front catches order-dependent flakes immediately. The `frozen_clock` fixture (freeze `datetime.now(timezone.utc)`) MUST land in PR1's conftest before randomization exposes latent date-time dependencies (cf. the economy `timedelta(hours=20)` flake). Any test using `datetime.now` instruments via `frozen_clock`.

**asyncio debug ON in CI:** `PYTHONASYNCIODEBUG=1` in the matrix env forces latent coroutine bugs (forgotten awaits, unclosed resources) to surface during CI rather than in production. Known benign warnings (discord.py's `asyncio.iscoroutinefunction` deprecation) are muted via `filterwarnings` in pyproject.toml.

**GGA + pre-commit co-existence:** The existing `.gga` shell hook is wrapped as a `language: script` sub-hook inside `.pre-commit-config.yaml`. Pre-commit enforces ordering; GGA caches its own results. Proven pattern — no conflict.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | Add `[tool.ruff]`, `[tool.mypy]`, `[tool.bandit]`, pytest gate + filterwarnings + dev deps |
| `.pre-commit-config.yaml` | New | Ruff, mypy, bandit, GGA shell hook integration |
| `Makefile` | New | Local DX: lint, type, test, cov, ci targets |
| `.github/workflows/ci.yml` | New | Matrix CI (3.11/3.12/3.14), all checks + pip-audit |
| `tests/conftest.py` | Modified | Add `frozen_clock` fixture |
| `tests/test_config.py` | New | Config module coverage (0% → 80%) |
| `tests/test_database.py` | New | Database module coverage (16% → 45%) |
| `tests/test_sentinel_cog.py` | Modified | Sentinel coverage 28% → 60% |
| `tests/test_tickets_cog.py` | Modified/New | Tickets coverage 15% → 55% |
| `tests/integration/test_moderation_flow.py` | New | Moderation round-trip flow test |
| `tests/integration/test_ticket_flow.py` | New | Ticket lifecycle flow test |
| `tests/integration/test_xp_flow.py` | New | XP/level-up flow test |
| `tests/property/test_economy_math.py` | New/Modified | Hypothesis tests for economy formulas |
| `tests/property/test_economy_math_smoke.py` | New | Proof-of-pattern hypothesis scaffold |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `asyncio debug` leaks warnings despite filterwarnings allowlist | Medium | Maintain allowlist; new warnings surface as CI failures — fix forward |
| Python 3.14 matrix cell fails on dependency updates | Medium | Pin minor version; tighten `uv.lock`; treat as canary |
| 70% gate for tickets.py requires panel-message-id tests (time/ordering dependent) | Medium | Use `frozen_clock` + deterministic mock IDs |
| mypy `attr-defined` relaxation hides real bugs in `ctx._guild_config` | Low | Documented tech debt; scoped to `bot/bot.py:256-264` only |

## Rollback Plan

1. Each PR is a standalone branch — close the PR to discard changes
2. Tracker branch `rama-c-qa-tooling` is deleted without merging to master
3. Coverage gate is config-only (`pyproject.toml` `addopts`) — revert to remove gate
4. Pre-commit hooks are opt-in per developer (`pre-commit install`) — no forced activation
5. CI workflow is file-only — delete `.github/workflows/ci.yml` to remove

## Dependencies

- No new runtime dependencies (all tools are dev-only)
- `uv.lock` must be updated with new dev deps
- Existing `.gga` shell hook remains functional as standalone

## Success Criteria

- [ ] `make ci` passes locally (lint + type + test + cov + bandit)
- [ ] CI green on all 3 Python versions (3.11, 3.12, 3.14)
- [ ] Coverage ≥ 70% after PR3 merges (strict gate enforced)
- [ ] Pre-commit runs all hooks including GGA on staged files
- [ ] 3 integration flow tests pass (moderation, tickets, XP)
- [ ] Hypothesis property tests pass for economy math functions
- [ ] `frozen_clock` eliminates date-time flake risk under pytest-randomly
