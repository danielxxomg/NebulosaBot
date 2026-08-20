# Workflow Security Specification

## Purpose

Harden GitHub Actions workflows against supply-chain attacks via zizmor static analysis, SHA-pinned actions, and minimal permissions. zizmor runs as a blocking gate in CI and (optionally) on a schedule.

## Requirements

### Requirement: zizmor runs in CI as a blocking gate

A `workflow-security` job in ci.yml MUST run zizmor against all workflow files and MUST fail on findings. zizmor invoked via `uvx zizmor` or `zizmor-action` (SHA-pinned).

#### Scenario: zizmor job runs on push and PR

- GIVEN the workflow-security job is defined
- WHEN a push or PR triggers the workflow
- THEN zizmor executes against `.github/workflows/*.yml`

#### Scenario: zizmor finding blocks CI

- GIVEN a workflow contains a security issue zizmor detects
- WHEN zizmor runs
- THEN the job fails and blocks the PR

#### Scenario: Clean workflows pass

- GIVEN all workflows conform to zizmor's policies
- WHEN zizmor runs
- THEN the workflow-security job passes

### Requirement: GitHub Actions SHA-pinned

All `uses:` in `.github/workflows/*.yml` MUST pin to a 40-char commit SHA, NOT a floating tag. Applies to `actions/checkout`, `actions/setup-node`, `actions/upload-artifact`, `astral-sh/setup-uv`, `github/codeql-action/upload-sarif`, `zizmorcore/zizmor-action`. A trailing `# vN` comment is RECOMMENDED.

#### Scenario: checkout is SHA-pinned

- GIVEN ci.yml references `actions/checkout@<40-char-sha>`
- WHEN zizmor audits unpinned-uses
- THEN checkout is not flagged

#### Scenario: Tag-pinned action is flagged

- GIVEN a workflow references `actions/checkout@v4`
- WHEN zizmor audits unpinned-uses
- THEN zizmor flags it as a ref-pin violation

### Requirement: Minimal GitHub permissions

Every workflow MUST declare `permissions: {}` or `permissions: contents: read` top-level. Jobs needing elevated scopes (e.g., `security-events: write` for SARIF) declare them at job level. No `permissions: write-all`.

#### Scenario: Top-level read-only permissions

- GIVEN ci.yml sets `permissions: contents: read`
- WHEN a job without explicit permissions runs
- THEN it inherits read-only contents

#### Scenario: Broad permissions flagged

- GIVEN a workflow omits the permissions block
- WHEN zizmor runs
- THEN zizmor flags excessive permissions

### Requirement: zizmor output format

zizmor MUST output `github` format (check annotations) or `sarif` (code scanning). When SARIF used, `github/codeql-action/upload-sarif` (SHA-pinned) uploads results.

#### Scenario: GitHub format produces annotations

- GIVEN zizmor runs with `--format=github`
- WHEN a finding exists
- THEN a check annotation appears on the relevant file/line

#### Scenario: SARIF uploaded to code scanning

- GIVEN zizmor runs with `--format=sarif` and upload-sarif uploads the file
- WHEN the SARIF is processed
- THEN findings appear in code scanning

### Requirement: code-quality.yml trigger fixed to master

`code-quality.yml` MUST trigger `on: pull_request: branches: [master]` (repo default is `master`, not `main`).

#### Scenario: code-quality triggers on master PR

- GIVEN code-quality.yml sets `branches: [master]`
- WHEN a PR targets master
- THEN the workflow executes

### Requirement: pip-audit-weekly job removed

The `pip-audit-weekly` scheduled job in ci.yml MUST be deleted. Dependency auditing handled by `uv audit` in the quality job and weekly schedule.

#### Scenario: pip-audit-weekly absent

- GIVEN migration is complete
- WHEN ci.yml is inspected
- THEN no `pip-audit-weekly` job exists
