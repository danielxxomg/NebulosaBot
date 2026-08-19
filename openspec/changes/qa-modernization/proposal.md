# Proposal: QA Modernization

## Intent
Legacy QA (mypy/bandit/pip-audit/pre-commit/extras) → ty/Ruff S/uv audit/zizmor/prek/tach/groups. Clear 426 hidden Ruff (bot/** S/C4/C90), stale uv.lock, tag-pinned Actions, zero boundaries. Keep strict typing, 87.85% cov, 2101 tests, green.

## Scope
### In Scope
- pyproject: extras→groups (PEP735), tool.uv, del mypy/bandit, add ty py311 + ANN/PYI/PGH003 preview, bot/** removal; uv.lock regen; CI setup-uv/ty/audit/tach/zizmor; fix code-quality trigger
- .pre-commit→prek.toml (builtin, pre-push uv check+tach); Makefile type/security/audit/tach; 5 delta specs

### Out of Scope
- Dashboard/Supabase/features/LOC beyond lint; publish nebulosabot[dev] (Pterodactyl requirements.txt pip-safe); tach beyond `utils→services` violation

## Capabilities
### New Capabilities
- `tach-boundaries`: 7 layers (cogs→views→services→utils→core→db→models), check+check-external
- `supply-chain-security`: uv audit CI+cron + zizmor SHA-pinned

### Modified Capabilities
- `pyproject-toml-qa-config`: mypy/bandit → ty+Ruff S+groups+preview
- `pre-commit-config-file`: .pre-commit+mypy/bandit → prek.toml
- `qa-pre-commit`: pre-commit → prek
- `ci-workflow-file`: mypy/bandit/pip-audit+setup-python → ty/uv audit/tach/zizmor+setup-uv
- `makefile-dx`: mypy/bandit → ty/uv audit/tach

## Approach
Stacked-to-main 6 PRs (auto-chain, 400/slice, 1200 total). PR1 first, PR2 before PR4, PR4 3 batches. Big-bang violates budget 3×; minimal duplicates configs.

| PR | Slice | LOC |
|----|-------|-----|
| 1 | uv | 250 |
| 2 | ty: py311 strict, cogs warn/rest error, close 28 deferred | 300 |
| 3 | prek | 200 |
| 4 | Ruff: A 274 B 97 C 55 | 600 |
| 5 | Security: Bandit 95↔S97 parity→del bandit, zizmor SHA | 200 |
| 6 | Tach: tach.toml, move parse_ticket_ref→core/models | 250 |

## Affected Areas
| Area | Impact | Desc |
|------|--------|------|
| pyproject.toml/uv.lock | Modified | groups, ty, preview, regen |
| prek.toml/.pre-commit | New/Removed | TOML builtin |
| tach.toml | New | 7 layers, 1 fix |
| ci.yml/code-quality.yml/Makefile | Modified | setup-uv/ty/tach/zizmor/master |
| bot/** | Modified | 426 fixes, 46 type:ignore |
| openspec/specs/* | Modified | 5 deltas |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| ty churn | Med | Pin ty==0.0.18 |
| cogs stub gaps | High | cogs warn/rest error |
| zizmor tag-pinned | High | SHA-pin PR5 |
| lock staleness | Med | uv lock --check |

## Rollback Plan
`git revert` per slice reverse: PR1 extras, PR2 mypy, PR3 YAML, PR4 ignores, PR5 bandit, PR6 tach.toml.

## Dependencies
setup-uv, ty, prek, tach, zizmor — current docs.

## Success Criteria
- [ ] ruff check 0, format --check 0, uv lock --check 0
- [ ] ty check bot/ tests/ 0 (cogs warn-tier)
- [ ] prek --all-files 0, pre-push uv check+tach 0
- [ ] bandit 0 deleted post-parity, uv audit 0 CI+cron, zizmor 0 SHA
- [ ] pytest 0 fail, cov ≥75%, matrix 3.11-3.14, PYTHONASYNCIODEBUG=1+filterwarnings error
- [ ] code-quality master, Ruff 0.15.20, 0 mypy/bandit/pip-audit
