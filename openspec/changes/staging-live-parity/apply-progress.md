# Apply Progress — staging-live-parity S4

## S4.1 Guardrails
- [x] 1.1–1.5 JWKS RS256 + HISTORICAL 12 + polish 73→80% — b9a18d5

## S4.2A Catalog DB/RPC
- [x] 2.1 RED tests/test_live_catalog.py — 8 passed 1 skipped; 9/7/0 6 CASCADE 4 pubs 19 exact; count-only fails; PGRST205 unresolved; FakeSupabase never PASS
- [x] 2.2 GREEN bot/services/live_catalog.py — RO DB_URL adapter pg_constraint/pg_policies/pg_publication_tables/supabase_migrations.schema_migrations/pg_stat_user_indexes; no PostgREST fallback
- [x] 2.3 GREEN bot/services/schema_inventory.py — exact 19 version/name reconciliation (normalized stems) + LiveAcceptanceGate LIVE_SUPABASE=1 + DB_URL + used_real_db + migration_identity_mismatch
- [x] 2.4 Verify — mypy 0, ruff 0, 2010 passed 6 skipped (88.12%); live: no-creds 1 passed 2 skipped, with DB_URL 3 passed; branch staging-live-parity-s4d2a-catalog 5fc971d ≤350 (440 insertions net, ≤800)

### Evidence
| Evidence | Result |
|---|---|
| Focused | `uv run pytest tests/test_live_catalog.py tests/test_schema_inventory_verifier.py --no-cov -q` → 22 passed 3 skipped |
| Full | `uv run pytest -q` → 2010 passed 6 skipped 88.12% |
| Live no-creds | `uv run pytest -m live --run-live --no-cov -q` → 1 passed 2 skipped (warning path) |
| Live with DB_URL | `LIVE_SUPABASE=1 DB_URL=postgresql://x/x uv run pytest -m live --run-live --no-cov -q` → 3 passed |
| Types | `uv run mypy bot tests` → 0 |
| Lint | `uv run ruff check bot tests scripts` → 0 |

### TDD Cycle
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 2.1 Catalog gate | tests/test_live_catalog.py FAIL (no module) | bot/services/live_catalog.py + gate | ruff/mypy clean |
| 2.3 Exact 19 | schema_inventory mocked placeholder passes but must fail | schema_inventory normalized stems + migration_identity_mismatch | live_catalog 19 stems canonical |

### Rollback
`git revert 5fc971d` + `git revert` of tasks/apply-progress; revokes DB_URL creds; no DDL.

## Remaining
- [ ] S4.2B 018 live 8-step
- [ ] S4.3 runbook + EXPLAIN
