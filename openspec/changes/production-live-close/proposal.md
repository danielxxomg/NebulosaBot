# Proposal: production-live-close S5 — Close S4 PASS_WITH_WARNINGS

## Intent

Close S4 synthetic `1p3s` (mocked `ProvenanceToken(4)`) with real staging vs `vozkcckiybebhcclrasa` (`ACTIVE_HEALTHY` PG 17.6.1.155). Fix 4 gate bugs (A-E) visible only via `psycopg`: `pg_policy` unscoped (cron 2→0), `pg_constraint` unscoped (29→6), 3-name migration desync, JWKS `RS256`-only vs live `ES256`. Deliver `9/7/0` 6 FKs 4 pubs `19↔19`, JWKS dual `ES256+RS256`, `018` applied with `LiveEvidenceReport` + `EXPLAIN` receipt. Mitigation: backup + `VALIDATE` + `DOWN` rollback.

## Scope

### In Scope
- `live_catalog.py` scoped `public` (A/B); `repair --status applied` allowlist 3 desync (C); JWKS dual `ES256+RS256` `kid=1` EC allowlist + `RS256` proof (D)
- `018_ticket_integrity_fks` live: `DO $preflight$ 21/21` → backup `ticket_backup_categoryid_text_20260818` → 8-step DDL (USING cast, indexes, FKs RESTRICT/SET NULL/CASCADE/SET NULL, VALIDATE) → `DROP idx_ticket_guild_number` only
- Evidence: before/after `LiveEvidenceReport` + `EXPLAIN (ANALYZE, BUFFERS)` receipt + `DOWN`
- Real gate `LIVE_SUPABASE=1 DB_URL=<direct>` → `1 passed` real `psycopg` (no `SkipProposedMigration`), `2070→2070+`

### Out of Scope
- Extra index drops (`idx_ticket_channel` stays); sentinel polish; ticket monolith moves — facaded S3

## Capabilities

### New Capabilities
- None — closes existing gate

### Modified Capabilities
- `live-schema-verifier`: scoped `public` catalog, dual JWKS, `19↔19` repair, `psycopg` receipts
- `database-layer`: `018` tracked 8-step, `EXPLAIN` gate, backup/`DOWN`

## Approach

Single PR `S5.1` ≤800 `stacked-to-main`, `approve_window`:

- **Catalog** `psycopg` scoped `public`: `pg_policy JOIN pg_class/pg_namespace WHERE nspname='public'` fixes `9,7,2→9,7,0`; FK same `29→6`
- **Identity** `supabase migration repair --status applied` for 3 desync (`016`/`017`, 2 realtime pubs) → `19↔19` tracked, no `psql` bypass
- **JWKS** dual `HMAC+EC`: keep `RS256` `PyJWKClient` `kid=1`, add `ES256` EC P-256 allowlist; `RS256` proof, `ES256` inert
- **018** `supabase link` + tracked `psql shell=False ON_ERROR_STOP lock_timeout 5s`; `DO $preflight$ 21/21`; `EXPLAIN` proves `Index Only Scan` via `idx_ticket_guild_ticket_number` before drop; `DOWN` restores `TEXT`

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/live_catalog.py` | Modified | Scope `pg_policy`/`pg_constraint` to `public`; dual JWKS |
| `bot/config.py` | Modified | `ES256` allowlist + `RS256` `kid`-bound |
| `migrations/018_ticket_integrity_fks.sql` | Modified | `DO $preflight$` + `DOWN` + `lock_timeout` tracked |
| `scripts/apply_staging_migration.py` | Modified | Tracked `psql shell=False` + report |
| `tests/test_live_catalog.py` | Modified | Real `LIVE_SUPABASE=1` + scoped guards |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DDL needs `approve_window`, lock contention | Med | `lock_timeout 5s`, low-traffic, `ON_ERROR_STOP` pre-cast abort |
| Ledger untracked if `psql` bypass | Med | `repair --status applied`; `19↔19` fail-closed |
| `PGRST205` REST catalog gap | Low | Bypass REST; direct `psycopg` `DB_URL` |
| Backup 7d retention | Low | `ticket_backup_categoryid_text_20260818` + `VALIDATE` + `DOWN` |

## Rollback Plan

1. `018 DOWN`: restore `categoryId TEXT`, drop 4 FKs, recreate `idx_ticket_guild_number`, drop backup after 7d
2. Catalog/JWKS: revert to unscoped + `RS256`-only
3. Ledger: `repair --status reverted` `018`; verify `19↔19`
4. No synthetic fallback — real failure stays `FAIL`

## Dependencies

- Staging `LIVE_SUPABASE=1` + `DB_URL` direct `vozkcckiybebhcclrasa`, `SUPABASE_URL`/`sb_secret_*`, `supabase` 2.114.0, `psycopg[binary]`; baseline `895bb8f` (2070 87.84% mypy0 ruff0)

## Success Criteria

- [ ] `LIVE_SUPABASE=1 DB_URL=... --run-live` → `1 passed` real `psycopg` (0 Skipped), `2070+` green
- [ ] `9/7/0` `6FKs` `4pubs` `19↔19` pass scoped `public` via `psycopg`
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` receipt covers `idx_ticket_guild_number` drop
- [ ] `018` 8-step live + before/after report + `DOWN` proof; backup exists
- [ ] JWKS dual `RS256` proof + `ES256` inert; no synthetic `1p3s`
