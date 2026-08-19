# Staging Live Parity — S4 Runbook

Staging proof for deferred S3 evidence: real credential gate, direct catalog, tracked 018 8-step DDL, EXPLAIN index policy, and RS256/HW256 JWT rotation. Stacked-to-main final slice (S4.3) — **docs-only**, no DDL or code moves.

> **S4 gates** — every change MUST stay `mypy 0 · ruff 0 · 2030+ passed` and live `LIVE_SUPABASE=1 DB_URL=… uv run pytest -m live --run-live -q` must prove a **real DB path**, not a fake. Mocked `PASS_WITH_WARNINGS` is rejected.

## Quick path (happy path)

1. Ensure staging creds present: `LIVE_SUPABASE=1` + `DB_URL` (or `SUPABASE_DB_URL`/`DATABASE_URL`) + `SUPABASE_URL` + `SUPABASE_KEY` + JWKS vars below.
2. Verify gates before any live window:
   ```bash
   uv run mypy bot tests
   uv run ruff check bot tests scripts
   uv run pytest -q
   python -m py_compile bot/__main__.py
   uv run pytest -m live --run-live --no-cov -q           # fails with warning when creds absent
   LIVE_SUPABASE=1 DB_URL=postgresql://… uv run pytest -m live --run-live --no-cov -q  # real DB path
   ```
3. In the approved staging window: backup → timeouts → tracked `psql` 018 → validate → post-catalog evidence → revoke creds.
4. Index receipt: `EXPLAIN (ANALYZE, BUFFERS)` on representative workload before any drop beyond the duplicate.

## Credential window and revocation

| Topic | Decision |
|-------|----------|
| Gate flag | `LIVE_SUPABASE=1` is required — no real proof without it; missing marker fails acceptance with a gate reason. |
| Real DB URL | `DB_URL` is primary; `SUPABASE_DB_URL` and `DATABASE_URL` are accepted variants. Every live helper (`live_catalog`, `apply_staging_migration`) resolves in that priority and warns/blocks without a real URL. `FakeSupabase` never `PASS`es. |
| Supabase creds | `SUPABASE_URL` + `SUPABASE_KEY` (`sb_secret_` modern or verified JWT legacy). `health_probe` read-only `guild`/`ticket` probes stay fail-closed. |
| JWKS creds | `SUPABASE_JWKS_URL` (or `SUPABASE_JWKS_URI`/`JWKS_URL`) + `SUPABASE_JWT_ISSUER` + `SUPABASE_JWT_AUDIENCE` — required for RS256 path (see JWT rotation). |
| Window | Short-lived secrets (`sb_secret_`, `DB_URL`) only for the S4 window. Create from the staging project's dashboard/connection string, use, then revoke/rotate immediately after S4.2 evidence is captured. |
| Revocation | After the window: revoke/rotate the short-lived secrets in the provider dashboard, unset `DB_URL`/`LIVE_SUPABASE` in the shell, and verify `uv run pytest -m live --run-live -q` returns to the warning path. The 018 `DOWN` backup `ticket_backup_categoryid_text_20260818` is retained until parity is accepted; then drop at operator discretion. |

**Read-only contract:** live acceptance and 018 application issue only `SELECT`/`EXPLAIN`/migration DDL via `psql -v ON_ERROR_STOP=1 -f migrations/018_ticket_integrity_fks.sql` (`shell=False`, fixed argv). No untracked SQL-editor `execute_sql` substitute.

## 018 DDL — 8-step tracked execution

### Preconditions

- Low-traffic window, backup captured before any cast, `lock_timeout = '5s'` and `statement_timeout = '30s'` set (guarded inside the migration).
- `LIVE_SUPABASE=1` + real `DB_URL` gate passes (`check_live_gate` / `LiveAcceptanceGate`).

### Ordered steps (preserved in `migrations/018_ticket_integrity_fks.sql`)

