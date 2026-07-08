# Archive Report — tooling-rigor

**Change**: `tooling-rigor`
**Archived**: 2026-07-08
**Verdict**: PASS WITH WARNINGS (6 non-blocking)
**PRs merged**: #19 (PR1 config+guards), #23 (PR2 ruff), #24 (PR3 mypy strict)

## Summary

NebulosaBot QA tooling upgraded to match bak-cli standard. Ruff expanded with 14 new rule groups (S, C4, C90, RET, T20, ARG, DTZ, EM, T10, TRY, RSE, FLY, PERF, FURB) plus mccabe max-complexity=15. Mypy strict mode enabled with per-file overrides replacing the project-wide `disable_error_code`. Pre-commit hooks expanded from a 4-file allowlist to `^(bot/|tests/)`. CI matrix added Python 3.13 (the production runtime). Coverage gate ratcheted from 70% to 75% across pyproject.toml, CI, and Makefile.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| pyproject-toml-qa-config | Updated | 3 requirements modified (ruff config expanded, mypy strict+per-file overrides, coverage 75) |
| pre-commit-config-file | Updated | 2 requirements modified (ruff hooks + files pattern, mypy hook + files pattern) |
| ci-workflow-file | Updated | 1 requirement modified (matrix +3.13), 1 requirement added (coverage gate 75) |
| makefile-dx | Updated | 1 requirement modified (cov target enforces 75% floor) |
| qa-ci-pipeline | Updated | 1 requirement modified (matrix +3.13), 1 requirement modified (coverage 75) |

## Archive Contents

- proposal.md
- specs/ (5 delta specs)
- design.md
- tasks.md (all tasks checked)
- verify-report.md (3 verification rounds, final PASS WITH WARNINGS)
- archive-report.md

## Source of Truth Updated

The following main specs now reflect the final implemented behavior:
- `openspec/specs/pyproject-toml-qa-config/spec.md`
- `openspec/specs/pre-commit-config-file/spec.md`
- `openspec/specs/ci-workflow-file/spec.md`
- `openspec/specs/makefile-dx/spec.md`
- `openspec/specs/qa-ci-pipeline/spec.md`

## Verification Rounds

1. **Round 1 (FAIL)**: Unchecked tasks, behavior changes in type-narrowing edits
2. **Round 2 (FAIL)**: mypy strict failed locally (21 errors), task 6.5 unchecked, sentinel behavior residual
3. **Round 3 (PASS WITH WARNINGS)**: All CRITICAL resolved; 6 non-blocking warnings recorded

## Warnings (non-blocking, carried forward)

1. pre-commit unavailable in local environment (task 6.5 reconciled — gates verified via ruff + mypy)
2. Wildcard mypy overrides remain broad (bot.services.*, tests.*, bot.cogs.*)
3. Coverage below 80% on changed files: bot/bot.py (73%), bot/cogs/sentinel.py (72%), bot/core/context.py (77%)
4. RuntimeWarnings from unawaited AsyncMock in test_ticket_service.py
5. React act(...) warnings in dashboard tests
6. pyproject.toml.bak and untracked files present at verification time

## Stale Checkbox Reconciliation

Task 6.5 was reconciled during archive. The task was left unchecked because `pre-commit` is not installed in the environment. The verify-report 3rd remediation (PASS WITH WARNINGS) confirms that the equivalent non-mutating gates (ruff check, mypy --strict) passed. The orchestrator explicitly approved proceeding with this reconciliation.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Ready for the next change.
