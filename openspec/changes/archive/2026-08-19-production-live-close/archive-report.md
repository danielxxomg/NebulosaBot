# Archive Report: production-live-close S5 — verify PASS (live MCP receipts)

**Change**: `production-live-close` — S5 S5.1 single PR production-live-close @ 48c6fe9 (from 895bb8f master)
**Branch**: `production-live-close-s5d1` @ 48c6fe9 — single PR stacked-to-main, 637 authored ≤800
**Date**: 2026-08-19
**Mode**: openspec
**Verdict**: `pass` — 5/5 requirements, 22/22 scenarios, 2094 passed 7 skipped, mypy 0, ruff 0, format 0, coverage 87.85%

## Goal

Close S4 synthetic `1p3s` (one-pass, three-scopes drift) as real production live — scoped catalog, repair-identified ledger, JWKS dual, live 018 DDL with EXPLAIN gate — proven by MCP-direct staging execution, not mocked provenance.

At S4 verification time the gate reported `PASS_WITH_WARNINGS` because live acceptance lacked a real `DB_URL`/`ProvenanceToken(4)` receipt (defaults to mocked `1p3s`). S5 S5.1 was defined to close exactly that provenance gap. This archive records the final state at close where the gap is resolved via real staging DDL session `vozkcckiybebhcclrasa` (Via-1, MCP `execute_sql`).

## MCP Session as Real Staging Receipt

MCP project `vozkcckiybebhcclrasa` (PG 17.6, Supabase) was executed via `execute_sql` direct — not a `FakeSupabase` mock — and is the canonical live evidence for S5. Before/after deltas:

- **Before** (TEXT 0-FK shadowing): `pg_typeof(ticket."categoryId")` → `TEXT`, 0 FK constraints validated, 21 rows with TEXT `categoryId`, 1 backup absent.
- **After** (UUID 4-FK validated): `pg_typeof` → `UUID` (21/21 cast), 4 FKs `convalidated=true` `contype='f'` scoped `nspname='public'` (`r/n/c/n` — `fk_ticket_parent_restrict` RESTRICT, `fk_ticket_category_set_null` SET NULL, `fk_ticket_note_cascade` CASCADE, `fk_ticket_audit_set_null` SET NULL), 1 audit orphan nulled (nullable `SET NULL` retained), `ticket_backup_categoryid_text_20260818` preserved for DOWN, `idx_ticket_guild_number` dropped (shadowed by unique `idx_ticket_guild_ticket_number` `idx_scan=15`), `EXPLAIN (ANALYZE, BUFFERS)` `Index Only Scan using idx_ticket_guild_ticket_number` `Heap Fetches: 0, Buffers: shared hit=1`, 9/7/0 scoped `public` catalog, 7 forced, 4 publications, 19 local ↔ 19 remote parity (+018 → 20).

This receipt supersedes any `LIVE_SUPABASE=1 DB_URL=mock` synthetic path. Per final-state authority, the archived `verify-report.md` § Live Execution Reconciliation is the final account; any intermediate `tasks.md` snapshot claiming missing live evidence is stale.

## Task Completion Gate — Exceptional Reconciliation

Persisted `tasks.md` at S5.1 showed `3.4 [ ]` (verify-report PASS flip) as the sole unchecked item. Per Task Completion Gate and Strict-vs-OpenSpec Archive Policy:

- `sdd-verify` now reports `verify-report.md` `verdict: pass` 5/5 22/22, proven via the MCP live receipts above — the code of 3.4 is complete.
- The checkbox was a stale artefact of the intermediate snapshot; `verify-report.md` and the MCP session prove every unchecked task complete.
- Reconciliation applied at archive: `tasks.md` line 3.4 checked with annotation `reconciled at archive: verify-report.md now verdict: pass 5/5 22/22 via MCP vozkcckiybebhcclrasa` — mechanical proof retained, no silent overwrite.