1. **Preflight** `DO $preflight$` — aborts before any `TEXT→UUID USING` cast on: `idx_ticket_active_slot` / `idx_ticket_active_channel` / `idx_ticket_guild_number` duplicates, `21/21` invalid `categoryId` UUIDs, missing/deep `parentId` (depth 1), `ticket_note` orphans (`0`), `ticket_audit` retention (`1 orphan + 1 guild mismatch` only). Any `RAISE EXCEPTION` prevents steps 2–8.
2. **`ticket.categoryId TEXT → UUID USING`** cast with explicit `USING` and backup `ticket_backup_categoryid_text_20260818` (restore `TEXT` via `DOWN`).
3. **Child indexes** for `parentId` / `ticket_note.ticketId` / `ticket_audit.ticketId`.
4. **`parentId → ticket.id ON DELETE RESTRICT`**.
5. **`categoryId → ticket_category.id ON DELETE SET NULL`**.
6. **`ticket_note.ticketId → ticket.id ON DELETE CASCADE`**.
7. **`ticket_audit.ticketId → ticket.id ON DELETE SET NULL`** (nullable + `NULL` cleanup for retained orphan/mismatch).
8. **`VALIDATE CONSTRAINT` + application checks**, then **drop only `idx_ticket_guild_number`** — the sole duplicate shadowed by unique `idx_ticket_guild_ticket_number` (`0` scans vs `11`). `idx_ticket_channel` and all other indexes remain.

### Witnessed live evidence in S4.2B

- Preflight inputs `21 tickets, 5 active; 0 invalid UUID; 0 category orphans; 0 missing/deep parents; 0 note orphans; 1 audit orphan + 1 audit guild mismatch` belong to the repository's live baseline — the migration must prove them before step 2 in every live execution.
- Before/after catalog capture is implicit via the migration's backup + `VALIDATE` + `pg_constraint`/`supabase_migrations` reads; the application suite runs after step 8.

### Rollback and timeouts

| Step | Rollback |
|------|----------|
| Preflight fail | Abort — no schema/ticket mutation attempted. Investigate duplicate/UUID/orphan counts. |
| After start (lock/timeout or cast/FK failure) | Abort `psql` on non-zero exit / timeout; run the `DOWN migration` section in the same file (drops new constraints/indexes, restores `ticket.categoryId TEXT` via `ticket_backup_categoryid_text_20260818`), then restore from the pre-window DB backup if `DOWN` cannot recover. `lock_timeout`/`statement_timeout` are set at the top of the file. |
| Post-apply drift | Re-verify `9/7/0`, `6 FKs`, `4 pubs`, `19 identity`, typed `categoryId`; run `uv run pytest -m live --run-live -q` with `DB_URL`; revert commits with `git revert` if DDL must be unwound. |

### Tracked command

```bash
# Approved staging window only — tracked file, fixed argv, no shell composition
LIVE_SUPABASE=1 DB_URL=postgresql://… uv run python scripts/apply_staging_migration.py --timeout 60
# Equivalent raw psql (helper builds this argv):
psql "$DB_URL" -v ON_ERROR_STOP=1 -f migrations/018_ticket_integrity_fks.sql
```

## EXPLAIN workload — index retention receipt

### Policy

`EXPLAIN (ANALYZE, BUFFERS)` on a **representative staging workload** is required before dropping any index beyond the already-approved duplicate. A zero cumulative count in `pg_stat_user_indexes` **alone MUST NOT** authorize a drop — the view is cumulative, the database is small, and a single-copy workload is not coverage proof. The S4.3 runbook MUST document a receipt for the duplicate and retain the other indexes.

