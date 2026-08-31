# Delta for qa-ci-pipeline

## ADDED Requirements

### Requirement: Daily Supabase dump cron via pooler

CI MUST add `.github/workflows/backup.yml` running daily via cron (`0 2 * * *` UTC) that dumps the Supabase DB through the session pooler (port 5432, `SUPABASE_DB_URL` pooler form), uploads artifact with 7-day retention (`retention-days: 7`), and fails visibly on dump error. Workflow MUST use SHA-pinned actions, `uv`/`pg_dump` available on runner, and MUST NOT log `SUPABASE_DB_URL`/`SENTRY_DSN` secrets. Coverage gate remains `--cov-fail-under=80` (2973 tests, 80.23% actual; headroom 0.23pp — slices MUST keep cov ≥80.23%).

#### Scenario: Cron file exists and triggers daily

- GIVEN `.github/workflows/backup.yml` with `on.schedule.cron` and `on.workflow_dispatch`
- WHEN workflow is parsed
- THEN cron is `0 2 * * *` and manual dispatch is allowed

#### Scenario: Artifact retention 7 days

- GIVEN backup job uploads via `actions/upload-artifact`
- WHEN inspected
- THEN `retention-days` is 7

#### Scenario: Failure surfaces not silent

- GIVEN `pg_dump` exits non-zero
- WHEN job runs
- THEN step fails (no `continue-on-error: true`) and run is marked failed

#### Scenario: Coverage headroom preserved

- GIVEN S0+S1 slices are applied sequentially
- WHEN `uv run pytest --cov-fail-under=80` runs (≥2973 passed)
- THEN cov stays ≥80.23% (0.23pp headroom not regressed)
