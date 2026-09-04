# Proposal: Unified Pending Close

## Intent

Close 6 verified pending items: coverage gaps on 4 files (54/62/69/72% vs ~80% clause at `test-suite-governance/spec.md:95`), ledger 61,478 (margin 2 vs ceiling), oxlint 321 findings awaiting blocking flip, 2 weak asserts, GGA discipline note. Math: 61,478 + 991 − 920 − 565 = **60,984** (< 61,480; aim ≤ 61,300 met).

## Scope

### In Scope

- S0 governance amendment (headroom, coexistence, buffer, GGA note)
- S1/S2/S5 cuts (~1,485 ln: fat-file ~920 + extended ~565)
- S3a/S3b probe resurrection (+991 ln from dc371d0)
- S4 oxlint fix-all-321 + blocking flip + re-stamp
- Weak-assert hardening (`test_live_catalog.py:87`, `test_i18n.py:537`)
- S6 ledger reconcile (re-measure mandatory)

### Out of Scope

- New features or behavior changes
- Branch salvage (8 landed/deleted, zero overlap per #5124)
- Upstream GGA report: mechanism CONFIRMED by extended repro 2026-09-04 (index poisoning + non-deterministic verdicts); report decision via consent envelope, pending user choice
- Dashboard pagination unit (excluded from ledger)

## Capabilities

### New Capabilities

None

### Modified Capabilities

- `test-suite-governance`: headroom rule (margin ≥100 before line-additive slices), 1500-vs-800 coexistence, aim-aspirational-with-buffer, GGA discipline note

## Approach

- S0 docs-only first; no line-additive work before headroom lands.
- S1 (cut A) → S2 (cut B + dc371d0 removals) → S5 extended cut (may run as S1.5; tasks phase decides).
- S3a (welcome, goodbye + hardening) → S3b (pickers, live_catalog).
- S4 oxlint fix-all + flip; split if >800. Stacked-to-master, ≤800/PR, strict TDD.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/test-suite-governance/spec.md` | Modified | Headroom, coexistence, buffer, GGA note |
| `tests/*` | Modified | Cuts, probes, assert hardening |
| `dashboard/*` | Modified | oxlint TS/JS fixes |
| `.github/workflows/code-quality.yml` | Modified | Blocking flip, baseline re-stamp |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Coverage jitter ±1 | Med | Per-slice `--cov`; revert-on-dip |
| Squash-chain drift (#5106) | Med | Per-slice ledger; S6 re-measure |
| Commit timeout | Med | Timeout ≥1800s; split S4 if >800 |
| Additive work before headroom | Low | Ceiling rule in task order |

## Rollback Plan

Revert in reverse stack order (S6 → S0); probes revert before cuts re-land. Re-measure ledger after any revert.

## Dependencies

- S0 blocks S3/S4; S1/S2/S5 fund S3a/S3b
- Evidence: Engram #5120/#5121/#5122/#5124/#5125, decisions #5123

## Success Criteria

- [ ] Coverage ≥80% on the 4 files
- [ ] Ledger < 61,480, ideally ≤ 61,300
- [ ] oxlint blocking green, 0 findings
- [ ] Weak asserts replaced with exact-equality/isinstance