No other task remains unchecked. Archived `tasks.md` is 18/18 complete.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `live-schema-verifier` | Updated | MODIFIED 2 (Modern secret-key probe → dual RS256+ES256 kid-bound bounded refresh; Catalog-backed parity → scoped `JOIN pg_class/pg_namespace nspname='public'` + tracked `repair --status applied` 3-name allowlist + psql bypass rejection), ADDED 1 (Provenance token 4-query binding — synthetic `1p3s` cannot PASS). Wrapped in `<!-- BEGIN DELTA: production-live-close S5 -->`. Prior deltas preserved. |
| `database-layer` | Updated | MODIFIED 2 reasserted (Credential-gated 018: tracked `supabase link` + backup/lock/ON_ERROR_STOP/DOWN eight-step contract with S5 S5.1 hardening; Evidence-based index retention: `EXPLAIN (ANALYZE, BUFFERS)` `Index Only Scan` 0 heap before sole `idx_ticket_guild_number` drop — S5 requires receipt live before DROP). Wrapped in `<!-- BEGIN DELTA: production-live-close S5 -->`. All prior deltas preserved. |

**Merge policy**: preserved all requirements not in delta; matched by heading name; maintained Markdown hierarchy; no `REMOVED`/`RENAMED` in this delta.

## Archive Contents

- `proposal.md` ✅ intent + S5.1 scope (scoped catalog + 19repair + JWKS + 018 + EXPLAIN, single PR ≤800)
- `specs/live-schema-verifier/spec.md` ✅ delta (dual JWKS + scoped 9/7/0 29→6 + provenance)
- `specs/database-layer/spec.md` ✅ delta (018 8-step backed + EXPLAIN gate + tracked application)
- `design.md` ✅ S5.1 technical design (scoped queries, repair linkage, JWKS migration, 018 ordering)
- `exploration.md` ✅ S4→S5 provenance deep-dive (1p3s synthetic → real MCP path)
- `tasks.md` ✅ 18/18 complete (after archive-time 3.4 reconciliation with verify-report proof)
- `verify-report.md` ✅ `verdict: pass` 5/5 22/22, MCP vozkcckiybebhcclrasa receipts
- `archive-report.md` ✅ this report (additive-only, excluded from mechanical `diff -r`)

## Mechanical Copy Contract

Archive copy used `git mv` (tracked) verified by `diff -r` — verbatim output included:

```
diff -r /tmp/sdd-archive.rlNcu2/source openspec/changes/archive/2026-08-19-production-live-close
(empty — no differences)
```

Empty `diff -r` is the only passing evidence. Sourced from pre-move recursive snapshot vs. archived tree; `archive-report.md` is additive-only and excluded.

Spec deltas were applied via direct file write (not `cp -R` of spec delta files) — merges preserve prior deltas and add S5 blocks, not byte-copy of delta.

## Verification at Close

- Build `python -m py_compile bot/__main__.py` ok
- `mypy bot tests` 0 errors (181 files)
- `ruff check bot tests scripts` 0 (181 files), `ruff format --check` 0 (184 files)
- `uv run pytest -q` 2094 passed 7 skipped, 87.85% ≥ 75% — 24 S5.1 TDD suite + 2070 baseline, no regressions
- Budget 637 authored lines ≤800 single stacked-to-main PR (12-file total 1552 = 637 + 915 provenance/docs)
- 9/7/0 scoped `public` (`pg_policy JOIN pg_class JOIN pg_namespace nspname='public'`), 7 forced, 0 policies, 4 publications, 6→4 FKs VALIDATED live, 19↔19 ledger (20 after 018)
- JWKS dual `["RS256","ES256"]` kid=1 bounded refresh, HS256 rejected, `iss/aud/exp/role` required — live ES256 EC P-256 `kid=1` verified
- `supabase/config.toml` + `supabase/migrations` → `../migrations` symlink, `repair --status applied` fixed argv `shell=False` for exactly 3 desync names, tracked 018 application, `lock_timeout=5s` `ON_ERROR_STOP=1`, backup retention
- `EXPLAIN (ANALYZE, BUFFERS)` Index Only Scan 0 heap fetches proven before `DROP idx_ticket_guild_number` only
- CRITICAL 0, blockers 0

## Source of Truth Updated

- `openspec/specs/live-schema-verifier/spec.md` — now reflects live-verified scoped catalog + JWKS dual + 19↔19 repair + provenance 4-query binding
- `openspec/specs/database-layer/spec.md` — now reflects live-gated 018 8-step ordered execution + EXPLAIN-gated index retention with required S5 hardening

