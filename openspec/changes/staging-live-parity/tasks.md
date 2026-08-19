# Tasks: staging-live-parity S4

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total | ~1400 split 400/350/400/200 each ≤800 |
| Chained | Yes — 4 stacked-to-main, work-unit commits |
| Delivery | auto-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Work Units

| Unit | Goal | PR | Rollback |
|------|------|----|----------|
| 1 | JWKS RS256 + HISTORICAL + polish | S4.1 | `bot/config.py` revert |
| 2 | Catalog 19 ids 9/7/0 6FKs 4pubs | S4.2A | `live_catalog.py` revert |
| 3 | 018 8-step live | S4.2B | `018*.sql` DOWN |
| 4 | Runbook + EXPLAIN | S4.3 | `docs/runbooks/*` revert |

## S4.1 Guardrails (~400 ≤800)

- [x] 1.1 RED `tests/test_jwks_verifier.py`: RS256 ok/fail, kid→1 refresh else fail, missing iss/aud/exp/role, HS256 confusion fail
- [x] 1.2 GREEN add `PyJWT[crypto]` direct (note: 2.13.0 now transitive via `uv.lock` only) + `PyJWKClient(jwks_uri)` `["RS256"]` required claims bounded refresh, HS256 allowlist retained
- [x] 1.3 RED+GREEN `schema_inventory.py`: `GUILD_SCOPE_GAPS`→`GUILD_SCOPE_GAP_HISTORY` 12, `guild_scope_runtime_closed==12`
- [x] 1.4 RED→GREEN polish 73→80% `ticket_repair_service.py`+`ticket_panel.py` (98-99/229-243/280-335, 95-115/163-186)
- [x] 1.5 Verify & PR: `uv run mypy bot tests` 0 `uv run ruff check` 0 `--cov=bot` ≥80%; `s4.1-guardrails` from `a80f129`→`main`; harness `LIVE_SUPABASE=1 DB_URL=... uv run pytest -m live --run-live -q`

## S4.2A Catalog DB/RPC (~350 ≤800)

- [x] 2.1 RED `tests/test_live_catalog.py`: 9/7/0 6 CASCADE 4 pubs 19 exact version/name; count-only fails PGRST205 unresolved FakeSupabase never PASS
- [x] 2.2 GREEN `live_catalog.py` RO `DB_URL` adapter `pg_constraint/pg_policy/pg_publication_tables/pg_stat_user_indexes/schema_migrations`; no PostgREST fallback
- [x] 2.3 GREEN `schema_inventory.py` exact 19 reconcil. + `LiveAcceptanceGate` needs `LIVE_SUPABASE=1`+`DB_URL`+Supabase/JWKS
- [x] 2.4 Verify & PR: `LIVE_SUPABASE=1 DB_URL=... uv run pytest -m live --run-live --no-cov -q` 1 passed 1 passed real; `s4.2a-catalog` from S4.1→`main`

## S4.2B 018 Live 8-Step (~400 ≤800)

- [ ] 3.1 RED preflight: DO raises before `TEXT→UUID USING` on dup/invalid UUID/orphan/depth; `apply_staging_migration.py` fixed-argv `psql` `shell=False` `ON_ERROR_STOP`
- [ ] 3.2 GREEN `018_ticket_integrity_fks.sql` order (1) preflight (2) TEXT→UUID USING (3) indexes (4) parent RESTRICT (5) category SET NULL (6) note CASCADE (7) audit SET NULL (8) VALIDATE→drop `idx_ticket_guild_number` only
- [ ] 3.3 GREEN `apply_staging_migration.py` tracked exec before/after capture backup/timeouts
- [ ] 3.4 Verify & PR: `LIVE_SUPABASE=1 DB_URL=... uv run pytest -m live --run-live -q` proves uuid 6+4 FKs only dupe dropped; `s4.2b-018-live` from S4.2A→`main`

## S4.3 Runbook + EXPLAIN (~200 ≤800)

- [ ] 4.1 `docs/runbooks/staging-live-parity.md`: credential window/revocation backup/DOWN/restore tracked `psql` checklist (mypy0 ruff0 1968+ live 1 passed 1 passed real)
- [ ] 4.2 `EXPLAIN (ANALYZE, BUFFERS)` receipt for dupe; zero `pg_stat_user_indexes` scans alone not drop `idx_ticket_channel` retained
- [ ] 4.3 JWT rotation docs: `jwks_uri` bounded kid refresh iss/aud HS256 retained
- [ ] 4.4 Verify & PR: `uv run pytest -q` + `python -m py_compile bot/__main__.py`; `s4.3-runbook` from S4.2B→`main`

## Gates

`mypy` 0 · `ruff check` 0 · `ruff format --check` clean · `uv run pytest -q` 1968+ · `uv run pytest -m live --run-live --no-cov -q` 1 passed 1 passed real (mocked PASS_WITH_WARNINGS rejected).

## Out of Scope

New business, economy CDC, dashboard RLS policies, migrations beyond 018, drops beyond EXPLAIN dupe, sentinel debt, untracked `execute_sql`.
