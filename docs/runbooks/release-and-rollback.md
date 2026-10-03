# Runbook: Release and Rollback Procedure

> **OPERATIONAL SPECIFICATION & RECOVERY LIMITATIONS**
> This runbook defines the controlled release cutting sequence, multi-surface version synchronization, local Git rollback steps, and disaster recovery boundaries for NebulosaBot.
>
> **CRITICAL LIMITATIONS**:
> - `BACKUP_ENCRYPTION_KEY` is **NOT provisioned** in the operational environment.
> - **No successful backup run has ever been observed** or validated.
> - **Isolated restore acceptance has never been executed**.
> - This repository and procedure **do NOT claim production readiness**.

---

## 1. Context and Scope

NebulosaBot operates as a Discord bot service with an embedded Next.js dashboard client (`dashboard/`).
No artifacts are published to external public registries (no PyPI package publishing, no Docker Hub images, and `dashboard/package.json` is marked `"private": true` with no npm publishing).

Consequently:
- **Release** refers to synchronized code cutting, version bump across repository surfaces, changelog reconciliation, and tag creation on Git branches.
- **Rollback** refers to Git-level branch reversion and local deployment checkout restoration. No external registry package revocation or registry rollback is possible or applicable.

### Related Runbooks
- Application data cleanup and reset gates: [`docs/runbooks/reset-procedure.md`](reset-procedure.md)
- Staging parity, DDL execution, and irreversible migration notes: [`docs/runbooks/staging-live-parity.md`](staging-live-parity.md)

---

## 2. Preconditions

Before cutting any release candidate or tagging a release, all of the following verification gates must be verified and passing:

| Gate | Requirement | Verification Command |
|------|-------------|----------------------|
| **Python Test Suite** | Full test suite green (0 failures) | `uv run pytest -q` |
| **Dashboard Tests** | Embedded Next.js client suite green | `(cd dashboard && npm test --silent)` |
| **Type Checking** | Zero `ty` diagnostic errors | `uv run ty check bot/ tests/` |
| **Linter & Style** | Ruff lint and format check clean | `uv run ruff check bot/ tests/ scripts/ && uv run ruff format --check bot/ tests/` |
| **Lockfile Sync** | `uv.lock` perfectly aligned with `pyproject.toml` | `uv lock --check` |
| **Release Candidate Guard** | Dedicated release candidate test passes | `uv run pytest tests/test_release_candidate.py -q --no-cov` |
| **Hygiene Tests** | Base hygiene assertions pass | `uv run pytest tests/test_welcome_foundation_pr1_hygiene.py -q --no-cov` |
| **Review & Risk** | GGA code review passes with native risks assessed | Verify review log against active `AGENTS.md` rules |

> **Exit status matters.** Every command in this runbook MUST be run so its process exit
> status is preserved. Do **not** pipe a verification command into `tail`, `head`, `grep`
> or similar: with default shell semantics the pipeline's status is that of the LAST
> command, so a failing test piped into `tail` exits `0` and reports false success. Use
> the unpiped form, or `set -o pipefail` when output must be trimmed.

---

## 3. Cut Procedure

When all preconditions are satisfied, execute the version bump in exact sequential order:

### 3.1 Step 1: Bump Python Package Surfaces
1. Update `pyproject.toml`:
   ```toml
   [project]
   version = "X.Y.Z"
   ```
2. Mirror in `bot/__init__.py`:
   ```python
   __version__ = "X.Y.Z"
   ```

### 3.2 Step 2: Regenerate Python Lockfile
Do NOT edit `uv.lock` by hand. Regenerate deterministically:
```bash
uv lock
uv lock --check
```

### 3.3 Step 3: Align Embedded Dashboard Client
The embedded dashboard ships on the bot's release line, so its version tracks the project
version. Update `dashboard/package.json`:
```json
{
  "name": "nebulosabot-dashboard",
  "version": "X.Y.Z"
}
```
The root package version in `dashboard/package-lock.json` must match. The lock declares the
root version in **two** places — the top-level `"version"` and `packages[""].version` —
and BOTH must be updated, or the release candidate guard fails:
```bash
(cd dashboard && npm test --silent)
```
`tests/test_release_candidate.py::TestDashboardVersionDivergence` fails if either dashboard
surface, or either lock field, is left behind during a bump.

