# Design: production-live-close S5

Run the real staging gate against `vozkcckiybebhcclrasa` and fix four latent bugs (A–E) visible only under real `psycopg`. Single PR S5.1, stacked-to-main, ≤800 lines. Closes S4 `PASS_WITH_WARNINGS`.

**Blast radius**: 9/7/0 RLS, 6 guild-CASCADE FKs, 4 CDC pubs, 19↔19 migrations — all proven mocked in S4, now re-proven against real staging (expected zero diff). JWKS live ES256 probe. DDL lock/rollback via 018 DOWN. Views/facades unchanged.

## Architecture Decisions

| # | Decision | Choice | Rejected | Rationale |
|---|----------|--------|----------|-----------|
| 1 | DB access | `psycopg`/`DB_URL` direct | PostgREST `pg_constraint` | `PGRST205` — system catalogs not in schema cache (confirmed live). Only `psycopg` returns truthful FK/policy counts. |
| 2 | Catalog scope | `JOIN pg_class/pg_namespace WHERE n.nspname='public'` for `pg_policy`+`pg_constraint` | unscoped global | Unscoped `pg_policy`=2 (`pg_cron`)→false `9,7,2`; `pg_constraint`=29 (auth/storage)→accidental pass via downstream `parent=='guild'` filter masks drift. Scoped=truthful 6 guild-CASCADE. |
| 3 | Migration identity | `supabase migration repair --status applied` for 3 desync | allowlist | Repair keeps ledger tracked (19↔19) + strict set-equality gate intact. Allowlist accepts drift — violates "tracked migrations only". |
| 4 | JWKS algorithm | dual `["RS256","ES256"]` via `PyJWKClient`, `kid`-bound, 1 bounded refresh | RS256-only | Live JWKS returns ES256 EC P-256; RS256-only NEVER verifies live JWTs. `PyJWKClient` is key-type-agnostic (selects by `kid`). Keep `iss`/`aud`/`exp`/`role`; block alg-confusion (no HS256 fallback). |
| 5 | Index drop | `EXPLAIN (ANALYZE, BUFFERS)` proving `idx_ticket_guild_ticket_number` Index Only Scan + 0 heap fetches BEFORE `DROP idx_ticket_guild_number` | conditional DROP on `idx_scan=0` | Zero scans is cumulative + insufficient (spec). EXPLAIN receipt is authoritative; conditional DROP without receipt violates "evidence-based retention". |
| 6 | 018 concurrency | `SET lock_timeout='5s'` + `ON_ERROR_STOP=1` | `pg_advisory_lock` | Advisory lock serializes operators but NOT long user txns holding `SHARE UPDATE EXCLUSIVE`-conflicting locks during `VALIDATE`. `lock_timeout` aborts cleanly in-window; advisory is orthogonal for single-operator apply. |
| 7 | Provenance | 4 `psycopg` SELECTs in `_sync_fetch_catalog` mints `ProvenanceToken(query_count=4)` | caller bool | Caller bool = synthetic `FakeSupabase`. Token unforgable: `_has_provenance()` requires `query_count==4` AND `isinstance`. Synthetic path runs in default suite but CANNOT `PASS`. |

## Data Flow

### (1) Single-PR S5 stacked gating

```
master(895bb8f) ─┐
                 ├─ PR S5.1 (≤800) ─ stacked-to-main
   code fixes A/B/C/D · supabase/ CLI · tests
        │
   ── credentials window ──
   LIVE_SUPABASE=1 DB_URL=<direct>
   ├─ read-only receipts (A/B/C/D)
   ├─ EXPLAIN receipt (idx drop)
   ├─ 018 tracked apply (E) + DOWN
   └─ verify-report PASS → merge master v0.7.0
```

### (2) JWKS dual path — ES256 EC vs RS256

```
validate_supabase_key(key)
  ├─ sb_secret_ → RLS health_probe (guild+ticket) [opaque]
  └─ JWT
       ├─ alg=ES256 → _verify_jwt_jwks(algs=[RS256,ES256])
       │     PyJWKClient(kid=1) → EC P-256 verify ✓ (live)
       │     unknown kid → 1 refresh, else FAIL (no HS256 fallback)
       ├─ alg=RS256 → same path (proof, inert)
       └─ alg∉{RS256,ES256} → REJECT (alg confusion blocked)
```

### (3) 018 live 8-step — preflight 21/21 → EXPLAIN → tracked