### Receipt for the sole allowed drop

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM ticket
WHERE "guildId" = :g AND "ticketNumber" = :n;
-- Buffers: shared hit/read, actual rows 1 — proves unique
-- idx_ticket_guild_ticket_number (unique ("guildId","ticketNumber")) covers
-- idx_ticket_guild_number; pg_stat_user_indexes: 0 vs 11 scans supports the
-- already-approved duplicate decision.
```

### Remaining 12 indexes — retained without a separate receipt

All 12 `UNUSED_INDEXES_FOR_REVIEW` entries stay **unless a future change supplies its own `EXPLAIN` workload** proving replacement:

- `idx_member_guild`, `idx_infraction_guild_target`, `idx_ticket_guild_status`, `idx_ticket_category_guild`, `idx_member_guild_xp`, `idx_member_guild_coins`, `idx_ticket_parent`, `idx_ticket_note_ticket`, `idx_ticket_note_created`, `idx_ticket_audit_ticket_history`, `idx_ticket_audit_guild_created`
- **`idx_ticket_guild_number`** — allowed duplicate drop above
- **`idx_ticket_channel`** — retained: closed-channel lookups (`channelId`) have independent selectivity; no `EXPLAIN` receipt proves its redundancy

### How to collect the EXPLAIN evidence

```bash
# With real DB_URL — prefer direct psql so EXPLAIN reflects staging planner
psql "$DB_URL" -c "EXPLAIN (ANALYZE, BUFFERS) SELECT …"
# Keep the output with Buffers/rows as the receipt; attach to the PR or this runbook.
```

## JWT rotation

### Modes

- **RS256 via JWKS (`jwks_uri`)** — modern path. `bot/config.py::_verify_jwt_rs256` uses `PyJWKClient(jwks_uri)` with `algorithms=["RS256"]`, required `role`, `iss`, `aud`, `exp`, and a **bounded `kid` refresh of at most 3 attempts**.
- **HS256 legacy allowlist** — `PyJWT` with `SUPABASE_JWT_SECRET` and `algorithms=["HS256"]`, required `role/iss/aud/exp`. Preserved for legacy `service_role` JWTs; does NOT accept RS256 tokens without JWKS.

### Required env and claims

| Env | Purpose |
|-----|---------|
| `SUPABASE_JWKS_URL` (or `SUPABASE_JWKS_URI` / `JWKS_URL`) | JWKS endpoint, e.g. `https://<project>.supabase.co/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_ISSUER` | Expected `iss` claim |
| `SUPABASE_JWT_AUDIENCE` | Expected `aud` claim |
| `SUPABASE_JWT_SECRET` | HS256 legacy secret (HS256 path only) |

Required claims in every verified token: **`iss`, `aud`, `exp`, `role`**. Missing any required claim, wrong `iss`/`aud`, expired `exp`, or `role != "service_role"` → rejected without fallback. `exp` is required via `options={"require": ["exp","iss","aud"]}`.

### Rotation — bounded `kid` refresh

When a token's `kid` header is unknown to the current JWKS cache, the RS256 verifier may retry **once per refresh cycle up to 3 bounded attempts**, each constructing a fresh `PyJWKClient(jwks_uri).get_signing_key_from_jwt(token)` — intended to pick up a newly published rotation key. If the `kid` is still unresolved, verification **fails closed without HS256 or payload-only fallback**. Non-`kid` errors (e.g. bad signature, wrong `alg`, bad `iss`/`aud`/`exp`) fail immediately without retry.

JWKS discovery/client caches can lag rotation; Supabase rotation can trust current and previously used keys and discovery may delay visibility — operators should wait for JWKS propagation or trigger a fresh `PyJWKClient` refresh on the next request.

### Algorithm confusion blocked

Tokens whose `alg` header is not `RS256` are rejected by the RS256 path without attempting JWKS; the HS256 path only allows `["HS256"]`. `alg=none` or `hs256`-as-`rs256` confusion is blocked. HS256 tokens are never verified through the JWKS path and RS256 tokens never through the HS256 secret.

### Rotation procedure (operator)