### 3.4 Step 4: Reconcile CHANGELOG.md
1. Ensure the newest bracketed release section matches the release target:
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD
   ```
2. Organize entries under standard Keep-a-Changelog headings (`### Added`, `### Changed`, `### Fixed`, `### Removed`).
3. If an earlier unbracketed section was shipped inside an existing tag, you may retitle it
   with that tag's date (e.g. `## [1.0.0] - 2026-08-26`) to stop claiming shipped work is
   unreleased. When you do this:
   - Record the retitle under `### Notes`, NOT under `### Fixed` — it is a historical
     reconciliation, not work delivered in the new release.
   - State the **provenance** of the date and content (which tag, verified against which tree).
     Never imply a pre-existing changelog entry existed when it did not.
   - Do not invent a `[X.Y.Z]` entry for a version whose metadata was wrong; a real gap in the
     release history stays documented as a gap rather than reconstructed.

### 3.5 Step 5: Verification Suite
Run the full verification battery. Run these unpiped (or under `set -o pipefail`) so a
failure cannot be masked by the trimming command:
```bash
uv run pytest tests/test_release_candidate.py tests/test_welcome_foundation_pr1_hygiene.py -q --no-cov
uv run pytest -q
uv run ruff check bot/ tests/ scripts/
uv run ruff format --check bot/ tests/
uv run ty check bot/ tests/
uv lock --check
(cd dashboard && npm test --silent)
```

---

## 4. Rollback Procedure

Because NebulosaBot is not published to third-party package managers or registries, rollback is entirely a local Git and deployment process.

### 4.1 Git Revert Workflow
If a release commit or merge must be unwound:

1. **Identify the Target Commit / Previous Tag**:
   ```bash
   git describe --tags --abbrev=0
   git log --oneline -5
   ```
2. **Execute Clean Git Revert**:
   - For an unpushed local commit:
     ```bash
     # Revert or modify prior to merge (do NOT use destructive commands on shared branches)
     git revert <commit-sha>
     ```
   - For a merged pull request / merge commit:
     ```bash
     git revert -m 1 <merge-commit-sha>
     ```
3. **Verify Reverted State**:
   ```bash
   uv lock --check
   uv run pytest -q
   ```

### 4.2 Git vs. Published State Boundaries
- **No Registry Rollback**: There is no PyPI unpublish, npm unpublish, or Docker tag pull-back.
- **Runtime Deploy Rollback**: The deployment host must check out the target Git commit or previous release tag and restart the bot process.

---

## 5. Recovery and Limitations

Disaster recovery and rollback have strict operational limits that must not be obscured:

1. **Missing Backup Encryption Key**:
   The `BACKUP_ENCRYPTION_KEY` environment variable is **not provisioned**. Automated encrypted database backups (`supabase-dump-encrypted`) cannot complete or decrypt without this secret.
2. **Unobserved Backup Execution**:
   **No successful backup run has ever been observed** or recorded in production. Backup reliability is unverified.
3. **Unexecuted Isolated Restore Acceptance**:
   **Isolated restore acceptance has never been executed**. There is no proven automated restore drill.
4. **DDL Rollback Irreversibility**:
   As documented in [`docs/runbooks/staging-live-parity.md`](staging-live-parity.md), migration 025 permanently dropped `ticket_backup_categoryid_text_20260818`. Consequently, migration 018's `DOWN` restore script is **IRREVERSIBLE** and cannot run. Database rollback requires restoring from an external snapshot, which is currently unproven.
5. **Data Reset Caution**:
   Any database cleanup or application data purge must adhere strictly to the read-only inventory and human sign-off gates specified in [`docs/runbooks/reset-procedure.md`](reset-procedure.md). Direct execution without human authorization is prohibited.
6. **No Production Readiness Claim**:
   Given the un-provisioned backup key and lack of proven restore drills, this system does not claim production readiness.
