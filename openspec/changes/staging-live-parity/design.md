# Design: staging-live-parity S4

## Technical Approach

Deliver four stacked-to-main PRs, each below 800 authored lines, behind one credential gate. The default path keeps `FakeSupabase`; acceptance requires `LIVE_SUPABASE=1`, `DB_URL`, Supabase credentials, and JWKS settings, then uses read-only `psql`/MCP SQL. Fake evidence and PostgREST `PGRST205` can never produce S4 PASS. The 24 hybrid-command decorators remain untouched; 12 guild gaps are already runtime-closed; view facades remain patch seams.

| Slice | Implementation boundary | Rollback |
|---|---|---|
| S4.1 | HS256/RS256, JWKS rotation, `GUILD_SCOPE_GAP_HISTORY`, runtime closure, bounded 73%→80% repair/panel tests. | `git revert`; code only. |
| S4.2A | Direct catalog adapter, exact 19 version/name pairs; optional restricted RPC, never PostgREST catalogs. | `git revert`; evidence-only; revoke credentials. |
| S4.2B | Credential-gated tracked 018 execution and catalog evidence; no DDL outside 018. | Abort before cast; DOWN/backup restore; re-verify. |
| S4.3 | Runbook, EXPLAIN receipt, acceptance/rollback checklist. | `git revert`; no runtime/schema effect. |

## Architecture Decisions

| Decision | Choice and rationale |
|---|---|
| Real credentials | S3 mocks prove binder shape only; acceptance therefore requires real `DB_URL` and Supabase/JWKS credentials, while default tests remain mocked. |
| Catalog source | Read `pg_constraint`, policies, publications, indexes, types, and `supabase_migrations.schema_migrations` through direct SQL. This bypasses `PGRST205` and proves identity, not count. |
| JWT verification | Discover `jwks_uri`; use `PyJWKClient`, `algorithms=["RS256"]`, required `role/iss/aud/exp`, and one bounded unknown-`kid` refresh. Keep HS256 separately allowlisted. |
| Index evidence | Require representative `EXPLAIN (ANALYZE, BUFFERS)`; cumulative zero scans do not prove non-use. Drop only redundant `idx_ticket_guild_number`. |
| Four PRs | Separate security, catalog, destructive DDL, and operations for reviewable rollback boundaries under 800 lines. |
| Historical rename | Rename to `GUILD_SCOPE_GAP_HISTORY`, retain all 12 entries for inventory tests, and add truthful `guild_scope_runtime_closed == 12`. |

## Data Flow

```text
S4.1 guardrails → S4.2A real catalog gate → S4.2B 018 window → S4.3 receipt
       └─ missing marker/creds: FAIL (not fake PASS) ─┘
```

```text
key ──sb_secret_──→ guild+ticket read-only probes ──→ accept/reject
  └─JWT──alg=HS256→ secret + HS256 claims ──────────→ accept/reject
       └─alg=RS256→ jwks_uri → PyJWKClient(kid) → one refresh → iss/aud/exp/role
```

```text
DB_URL + LIVE_SUPABASE=1 → backup/timeouts → (1) preflight
   ├─fail → abort before (2) TEXT→UUID cast
   └─pass → (2) cast → (3) child indexes → (4) parent RESTRICT
            → (5) category SET NULL → (6) note CASCADE
            → (7) audit SET NULL → (8) validate/checks
            → EXPLAIN receipt → drop duplicate only
            └─failure/lock timeout → DOWN or backup restore → re-verify
```

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/config.py`, `pyproject.toml`, `requirements.txt`, `uv.lock` | Modify | JWKS/issuer/audience configuration and direct PyJWT crypto dependency. |
| `bot/services/schema_inventory.py` | Modify | Typed catalog evidence, exact migration reconciliation, historical rename, runtime closure. |
| `bot/services/live_catalog.py` | Create | Read-only `DB_URL`/RPC adapter; no mutation or PostgREST catalog fallback. |
| `migrations/018_ticket_integrity_fks.sql` | Modify | Preserve/enforce the existing eight-step order, preflight abort, lock guards, and DOWN; add no new migration. |
| `scripts/apply_staging_migration.py`, `docs/runbooks/staging-live-parity.md` | Create | Fixed tracked-file execution (`psql`, no shell composition), EXPLAIN, evidence, and rollback procedure. |
| `tests/test_config.py`, `tests/test_schema_inventory_verifier.py`, live/JWKS/repair/panel tests | Modify/Create | RED tests for both credential paths, rotation, drift, gates, and bounded error coverage. |

## Interfaces / Contracts

`CatalogEvidence` is a frozen dataclass containing `rls(9,7,0)`, six guild CASCADE FKs, four CDC tables, typed `categoryId`, index plans, and exact `(version,name)` pairs. `LiveAcceptanceGate` returns `passed` plus missing-credential/drift reasons; `FakeSupabase` is unit-test-only.

## Testing Strategy

Unit tests cover HS256, RS256 claims/confusion/unknown-`kid` refresh, rename preservation, and normalization. Integration tests cover real catalog and 018 preflight/rollback. Default live SKIPs remain allowed; acceptance must show real `1 passed 1 passed`, not fake `1 passed 1 skipped`.

## Threat Matrix

| Boundary | Status | Response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — fixed SQL path; no executable-doc classification. | None. |
| Git repository selection | N/A — no selector. | None. |
| Commit state | N/A — no commit automation. | None. |
| Push state | N/A — no push automation; orchestrator-owned. | None. |
| PR commands | N/A — no command construction. | None. |

The process boundary is fixed-argv `psql`/MCP, `shell=False`, `ON_ERROR_STOP`, timeout, and non-zero exit abort; RED tests assert no arbitrary file or shell fallback.

## Migration / Rollout

Approved staging window only: backup and catalog baseline, EXPLAIN, credential/preflight gate, tracked 018, post-catalog evidence, application checks, credential revocation. No extra DDL or SQL-editor `execute_sql`.

## Open Questions

None blocking; deployment must supply the approved issuer, audience, JWKS URI, and credential window.
