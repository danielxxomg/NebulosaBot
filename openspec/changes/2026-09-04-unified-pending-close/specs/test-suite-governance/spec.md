# Delta for test-suite-governance

## MODIFIED Requirements

### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 175/62,384/3063/81.99% @9871add → lines strictly below 61,480 (the ONLY gate); files within 169-181. Ledger budget 1500 lines/slice bounds suite-size delta per slice and MUST NOT be conflated with the 800 diff-lines/PR review budget — distinct dimensions (suite growth vs reviewer load). Final aim ≤61,300 is ASPIRATIONAL with documented buffer, explicitly NOT a gate. Line-additive slices MUST satisfy the Slice Headroom Gate first. Restoration is parametrization-first: zero D3 deletions by default; any deletion still requires D3 proof per the FAIL-regardless-of-metrics gate below. Coverage scope: `bot/views/setup_modules/welcome.py`, `bot/views/setup_panel.py`, `bot/views/setup_modules/goodbye.py`, `bot/services/live_catalog.py` each to ~80%, funded by probes resurrected from dc371d0. The dashboard pagination unit (`dashboard/__tests__/app/audit-panel.test.tsx:122-169`) is excluded from the Python ledger.

(Previously: no headroom rule; 1500-vs-800 coexistence undocumented; aim read as gate.)

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Hard ceiling gates, aim does not

- GIVEN all slices merged
- WHEN metrics measured
- THEN lines strictly below 61,480 with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)

## ADDED Requirements

### Requirement: Slice Headroom Gate

Before any line-additive test slice lands, the ledger MUST show margin ≥100 lines above the ceiling (lines ≤61,380 at ceiling 61,480). Each slice MUST measure before/after with ledger trail; a slice that would breach the ceiling MUST NOT land.

#### Scenario: Headroom satisfied

- GIVEN ledger shows margin ≥100 above ceiling
- WHEN line-additive slice lands with before/after ledger
- THEN slice accepted, trail recorded

#### Scenario: Headroom blocks additive slice

- GIVEN ledger margin <100 above ceiling
- WHEN line-additive slice proposed
- THEN slice MUST NOT land until cuts restore margin

### Requirement: Assert Strength Standard

Weak `is not None` asserts MUST be replaced with exact-equality or isinstance where a concrete expected value exists (mirrors `tests/test_i18n.py:525`); hardening rides the probe slices.

#### Scenario: Weak assert hardened

- GIVEN probe slice touches a file with `is not None` asserts
- WHEN a concrete expected value exists
- THEN asserts use exact-equality/isinstance

### Requirement: Apply Staging Discipline

Apply commits MUST stage only intentional paths. The GGA hook MAY restore stale index snapshot entries (extended repro 2026-09-04: commit-time `invalid object` index poisoning; the isolated clean-index repro was degenerate). Every commit MUST be verified with `git show --stat HEAD` immediately after creation; a poisoned index MUST be repaired before further operations. Upstream defect report: decision pending via consent envelope (provider-defect discipline).

#### Scenario: Intentional staging only

- GIVEN apply commit prepared
- WHEN staged paths and post-commit `git show --stat HEAD` are inspected
- THEN only intentional paths appear; any hook-restored planning files are detected and reset before push
