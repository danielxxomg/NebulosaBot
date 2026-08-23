# Duplication Budget Specification

## Purpose

Cap code duplication (jscpd) in `bot/` and `tests/` with a committed baseline ceiling enforced locally (pre-push) and in CI, ratcheting downward over time.

## Requirements

### Requirement: Committed baseline ceiling file

A committed `reports/jscpd-baseline.json` MUST declare per-scope duplication ceilings as JSON percentages: `{"bot": <float>, "tests": <float>}`. It MUST be the single ceiling source consumed by both the pre-push hook and CI; no other threshold value MAY gate duplication.

#### Scenario: Baseline parsed

- GIVEN a valid baseline file is committed
- WHEN the checker loads it
- THEN it obtains numeric ceilings for the `bot` and `tests` scopes

#### Scenario: Missing or malformed baseline

- GIVEN the baseline file is absent or unparsable
- WHEN the checker runs
- THEN it exits 1 (infrastructure failure) without comparing any scope

### Requirement: Checker exit-code contract

`scripts/jscpd_check.py` MUST run the pinned `jscpd@4.0.1` over `bot/` and `tests/` (JSON reporter, temporary output directory, no shell interpolation), read each scope's `statistics.clone.percentage`, and compare it against its ceiling. Exit codes MUST be: 0 when every scope is at or below its ceiling; 2 when any scope strictly exceeds its ceiling; 1 for infrastructure failures (missing tool output, unparsable report, bad baseline).

#### Scenario: Within ceiling passes

- GIVEN measured duplication is at or below ceiling in both scopes
- WHEN the checker completes
- THEN it prints the measured per-scope values and exits 0

#### Scenario: Above ceiling fails

- GIVEN any scope measures strictly above its ceiling
- WHEN the checker completes
- THEN it reports the offending scope(s) with measured vs ceiling values and exits 2

#### Scenario: Infrastructure failure distinguished from violation

- GIVEN jscpd crashes or emits unparsable output
- WHEN the checker handles the failure
- THEN it exits 1, distinct from a budget violation (2)

### Requirement: Pre-push hook enforcement

`prek.toml` MUST define a local `jscpd-check` hook in the pre-push stage scoped to `^(bot/|tests/)` that invokes the checker. A push MUST be aborted whenever the checker exits non-zero.

#### Scenario: Push blocked above ceiling

- GIVEN current duplication exceeds a ceiling
- WHEN the developer pushes
- THEN the hook fails (exit 2 surfaced) and the push is aborted

#### Scenario: Push allowed within ceiling

- GIVEN duplication is within all ceilings
- WHEN the developer pushes
- THEN the hook passes and the push proceeds

### Requirement: CI fails above baseline

The code-quality workflow MUST drop `continue-on-error` from its duplication step and MUST enforce the same committed baseline by running the same checker with the same `jscpd@4.0.1` pin. The job MUST fail when any scope exceeds its ceiling. Human-readable duplication reports remain advisory output.

#### Scenario: CI red above baseline

- GIVEN a change raises duplication above a ceiling
- WHEN the workflow runs
- THEN the job fails and blocks merge

#### Scenario: Advisory report retained on green

- GIVEN the job runs at or below ceilings
- WHEN it completes
- THEN it passes while still producing the advisory duplication report

### Requirement: Calibration procedure

Ceilings MUST be calibrated empirically before gates activate: measure current per-scope duplication, then set each ceiling to measured + 0.5 percentage points. The calibration commit MUST contain only the baseline file (plus wiring if not yet present).

#### Scenario: Calibrated ceiling formula

- GIVEN `bot` measures 4.20% at calibration time
- WHEN the baseline is written
- THEN the bot ceiling equals 4.70 (measured + 0.5pp)

### Requirement: Lowering protocol

Lowering a ceiling MUST be a baseline-JSON-only commit, made only after a measurement shows the new lower value holds. Ceiling values MUST NOT increase except through a recalibration commit whose message records the justification.

#### Scenario: Ratchet-down commit

- GIVEN refactors reduced `bot` duplication to a lower stable value
- WHEN a lowering commit lands
- THEN it touches only the baseline JSON and sets the ceiling below its previous value

#### Scenario: Raise requires documented recalibration

- GIVEN a structural change legitimately requires headroom
- WHEN a ceiling is raised
- THEN the commit message documents the recalibration reason