## Accomplished

- ✅ S5.1 @ 48c6fe9 delivered via MCP `execute_sql` direct (Via-1), not mocked `LIVE_SUPABASE` synthetic — real DDL `TEXT`→`UUID` with `USING` cast 21/21, 4 FKs VALIDATED (`r/n/c/n`), audit 1 nulled preserved, backup `ticket_backup_categoryid_text_20260818` retained, `idx_ticket_guild_number` dropped under EXPLAIN + Buffers gate, shadow dropped proven `idx_scan=15`
- ✅ Catalog scoping fixed: `POLICY_QUERY` + `FK_QUERY` both `JOIN pg_class`/`pg_namespace WHERE nspname='public'` — unscoped 9/7/2 (pg_cron) and 29 (auth/storage) false-fails rejected — live 9/7/0 proven
- ✅ 19↔19 ledger reconciled via tracked `repair --status applied` allowlist 3 (`greeting_onboarding_channel`, `add_tables_to_realtime_publication`, `add_realtime_publication_tables`), `supabase/migrations` symlink + `supabase/config.toml`, 19 local ↔ 19 remote → 20 after 018
- ✅ JWKS dual `PyJWKClient` kid-bound `["RS256","ES256"]` — live ES256 EC P-256 `kid=1` verifies, HS256 rejected, unknown kid ≤2 attempts then FAIL, RS256 still verified (inert)
- ✅ 24 TDD RED→GREEN (`tests/test_production_live_close_s5_tdd.py` 6 suites: S5Scoping 4, JwksDual 5, RepairAllowlist 4, SubprocessShell 5, ProcessIntegration 4, EvidenceWiring 2) + gates mypy/ruff/format + `uv run pytest` 2094

## Next Steps

- None — chain S1–S5 closed. S6 would be production windows only (no new synthetic scope).
- S5 archived; active changes directory no longer contains `production-live-close`.
- Future CI may surface MCP receipts (`vozkcckiybebhcclrasa`) as `live-mcp-vozkcckiybebhcclrasa` artifact alongside `ProvenanceToken(4)` psycopg path.

## Relevant Files (final-state authority)

- `openspec/specs/live-schema-verifier/spec.md` — source of truth including S5 delta (this archive)
- `openspec/specs/database-layer/spec.md` — source of truth including S5 delta (this archive)
- `openspec/changes/archive/2026-08-19-production-live-close/` — full audit trail (proposal, specs×2 deltas, design, exploration, tasks 18/18, verify-report PASS 5/5 22/22, this archive-report)
- `openspec/changes/archive/2026-08-19-production-live-close/verify-report.md` — terminal S5 verification (MCP Live Execution Reconciliation — authoritative)
- `bot/services/live_catalog.py` — `POLICY_QUERY`/`FK_QUERY` scoped public + `ProvenanceToken(query_count==4)` in `_sync_fetch_catalog`
- `bot/config.py` — `_verify_jwt_jwks`, `_JWKS_ALGS=["RS256","ES256"]`, kid-bound bounded refresh
- `scripts/apply_staging_migration.py` — `supabase link` + tracked 018 + `shell=False ON_ERROR_STOP=1 lock_timeout 5s` + `EXPLAIN` + before/after LiveEvidenceReport + repair argv
- `supabase/config.toml` + `supabase/migrations` symlink — tracked linkage
- `migrations/018_ticket_integrity_fks.sql` — DO $preflight$ 21/21 + 8-step USING/3 indexes/4 FKs VALIDATE + DROP idx_ticket_guild_number only + DOWN
- `tests/test_production_live_close_s5_tdd.py` — 24 TDD RED suite (377 lines)
- `bot/services/schema_inventory.py` / `bot/core/db/base.py` — binder + health probes supporting live catalog

## Intentional Archive Declaration

- `tasks.md` 3.4 stale-checkbox reconciliation is intentional, backed by `verify-report.md` `verdict: pass` and MCP live DDL receipts — not a scope reduction.
- No CRITICAL issues exist to waive (verify-report: 0 critical, 0 blockers). No scope was dropped; all 5/5 req 22/22 proven.
