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


## S4.2B 018 Live 8-Step
- [x] 3.1 RED tests/test_s4d2b_018_live.py — DO preflight before TEXT→UUID USING, dup/UUID/orphan/depth raises, fixed-argv psql shell=False ON_ERROR_STOP
- [x] 3.2 GREEN migrations/018_ticket_integrity_fks.sql — 8-step ordered: preflight → cast USING → child indexes → parent RESTRICT → category SET NULL → note CASCADE → audit SET NULL nullable+cleanup → VALIDATE → drop idx_ticket_guild_number only, DOWN present
- [x] 3.3 GREEN scripts/apply_staging_migration.py — tracked psql allowlist 018 only, backup ticket_backup_categoryid_text_20260818, LiveGateResult LIVE_SUPABASE=1+DB_URL+used_real_db, fail-with-warning not mocked pass, fixed argv timeout shell=False
- [x] 3.4 Verify — mypy 0, ruff 0, full 2030 passed 7 skipped; focused 20 passed 1 skipped; live no-creds 1 passed 3 skipped (warning), live with DB_URL 4 passed (real DB path); branch staging-live-parity-s4d2b-018-live ≤431 insertions net, ≤800

### Evidence S4.2B
| Evidence | Result |
|---|---|
| Focused | `uv run pytest tests/test_s4d2b_018_live.py --no-cov -q` → 20 passed 1 skipped |
| Full | `uv run pytest -q --no-cov` → 2030 passed 7 skipped |
| Live no-creds | `uv run pytest -m live --run-live --no-cov -q` → 1 passed 3 skipped (fail-with-warning path) |
| Live with DB_URL | `LIVE_SUPABASE=1 DB_URL=postgresql://x/x uv run pytest -m live --run-live --no-cov -q` → 4 passed |
| Types | `uv run mypy bot tests` → 0 |
| Lint | `uv run ruff check bot tests scripts` → 0 |

### TDD Cycle S4.2B
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 3.1 Preflight+argv | tests/test_s4d2b_018_live.py FAIL (no helper module) | scripts/apply_staging_migration.py build_psql_argv + check_live_gate | ruff mypy 0, fail-with-warning gate |
| 3.3 Live gate strict | LIVE_SUPABASE without DB_URL must warn+fail | check_live_gate DB_URL/used_real_db + warning | no mocked pass — FakeSupabase never PASS |
| 3.2 Ordered 018 | 8-step order KIND already green (S3) | 018 serves helper validation, DOWN present | helper allowlist enforces tracked path |

### Rollback S4.2B
`git revert` of 018 helper + tasks/apply-progress; revokes DB_URL; if 018 already applied live: DOWN restores TEXT via backup ticket_backup_categoryid_text_20260818; `git revert` of migration commit.

## S4.3 Runbook + EXPLAIN (docs-only, ≤200)

- [x] 4.1–4.3 RED tests/test_s4d3_runbook.py 26 failed → 26 passed (credential window/revocation, EXPLAIN BUFFERS, JWT JWKS/RS256/HS256, 8-step + lock_timeout, GUILD_SCOPE_GAP_HISTORY)
- [x] 4.1 GREEN docs/runbooks/staging-live-parity.md — creds S4.2 window + revocation, backup ticket_backup_categoryid_text_20260818/DOWN/restore, tracked psql checklist, mypy0 ruff0 gates
- [x] 4.2 GREEN EXPLAIN (ANALYZE, BUFFERS) receipt for duplicate idx_ticket_guild_number only; zero pg_stat_user_indexes scans alone not drop; idx_ticket_channel retained; 12 unused noted
- [x] 4.3 GREEN JWT rotation docs — jwks_uri bounded kid 3-refresh, iss/aud/exp/role, HS256 legacy SUPABASE_JWT_SECRET allowlist, alg confusion blocked, rotation procedure
- [x] 4.4 Verify — mypy 0, ruff 0, ruff format clean, python -m py_compile bot/__main__.py ok, full 2056 passed 7 skipped (88.12%)

### Evidence S4.3

| Evidence | Result |
|---|---|
| Focused | `uv run pytest tests/test_s4d3_runbook.py --no-cov -q` → 26 passed |
| Full | `uv run pytest -q` → 2056 passed 7 skipped; `uv run pytest --no-cov -q` → 2056 passed 7 skipped |
| Types | `uv run mypy bot tests` → 0 |
| Lint | `uv run ruff check bot tests scripts` → 0 (hidden TRY400 fix applied) |
| Format | `uv run ruff format --check bot tests scripts` → 183 files formatted |
| Compile | `python -m py_compile bot/__main__.py` → ok |
| Live docs | runbook documents `LIVE_SUPABASE=1 DB_URL=… uv run pytest -m live --run-live -q` real path |

### TDD Cycle S4.3

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 4.1–4.3 Runbook | tests/test_s4d3_runbook.py 26 failed (runbook absent) | docs/runbooks/staging-live-parity.md (≈175 lines, no code/DDL) | ruff TRY400 narrow fix; mypy0; full suite 2056 passed |

### Rollback S4.3

`git revert` of docs/runbooks/staging-live-parity.md + tests/test_s4d3_runbook.py + tasks/apply-progress; no runtime/schema effect (docs-only).

## Remaining

- [x] S4.3 runbook + EXPLAIN — all S4 slices complete (S4.1 → S4.2A → S4.2B → S4.3)

### S4.3 Branch

`staging-live-parity-s4d3-runbook` from `29f946a` → `master`, ≤200 authored, docs-only, stacked-to-main final slice. PR prepared before push: `gh pr create --base master` (not pushed).
