# Tasks: cleanup-stability — Hygiene & Stability (S1 L3)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total | ~1,140 (80+330+330+200+200) |
| Risk | Low (≤330 vs 600) |
| Chained | Yes 5× PR1a→PR1b→PR1c→PR2→PR3 |
| Delivery | auto-chain stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| U | Goal | PR | Test | Harness | Rollback |
|------|------|----|------|---------|----------|
| 1 | Hygiene+gates | PR1a | `pre-commit run --all-files` | `git ls-remote --heads origin` | `pre-commit.yaml`,`ci.yml` |
| 2 | Format A 13 | PR1b | `ruff format --check` | `ruff format --check` | 13 files |
| 3 | Format B 12+lint | PR1c | `ruff check bot tests` | `ruff check --statistics` | 12 files |
| 4 | Ratchet+types+DRY | PR2 | `mypy bot tests` | `pytest -k cache -q` | `pyproject.toml`,`context.py` |
| 5 | Inventory+RLS | PR3 | `pytest -k rls -q` | `python -m py_compile bot/__main__.py` | `bot/core/db/` no DDL |

## Phase 1: PR1a — Hygiene & Gates

- [x] 1.1 RED git helper rejects ambiguous origin/SHA — `pytest -k git_hygiene`
- [x] 1.2 `git diff 8cb5674..master` + `archive/2026-07-pr2a/b` + `ls-remote` + `prune --dry-run` →7 stale
- [x] 1.3 Pin Ruff `0.15.20` `check`→`format --check` `files: "^(bot/|tests/)"` — `pre-commit run --all-files`
- [x] 1.4 Full `bot/`+`tests/` gates `ci.yml`+`Makefile` — `gh workflow view ci`
- [x] 1.5 Branch pr1a `f83e767`; `chore: gates pin ruff 0.15.20`; `gh pr create --base master`

## Phase 2: PR1b — Format A

- [x] 2.1 `ruff format` 13 files — `ruff format --check bot tests`
- [x] 2.2 Branch pr1b; `style: format A (13)`; `gh pr create --base master` 📍PR1a

## Phase 3: PR1c — Format B+Lint

- [x] 3.1 RED `F401`/`I001`/`E501` 12 files+fix — `ruff check bot tests`
- [x] 3.2 Branch pr1c; `style: format B +F401/I001/E501`; `gh pr create --base master`

## Phase 4: PR2 — Ratchet+Mypy+DRY

- [x] 4.1 RED `Context[NebulosaBot]`+`cache_key`+`dispatch_greeting` — `pytest -k "context or cache" -q` (7 RED→GREEN)
- [x] 4.2 Ratchet `pyproject.toml` drop `RSE→RET→SIM` keep `TRY003` — `ruff check bot tests` (bot 0, total 6 deferred → 0 via fix)
- [x] 4.3 `context.py`+23 cogs `Context[NebulosaBot]` drop `type: ignore[arg-type]` — `mypy bot tests` 57→30 (bot 0, tests 30 remain)
- [x] 4.4 DRY `cache.py` `cache_key`+`greeting_service.py` TTL300s/30s — `pytest -q` (1783 passed)
- [x] 4.5 Branch pr2; `chore: ratchet`+`fix: Context`+`refactor: DRY`; `gh pr create --base master`

## Phase 5: PR3 — Inventory+RLS no DDL

- [x] 5.1 RED `Database.connect()` fail-closed+9-table denied — `pytest -k "service_role or rls" -q` (21 passed)
- [x] 5.2 RED guild-scope ID-only+`015_*` parity — `pytest -k inventory -q` (10 passed)
- [x] 5.3 `ServiceRoleValidationError` `db/base.py`+`config.py` — `pytest -k scope -q` (30 passed incl. pr3)
- [x] 5.4 `SchemaInventory` `schema_inventory.py` (`ticket_note CASCADE`/`SET NULL`,`015` drift, CDC 4, TTL) — `pytest --cov=bot --cov-fail-under=75 -q` (29 pr3 RED→GREEN, full 1812 passed)
- [x] 5.5 Branch pr3 `cleanup-stability-pr3` f15890c; `feat: inventory RLS+FK/TTL docs no DDL`; `gh pr create --base master` (stacked 📍 PR2, not pushed, GGA passed)

## Out of Scope (S2)

No `TicketService` split; no economy invalidation; no DDL before `015`.

## Per-PR Gates (stacked→master)

Each PR: `ruff check/format --check`,`mypy bot tests`,`pytest --cov=bot --cov-fail-under=75 -q`,`pre-commit run --all-files`,`gh pr checks --watch`. PR1a→PR1b→PR1c→PR2→PR3; retarget; `git revert <sha>`.