```
supabase link → migrations symlink → migration up --linked
  OR tracked psql shell=False ON_ERROR_STOP lock_timeout=5s + repair --status applied
     │
  DO $preflight$ (21/21: 0 dups, 0 invalid UUID, 0 orphans, 1+1 audit)
     │ pass
  backup ticket_backup_categoryid_text_20260818
     │
  2 categoryId TEXT→UUID USING · 3 child indexes · 4 parentId RESTRICT
  5 categoryId SET NULL · 6 ticket_note CASCADE · 7 ticket_audit SET NULL · 8 VALIDATE
     │
  EXPLAIN (ANALYZE, BUFFERS) WHERE guildId=? AND ticketNumber=?
     ├─ Index Only Scan idx_ticket_guild_ticket_number, Heap Fetches=0 ✓
     ▼
  DROP idx_ticket_guild_number (sole drop) → schema_migrations ← 018 (tracked)
     │ fail → ON_ERROR_STOP aborts, DOWN restores TEXT, backup retained
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/services/live_catalog.py` | Modify | Scope `pg_policy`/`pg_constraint` to `public` via `pg_class`/`pg_namespace` JOIN (A/B) |
| `bot/config.py` | Modify | Rename `_verify_jwt_rs256`→`_verify_jwt_jwks`; allowlist `["RS256","ES256"]`; kid-bound (D) |
| `scripts/apply_staging_migration.py` | Modify | Tracked `psql shell=False` + `repair --status applied` post-apply; before/after report (E) |
| `migrations/018_ticket_integrity_fks.sql` | Modify | Confirm `DO $preflight$` + `lock_timeout='5s'` + `DOWN` present |
| `supabase/config.toml` | Create | One-time CLI linkage |
| `supabase/migrations` | Create | Symlink to `../migrations` |
| `tests/test_live_catalog.py` | Modify | Real `LIVE_SUPABASE=1`+`DB_URL` marker; scoped-query guards (A/B) |
| `tests/test_jwks_verifier.py` | Modify | ES256 case + alg-confusion rejection (D) |
| `tests/test_s4d2b_018_live.py` | Modify | `repair --status applied` post-apply + DOWN proof |
| `verify-report.md` (S4) | Modify | Verdict `pass_with_warnings`→`pass`; record real receipts |

## Contracts

```python
# live_catalog.py — scoped (A/B)
FK_QUERY = """SELECT conrelid::regclass::text AS child, confrelid::regclass::text AS parent,
  CASE confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL'
  WHEN 'r' THEN 'RESTRICT' ELSE confdeltype::text END AS on_delete
  FROM pg_constraint c JOIN pg_class cc ON cc.oid=c.conrelid
  JOIN pg_namespace n ON n.oid=cc.relnamespace WHERE c.contype='f' AND n.nspname='public'"""
POLICY_QUERY = """SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'"""
# config.py (D): _JWKS_ALGS = ["RS256", "ES256"]
# apply_staging_migration.py (E): REPAIR_NAMES for 3 desync + 018 post-apply
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | scoped queries (A/B); ES256 + alg-confusion (D); `repair` allowlist (E) | grep query text; mocked PyJWKClient EC; argv |
| Integration | `ProvenanceToken(4)` binds 9/7/0, 6 FKs, 4 pubs, 19↔19; mock→real zero delta | mocked `psycopg`; real marker |
| E2E live | `LIVE_SUPABASE=1 DB_URL=<direct> --run-live` → `1 passed`, 0 skipped | creds-gated; before/after report |
| DDL | preflight aborts bad data; 8-step order; DOWN restores TEXT | fixture dirty rows; assert preflight raises before cast |

## Threat Matrix

| Boundary | Applicability | Response | RED tests |
|---|---|---|---|
| Doc-like / Git repo / Commit / Push / PR | N/A — no routing, VCS, or PR automation | — | — |
| **Subprocess/shell** | **Applicable** — `psql` via `subprocess.run(shell=False)` | Fixed argv `["psql", url, "-v", "ON_ERROR_STOP=1", "-f", path]`; `shell=False`; allowlist rejects file ≠ `018_ticket_integrity_fks.sql`; `timeout` | (1) non-018 stem rejected; (2) `shell=False` asserted; (3) non-zero exit raises + retains backup |
| **Process integration** | **Applicable** — 018 DDL window + creds gate | `check_live_gate` requires `LIVE_SUPABASE=1`+`DB_URL`+`used_real_db=True`; `ON_ERROR_STOP` halts; `lock_timeout='5s'` aborts; `DOWN` restores | (1) missing creds → `passed=False`+warning; (2) preflight fail → no cast; (3) `lock_timeout` abort → backup retained |

## Rollback

- **Code PR**: single `git revert` — code-only (A/B/C/D) reverts cleanly; provenance hardened (real failure stays `FAIL`, no synthetic fallback).
- **018 DDL**: `DOWN` restores `TEXT categoryId`, drops 4 FKs, recreates `idx_ticket_guild_number`; backup retained 7d; `repair --status reverted 018`. No extra DDL beyond 018.
- **Pre-apply**: read-only catalog + EXPLAIN receipts (9/7/0, 6 FKs, 4 pubs, 19↔19, idx coverage) — no DDL.

## Open Questions

- [ ] `DB_URL` revocation deadline (Q1) — 018 in S5.1 or defer S5.2?
- [ ] Backup retention (Q6) — 7d default vs 30d scheduled cleanup.
- [ ] Post-018 rollback trigger (Q7) — bot startup health-check vs manual.

## Next Step

Ready for tasks (sdd-tasks).
