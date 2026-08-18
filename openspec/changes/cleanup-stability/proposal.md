# Proposal: cleanup-stability — Hygiene & Stability (S1 L3)

## Intent
`v0.2.0` `f83e767` green (1,761 tests, 88.47%) but gates curated: 27+3 Ruff, 658 format drift, 57 mypy, 9 tables RLS no-policy, FK drift. Enforce `bot/`+`tests/` gates.

## Scope
### In Scope
- Prune 7 stale `origin/*`; keep `archive/2026-07-pr2a/b` for `8cb5674`
- Ruff 0.8.6→0.15.20; `ci.yml`/`Makefile` → full scope (excl. `scripts/`)
- Split 25-file format (658) + `F401`/`I001`/`E501`
- Ratchet `RSE→RET→SIM` explicit TRY (`TRY003` deferred), `Context[NebulosaBot]`, DRY `cache_key`
- Inventory live vs disk; verify `015`; guild scoping; RLS `service_role` + tests; FK/TTL doc
### Out of Scope
- `TicketService` split → S2; economy 30s → S2; DDL before inventory

## Capabilities
### New Capabilities
- None — hygiene only.
### Modified Capabilities
- `pyproject-toml-qa-config`: ratchet, TRY/S, parameterized Context
- `pre-commit-config-file`: pin + hook
- `ci-workflow-file`/`qa-ci-pipeline`: blocking CI
- `database-layer`: RLS `service_role`, FK, guild scoping
- `cache-sync-realtime`/`cache-layer`: TTL doc

## Approach
Stacked to `main` (A2). 658 > 600 for 3 PRs → 5 slices. Refs: `Diagramas/DiagramaSecuencia.mmd`, `Diagramas/DiagramaEntidad-Relación.mmd`.
| PR | Work unit | Budget | Verify |
|----|-----------|--------|--------|
| PR1a | Prune + gates | ~80 | `git ls-remote`, `pre-commit --all` |
| PR1b | Format A (13) | ~330 | `ruff format --check` 0 |
| PR1c | Format B + lint | ~330 | `ruff check` 0 |
| PR2 | Ratchet + mypy + DRY | ~200 | `mypy` 0, `pytest` green |
| PR3 | Inventory + RLS/FK/TTL | ~200 | No DDL without `015` parity |
Diff `8cb5674..master` before deletes.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `.pre-commit-config.yaml` | Modified | Pin + hook |
| `ci.yml`, `Makefile` | Modified | Gates |
| `pyproject.toml` | Modified | Ratchet |
| `bot/cogs/*.py`, `checks.py` | Modified | `Context[NebulosaBot]` (23 callers) |
| `bot/core/db/*`, `realtime.py` | Modified/Doc | Scoping, `AsyncClientOptions` |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Format > budget | High | Split PR1b/c |
| TRY/S 136/95 | High | Explicit codes; defer TRY003/S101 |
| RLS exposure | Med | Deny-by-default + role check |
| FK deletes audit | Med | `ticket_note` CASCADE, `ticket_audit` SET NULL |

## Rollback Plan
Each PR `git revert` alone; DDL blocked until `resolved`.

## Dependencies
- Anchor `f83e767`; Supabase read; `005_rls_secure_default`

## Success Criteria
- [ ] `ruff format --check` 0; ratcheted `ruff check` 0
- [ ] `mypy bot tests` 0 no new `type: ignore[arg-type]`
- [ ] CI/pre-commit block on `bot/`+`tests/`
- [ ] RLS `service_role` + negative tests
- [ ] No DDL; `015` parity; `pytest` 1,761 cov≥75%

## Assumptions
5 PRs stacked-to-main (658>600/3). RLS `service_role` only. `SET NULL` retain. `pr2a/b` diff-first. `auto-chain`, hygiene-exempt `strict_tdd`.
