# Proposal: tests-slim

## Intent

Slim pytest bloat without behavior loss. 2026-08-31 @2bb4e89: **184 files / 61,622 ln / 3005 / 2986+19 / cov 80.50%** (9881 prod ln). Audit #4711 (158/56,307, 2026-08-23) stale — +26/+5,315 ln since clean-1.0 + v1-postrelease-zero + ops-zero-lite. Every slice green + cov >=80.50% + ty/ruff/vulture 0.

## Scope

### In Scope

- S1 locale hoist — dedup `_load_i18n`+`_LOCALE_MATRIX` across 5 `*i18n.py` into `conftest.py`
- S2 factory hoist — replace local `_make_member` in ~7 greeting files + `ticket_helpers` with `conftest` builders
- S3 cluster param — collapse `TestDispatchWelcome` disabled-card cluster (~8) + economy twins into `parametrize`
- S4 deletions LAST — remove only proven-redundant source-greps (twin exists), per-batch `--cov` proof

### Out of Scope

- `mutmut` (deferred), `dashboard/` vitest, coverage tests, `bot/` change

## Capabilities

### New Capabilities

- None — tests-only.

### Modified Capabilities

- None.

## Approach

Parametrize first (S1-S3), delete LAST (S4) with `--cov=bot --randomly-seed=42` per batch. No deletion without proof. Pass count drops (N->1) — gates green + cov floor. `filterwarnings=error` stays.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/test_*i18n.py` (5) | Modified | Hoist `_load_i18n`/`_LOCALE_MATRIX` |
| `tests/test_greeting_*.py` + helpers | Modified | Use conftest factories; param cluster |
| `tests/test_pr3_*.py` (enumerated in spec) | Removed | Delete proven-redundant source-greps (twin exists) — `rank_renderer_wiring` is KEEP (behavioral guard) |
| KEEP: `test_ops_observability.py` (live-spec evidence: OO-R3 + Sentry gates), `property/test_economy_math.py` | Untouched | 191+/76 ln |
| `tests/conftest.py` | Modified | Add shared helpers |
| KEEP: `comma_timer`/`zero_hybrid`/`i18n_key_coverage`/`s3d1_guardrails` | Untouched | 42/49/416/325 ln |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cov dip on deletions (80.50% tight) | High | Measure `--cov` per batch; revert if <80.50 |
| Guard deleted by mistake | Med | KEEP checked; KEEP tests green |

## Rollback Plan

Tests-only reverts. S1-S3: `git revert <slice>`. S4: revert + re-measure `--cov`. Slice = commit boundary; never squash S4 into S1-S3.

## Dependencies

- Baseline `2bb4e89` green; `filterwarnings=error` + seed 42.

## Success Criteria

- [ ] S1-S3: -1500..-2000 ln, green + cov >=80.50% + ty/ruff/vulture 0
- [ ] S4: each deletion has proof + cov >=80.50%
- [ ] KEEP untouched/green; seed 42 green every slice
- [ ] Final: 180 files (in 169-181 range) / 60,939 ln — strict decrease from 61,622 with ledger; ~57-59.5k was computed from savings assumptions (2,618 deletable + 1,500-2,000 param) that measurement disproved: proof gate yielded 4/15 deletions, 11 documented survivors; further reduction parked pending new twin evidence

## Review Workload Forecast

| Slice | Forecast | Budget 1500 | Chained PRs |
|-------|----------|-------------|-------------|
| S1 locale hoist | ~400-600 | Within | Yes |
| S2 factory hoist | ~500-800 | Within | Yes |
| S3 cluster param | ~400-600 | Within | Yes |
| S4 deletions | ~200-500 | Within | Yes |
| **Total** | **~1500-2500** | **Sliced** | **Yes** |

Decision needed before apply: Yes — chained PRs (stacked-to-master), one slice per PR.
Chained PRs recommended: Yes.
400-line budget risk: Medium (per-slice within 1500; aggregate sliced).
