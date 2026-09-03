# Delta for test-suite-governance

## MODIFIED Requirements

### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 184/61,622/3005/80.50% @2bb4e89 → lines strictly below 61,480; files within 169-181. Budget 1500/slice, stacked-to-master.

> Rationale (tests-slim-fase-2): restores original <61,480 ceiling after twin proof + deletion of 11 survivors (≈ −1,700 ln), reversing cov-headroom-guard interim uplift to <61,800.

(Previously: interim <61,800 ceiling pending tests-slim fase 2 deletion of 11 survivors)

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Final target

- GIVEN all slices merged
- WHEN metrics measured
- THEN files within 169-181, lines strictly below 61,480 with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion in the diff carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)