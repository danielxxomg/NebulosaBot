# Delta for CI Workflow File

## ADDED Requirements

### Requirement: Duplication gate enforced in CI

The code-quality workflow MUST run the duplication budget checker (`scripts/jscpd_check.py`, pinned `jscpd@4.0.1`) with `continue-on-error` REMOVED, enforcing the committed `reports/jscpd-baseline.json` ceilings. The job MUST fail when any scope exceeds its ceiling, identical to the pre-push gate. Human-readable duplication report output remains advisory and non-gating.

(Previously: jscpd ran in CI as report-only under `continue-on-error: true`, so duplication regressions never blocked anything.)

#### Scenario: CI red above baseline

- GIVEN a change raises duplication above a committed ceiling
- WHEN the code-quality workflow runs
- THEN the duplication step exits 2 and the job fails

#### Scenario: Green below baseline keeps advisory report

- GIVEN duplication is at or below all ceilings
- WHEN the code-quality workflow runs
- THEN the job passes and the advisory duplication report is still produced
