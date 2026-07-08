# Proposal: Tooling Rigor Upgrade

## Intent

NebulosaBot's QA tooling lags behind the bak-cli standard (Go). Ruff rules miss security/comprehensions/complexity, mypy suppresses errors project-wide, pre-commit only lints 4 files, coverage gates are 70% (target 75%), CI skips Python 3.13 (the production runtime), and there is no `.github/workflows/ci.yml` with a proper matrix. This change closes those gaps without touching runtime code.

## Scope

### In Scope
- W2: Add 14 ruff rule groups (S, C4, C90, RET, T20, ARG, DTZ, EM, T10, TRY, RSE, FLY, PERF, FURB) with `max-complexity=15` and per-file test ignores
- W3: Enable `strict = true` in mypy; scope `attr-defined` suppression per-file
- W5: Expand pre-commit ruff/mypy hooks from hardcoded 4-file list to `^(bot/|tests/)`
- W6: Raise `--cov-fail-under` from 70 to 75 in CI, Makefile, and pyproject.toml
- W7: Add Python 3.13 to CI matrix (currently 3.11, 3.12, 3.14; production runs 3.13)
- W4: Align Makefile `test`/`cov` targets with pyproject.toml coverage gate (75%)

### Out of Scope
- Runtime bugfixes (C1-C4, S1) → already in PR #18 (`runtime-bugfixes`)
- Large cog refactors (tickets.py 1953 lines, sentinel.py 843 lines)
- Adding `radon`/`vulture` for complexity/dead code detection
- Dockerfile.ci (not needed for Discord bot)

## Capabilities

### Modified Capabilities
- `pyproject-toml-qa-config`: ruff rule expansion, mypy strict mode, coverage gate raise to 75%
- `pre-commit-config-file`: hook file-scope expansion from 4-file allowlist to `^(bot/|tests/)`
- `qa-ci-pipeline`: coverage gate raise, Python 3.13 added to matrix
- `ci-workflow-file`: Python 3.13 added to matrix, coverage gate raise
- `makefile-dx`: coverage gate alignment to 75%

### New Capabilities
- None (all changes modify existing capabilities)

## Approach

**Incremental with debt-clearing pass.** Enable new ruff rules first — this will surface existing violations. Run `ruff check --fix` for auto-fixable ones, manually fix the rest, then enable strict mode. Mypy strict will also surface new errors; scope them per-file with targeted `[[tool.mypy.overrides]]` blocks rather than project-wide suppression. Pre-commit and CI changes are mechanical edits to YAML. Coverage gate bump from 70→75 is safe (current actual coverage is 74.59%, already above threshold).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | ruff rules, mypy strict, coverage gate |
| `.pre-commit-config.yaml` | Modified | hook file-scope patterns |
| `.github/workflows/ci.yml` | Modified | Python 3.13 matrix, coverage gate |
| `Makefile` | Modified | coverage gate alignment |
| `bot/**/*.py` | Modified | violations surfaced by new ruff rules (debt-clearing) |
| `tests/**/*.py` | Modified | violations + per-file mypy overrides |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| New ruff rules surface hundreds of violations | High | Use `ruff check --fix` first; manual fix remainder; `# noqa` only for justified exceptions |
| Mypy strict surfaces type errors across codebase | High | Per-file `[[tool.mypy.overrides]]` for existing debt; fix forward for new code |
| Coverage gate 75% fails if coverage dips slightly | Low | Current 74.59% is already at threshold; a few new tests will secure margin |
| Pre-commit becomes slower with full file set | Low | Hooks are fast; ruff/mypy are incremental |

## Rollback Plan

1. Revert `pyproject.toml` to prior ruff/mypy/coverage config
2. Revert `.pre-commit-config.yaml` file-scope patterns
3. Revert `.github/workflows/ci.yml` matrix and coverage gate
4. Revert `Makefile` coverage gate
5. No data migrations or runtime changes — rollback is zero-risk

## Dependencies

- None (pure tooling config changes)

## Success Criteria

- [ ] `ruff check bot/ tests/` passes with zero violations
- [ ] `mypy --strict bot/ tests/` passes (with scoped per-file overrides only)
- [ ] `pre-commit run --all-files` passes with hooks scoped to `^(bot/|tests/)`
- [ ] CI matrix runs Python 3.11, 3.12, 3.13, 3.14
- [ ] `--cov-fail-under=75` enforced in CI, Makefile, and pyproject.toml
- [ ] `make ci` passes locally

## Proposal Question Round

These questions shaped the assumptions below — review before proceeding to specs:

1. **Ruff: strict all-at-once vs incremental?** → Assumption: **incremental**. Enable all rules, run `ruff check --fix`, manually fix remainder. Use `# noqa` only for justified exceptions (not blanket debt).
2. **Mypy strict: fix-all-first vs per-file overrides?** → Assumption: **per-file overrides**. Enable `strict = true`, scope existing violations with `[[tool.mypy.overrides]]` per module. Fix forward for new code.
3. **CI workflow: create or defer to Makefile?** → Assumption: **the file already exists** (`.github/workflows/ci.yml`). Modify it — add Python 3.13, raise coverage gate. No new file creation needed.
