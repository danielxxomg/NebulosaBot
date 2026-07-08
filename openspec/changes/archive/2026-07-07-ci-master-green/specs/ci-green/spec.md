# CI Green — Acceptance Criteria Specification

## Purpose

Verify that master CI passes all gates after cosmetic formatting and test-only TypeScript fixes. No production behavior changes.

## Requirements

### Requirement: Python Formatting Gate

The project MUST pass `ruff format --check .` with zero files requiring reformatting.

#### Scenario: Full project passes format check

- GIVEN the master branch with all formatting changes applied
- WHEN `ruff format --check .` is executed at the project root
- THEN the command exits with code 0
- AND zero files are reported as needing reformatting

#### Scenario: CI scoped format check passes

- GIVEN the CI workflow's scoped `ruff format --check` invocation
- WHEN the CI pipeline runs the format gate
- THEN the gate passes without failure

### Requirement: TypeScript Compilation Gate

The `dashboard/` directory MUST pass `npx tsc --noEmit` with zero errors.

#### Scenario: Ticket-actions test type error resolved

- GIVEN `dashboard/__tests__/lib/actions/ticket-actions.test.ts`
- WHEN TypeScript type-checks the file
- THEN the TS2322 error at line 254 (setupAuth param type) is resolved

#### Scenario: Middleware test import error resolved

- GIVEN `dashboard/__tests__/middleware.test.ts`
- WHEN TypeScript type-checks the file
- THEN the TS7016 error at line 2 (path-to-regexp import) is resolved

#### Scenario: Middleware test mock completeness resolved

- GIVEN `dashboard/__tests__/middleware.test.ts`
- WHEN TypeScript type-checks the file
- THEN the TS2345 errors at lines 81 and 103 (missing supabase in mock) are resolved

#### Scenario: Full dashboard type-check passes

- GIVEN all four TypeScript errors are fixed
- WHEN `npx tsc --noEmit` is executed in `dashboard/`
- THEN the command exits with code 0
- AND zero type errors are reported

### Requirement: CI Matrix Passes

CI MUST be green on all Python versions in the qa-matrix (3.11, 3.12, 3.14).

#### Scenario: All matrix versions pass

- GIVEN the change is merged to master
- WHEN the CI pipeline runs the qa-matrix
- THEN all jobs for Python 3.11, 3.12, and 3.14 pass

### Requirement: Non-Regression on Production Behavior

The change MUST NOT alter any production behavior. Formatting is cosmetic; TypeScript fixes are test-only.

#### Scenario: No production code logic changes

- GIVEN the diff between the change branch and pre-change master
- WHEN production source files (non-test, non-config) are compared
- THEN no logic changes are present — only whitespace/formatting differences

#### Scenario: Rollback is safe

- GIVEN the change is merged to master
- WHEN `git revert <merge-sha>` is executed
- THEN the revert succeeds cleanly
- AND CI returns to its prior state (red, per pre-change baseline)

### Requirement: Downstream PR Rebaseability

PRs #18, #19, and #20 SHOULD rebase onto the green master cleanly.

#### Scenario: PR #18 rebases without conflicts

- GIVEN PR #18 (`fix/runtime-bugfixes`) targets master
- WHEN the branch is rebased onto the formatted master
- THEN rebase completes without conflicts
- AND a fixup commit re-formats any PR #18 touched files if needed

#### Scenario: PRs #19 and #20 rebase without conflicts

- GIVEN PRs #19 and #20 target master
- WHEN their branches are rebased onto the formatted master
- THEN rebase completes without conflicts
