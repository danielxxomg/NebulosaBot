# Delta for test-suite-governance

## MODIFIED Requirements

### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 175/62,384/3063/81.99% @9871add (re-verified fresh) → lines strictly below 61,480 with final aim ≤61,300; files within 169-181. Budget 1500/slice, stacked-to-master. Restoration is parametrization-first: zero D3 deletions by default; any deletion still requires D3 proof per the FAIL-regardless-of-metrics gate below. Coverage scope: `bot/views/setup_modules/welcome.py` (54%), `bot/views/setup_panel.py` (62%), `bot/views/setup_modules/goodbye.py` (69%), `bot/services/live_catalog.py` (72%) each to ~80%, plus hardening of `tests/test_setup_panel_pickers.py:192-197`. The dashboard pagination unit (`dashboard/__tests__/app/audit-panel.test.tsx:122-169`) is excluded from the Python ledger.

> Rationale (tests-slim-fase-3): parametrization-first restoration after greeting-templates additions pushed the suite to 62,384.

(Previously: interim <61,480 pending tests-slim fase 3 parametrization)

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Final target

- GIVEN all slices merged
- WHEN metrics measured
- THEN files within 169-181, lines strictly below 61,480 (aim ≤61,300) with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion in the diff carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)
