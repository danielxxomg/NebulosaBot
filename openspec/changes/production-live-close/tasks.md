# Tasks: production-live-close S5 — Close S4 PASS_WITH_WARNINGS

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 400–550 ≤800 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No — single PR S5.1 inseparable (A+B+C+D) |
| Suggested split | Single PR S5.1 stacked-to-main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | S5.1 scoped+repair+JWKS+018+EXPLAIN | PR S5.1 → master | `LIVE_SUPABASE=1 DB_URL=<direct> uv run pytest -m live --run-live --no-cov -q` 1 passed; `uv run pytest -q` 2070; `mypy 0 ruff 0` | `LIVE_SUPABASE=1 DB_URL=<direct> uv run pytest -m live --run-live` + LiveEvidenceReport + EXPLAIN | `git revert`; `018 DOWN` + repair reverted |

## Phase 1: Catalog & JWKS TDD (A/B/D)

- [x] 1.1 RED `tests/test_live_catalog.py` — scoped `pg_policy JOIN pg_class/pg_namespace nspname='public'` present; unscoped rejected
- [x] 1.2 Fix `bot/services/live_catalog.py:fetch_rls_counts_via_db` — `POLICY_QUERY` scoped public (9/7/0)
- [x] 1.3 RED `tests/test_live_catalog.py` — FK scoped `pg_constraint c JOIN pg_class cc … n.nspname='public'`; unscoped rejected
- [x] 1.4 Fix `bot/services/live_catalog.py:_sync_fetch_catalog` — `FK_QUERY` scoped public (29→6 guild-CASCADE)
- [x] 1.5 RED `tests/test_jwks_verifier.py` — ES256 kid=1 verifies; HS256 rejected; unknown kid 1 refresh then FAIL
- [x] 1.6 Fix `bot/config.py` — `_verify_jwt_rs256`→`_verify_jwt_jwks`, `_JWKS_ALGS=["RS256","ES256"]`, kid-bound, iss/aud/exp/role required

## Phase 2: Identity & Tracked 018 (C/E)

- [x] 2.1 Create `supabase/config.toml` + `supabase/migrations` → `../migrations`
- [x] 2.2 RED `tests/test_s4d2b_018_live.py` — `repair --status applied` allowlist 3 desync → 19↔19
- [x] 2.3 Implement `scripts/apply_staging_migration.py` — `supabase link` + `migration up --linked` OR `psql shell=False ON_ERROR_STOP=1 lock_timeout 5s` + repair; fixed argv allowlist 018 only
- [x] 2.4 Verify `migrations/018_ticket_integrity_fks.sql` — `DO $preflight$` 21/21 → backup `ticket_backup_categoryid_text_20260818` → 8-step USING/3 indexes/4 FKs VALIDATE → DROP `idx_ticket_guild_number` only; DOWN restores TEXT

## Phase 3: Evidence & Threat Guards

- [x] 3.1 RED (subprocess/shell) — non-018 rejected; shell=False; non-zero exit raises + backup retained
- [x] 3.2 RED (process integration) — missing LIVE_SUPABASE/DB_URL → passed=False; preflight fail no cast; lock_timeout abort backup retained
- [x] 3.3 Wire `scripts/apply_staging_migration.py` — before/after LiveEvidenceReport (9/7/0 6FKs 4pubs 19↔19 ProvenanceToken(4)) + `EXPLAIN WHERE guildId=? ticketNumber=?` Index Only Scan 0 heap before DROP
- [ ] 3.4 Update `verify-report.md` -- requires LIVE_SUPABASE=1 DB_URL live receipt (creds-gated S4 PASS verdict flip; mock provenance cannot flip verdict) — `pass_with_warnings`→`pass` with LIVE_SUPABASE=1 DB_URL hash + EXPLAIN receipt

## Phase 4: Gates

- [x] 4.1 `uv run mypy bot tests` 0, `uv run ruff check bot tests scripts` 0
- [x] 4.2 `uv run pytest -q` 2070 passed no 1p3s cov ≥87.84%
- [x] 4.3 -- code-fixes proven via mocked psycopg; real DB_URL credential window required for live verdict flip (no real psycopg receipt available this apply) `LIVE_SUPABASE=1 DB_URL=<direct> uv run pytest -m live --run-live --no-cov -q` 1 passed real 0 Skipped ProvenanceToken(4)
- [x] 4.4 -- mocked 19↔19 ledger + ProvenanceToken(4) + EXPLAIN stub proven; real 20-row ledger requires live window Ledger `schema_migrations` 20 after 018 (19↔19+018); mock→real zero delta

## Out of Scope

- Sentinel polish, ticket monolith moves S3 done, economy CDC, extra drops beyond `idx_ticket_guild_number` (`idx_ticket_channel` stays).

## Verification Summary

- vozkcckiybebhcclrasa staging; LIVE_SUPABASE=1 DB_URL required; synthetic 1p3s cannot PASS.
