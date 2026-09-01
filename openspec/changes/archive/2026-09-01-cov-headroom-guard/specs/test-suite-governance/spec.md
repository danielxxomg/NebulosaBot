# Delta for test-suite-governance

## MODIFIED Requirements

### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 184/61,622/3005/80.50% @2bb4e89 → lines strictly below 61,800 until tests-slim fase 2 lands (deleting the 11 documented survivors, ≈ −1,700 ln, which restores the <61,480 target); files within 169-181 (UNCHANGED). Budget 1500/slice, stacked-to-master.

> Rationale (cov-headroom-guard remediate-1): the coverage-guard slice traded +384 ln for +0.96pp headroom (80.53→81.49%); fase 2 restores the original ceiling.

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Final target

- GIVEN all slices merged
- WHEN metrics measured
- THEN files within 169-181, lines strictly below 61,800 until tests-slim fase 2 lands (deleting the 11 documented survivors, ≈ −1,700 ln, which restores the <61,480 target) with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion in the diff carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)
