# Delta for Pre-commit Config File

## REMOVED Requirements

### Requirement: Pre-push stage runs uv check and tach

(Reason: upstream `uv check` semantics changed — it now emits an experimental warning and runs type checking, duplicating the dedicated `ty` hook. The pre-push slot is replaced wholesale by a lockfile-freshness check under a new id; rename-not-reuse because the hook's meaning changed entirely.)

(Migration: `uv check` → `uv lock --check` under local hook id `uv-lock-check`; `tach check` / `tach check-external` are unchanged and re-land under the ADDED requirement below. No other callers exist.)

## ADDED Requirements

### Requirement: Pre-push stage runs uv lock check and tach

`prek.toml` MUST include pre-push hooks: `uv-lock-check` (local id, entry `uv lock --check`), `tach check`, and `tach check-external`, each with `stages = ["pre-push"]`. Tests MUST NOT run per-commit.

#### Scenario: Pre-push runs lock check and tach

- GIVEN pre-push hooks run `uv-lock-check`, `tach check`, `tach check-external`
- WHEN `git push` runs
- THEN lockfile freshness is verified and module boundaries are enforced

#### Scenario: Stale lock blocks push

- GIVEN `pyproject.toml` changed without regenerating `uv.lock`
- WHEN the developer pushes
- THEN `uv-lock-check` fails and the push is aborted

### Requirement: jscpd-check pre-push hook

`prek.toml` MUST include a local `jscpd-check` hook in the pre-push stage scoped to `^(bot/|tests/)` that invokes the duplication budget checker (see the duplication-budget specification). A push MUST abort on any non-zero checker exit.

#### Scenario: Push blocked above duplication ceiling

- GIVEN duplication exceeds a committed baseline ceiling
- WHEN the developer pushes
- THEN `jscpd-check` exits non-zero and the push is aborted

#### Scenario: Push proceeds within ceiling

- GIVEN duplication is within all ceilings
- WHEN the developer pushes
- THEN `jscpd-check` passes and the push proceeds

## MODIFIED Requirements

### Requirement: Hook priorities and ordering

`prek.toml` MAY define `[priorities]`. Effective order: builtin → ruff check → ruff format → ty → GGA (pre-commit); uv-lock-check → jscpd-check → tach check → tach check-external (pre-push).

(Previously: the pre-push order referenced `uv check` and had no duplication hook.)

#### Scenario: Hooks execute in priority order

- GIVEN `prek.toml` defines priorities or relies on list order
- WHEN prek runs the pre-push stage
- THEN hooks execute in the specified order (lock check, duplication, tach)