1. Publish the new signing key at the JWKS endpoint (`jwks_uri`).
2. Wait for clients to pick up the new `kid` (next request performs a bounded `PyJWKClient` refresh); existing tokens signed by the previous key remain valid until `exp` or JWKS removal.
3. Retire the old key only after its last token's `exp` has passed and no active client holds its `kid`.
4. Verify: `uv run pytest tests/test_jwks_verifier.py -q` asserts valid sig ok, bad sig fail, `kid` refresh once-then-success, bounded `kid` miss fail, missing `iss`/`aud`/`exp`/`role` fail, `alg` confusion fail, HS256 allowlist retained.

## GUILD_SCOPE_GAPS — historical rename note

The 12-name inventory `GUILD_SCOPE_GAPS` (ID-only DB methods that are not directly guild-scoped without a service check) is now canonically **`GUILD_SCOPE_GAP_HISTORY`** — a **historical** ledger retained for report/tests. A separate runtime assertion **`guild_scope_runtime_closed == 12`** records that the S4.1 live catalog now enforces guild ownership at runtime (12/12), so the historical list is **not an active blocker** despite its preservation. Tests and report models reference `GUILD_SCOPE_GAP_HISTORY`; `GUILD_SCOPE_GAPS` remains as a deprecated alias for backward compatibility.

## Live parity acceptance

| Check | Command | Expected |
|-------|---------|----------|
| Types | `uv run mypy bot tests` | `0 errors` |
| Lint/format | `uv run ruff check bot tests scripts` · `uv run ruff format --check bot tests scripts` | clean |
| Baseline | `uv run pytest -q` | `2030 passed 7 skipped` (or higher after S4.3), no failures |
| Live no-creds | `uv run pytest -m live --run-live --no-cov -q` | warning path — gate fails, no mocked PASS |
| Live real DB | `LIVE_SUPABASE=1 DB_URL=postgresql://… uv run pytest -m live --run-live --no-cov -q` | `4 passed` (incl. real DB/RPC) |

## Checklist

- [ ] Staging window approved, low-traffic, before/after catalog baseline captured
- [ ] `LIVE_SUPABASE=1` + real `DB_URL` gate passes (`used_real_db == True`)
- [ ] `mypy 0`, `ruff 0`, `uv run pytest -q` green; `python -m py_compile bot/__main__.py` clean
- [ ] 018 applied via tracked `psql -f migrations/018_ticket_integrity_fks.sql` only; `EXPLAIN` receipt attached; only `idx_ticket_guild_number` dropped
- [ ] JWT `jwks_uri` + bounded `kid` refresh + `iss/aud/exp/role` + RS256/HS256 allowlist verified (`test_jwks_verifier.py`)
- [ ] `GUILD_SCOPE_GAP_HISTORY` 12 + `guild_scope_runtime_closed == 12` confirmed
- [ ] Short-lived creds (`sb_secret_`, `DB_URL`) revoked/rotated after evidence capture

## References

- `bot/config.py` — `_verify_jwt_rs256` (JWKS RS256 + bounded `kid` refresh, `iss/aud/exp/role`, `alg` allowlist; HS256 legacy via `SUPABASE_JWT_SECRET`)
- `bot/services/live_catalog.py` — `LiveAcceptanceGate` (real DB/RPC only, 19 exact identity, `PGRST205` disclaimer)
- `bot/services/schema_inventory.py` — `GUILD_SCOPE_GAP_HISTORY` (12 historical) + `GUILD_SCOPE_RUNTIME_CLOSED`
- `scripts/apply_staging_migration.py` — `build_psql_argv` (`shell=False`, `ON_ERROR_STOP`, 018 allowlist, `check_live_gate`), `BACKUP_TABLE = ticket_backup_categoryid_text_20260818`
- `migrations/018_ticket_integrity_fks.sql` — 8-step ordered DDL + backup/timeouts/`DOWN`
- `tests/test_s4d3_runbook.py` / `tests/test_jwks_verifier.py` / `tests/test_live_catalog.py` / `tests/test_s4d2b_018_live.py`
