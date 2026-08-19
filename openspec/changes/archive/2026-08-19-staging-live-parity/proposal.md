# Proposal: staging-live-parity S4 — Real Staging Proof for Deferred S3 Evidence

## Intent

Prove deferred S3 evidence with real staging creds. `a80f129` green (1968/87.80% mypy0 ruff0) but live mocked: 018 unapplied, catalog `PGRST205`, no JWKS, fake tests. S4 applies 018, proves catalog via DB/RPC, adds RS256 JWKS, enforces EXPLAIN index policy under strict gates. Refs: `Diagramas/DiagramaEntidad-Relación.mmd`, `DiagramaSecuencia.mmd`, `Ecosistema-Comandos.mmd`.

## Scope

### In Scope
- 4 stacked PRs to `main` (`auto-chain`, ≤800): **S4.1** JWKS/RS256 + `HISTORICAL` rename + 73%→80% (~400); **S4.2A** catalog DB/RPC 19-identity; **S4.2B** 018 8-step; **S4.3** docs/runbook.
- Real creds: `LIVE_SUPABASE=1` + `DB_URL` direct; mocked fallback default suite only, never acceptance.
- JWKS RS256 via `jwks_uri` + rotation; dual HS256 allowlist.
- EXPLAIN `(ANALYZE, BUFFERS)` on staging workload before any drop beyond dupe.

### Out of Scope
- New features, economy CDC, dashboard auth RLS policies, migrations beyond 018.
- Drops beyond EXPLAIN; sentinel debt outside changed files; untracked SQL-editor DDL.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `live-schema-verifier`: RS256/JWKS + DB/RPC parity (9/7/0, 6 FKs, 4 pubs, 19 identity) + strict gate.
- `database-layer`: ordered 018 DDL + preflight + `GUILD_SCOPE_GAPS`→`HISTORICAL` + runtime assertion.
- `bot-core`: JWT HS256 legacy + RS256 JWKS (`PyJWKClient`, `kid`, `iss/aud/exp`).

## Approach

- **S4.1** — Keep HS256 `sb_secret_` probe fail-closed. Add `PyJWT[crypto]` + `PyJWKClient` RS256, required `role/iss/aud/exp`, bounded `kid` refresh (no fallback). Rename to `GUILD_SCOPE_GAP_HISTORY` + `guild_scope_runtime_closed==12`. Polish repair/panel to 80%; overflow → S4.3.
- **S4.2A** — Direct SQL via `psql`/MCP with staging creds (bypass `PGRST205`): `pg_constraint`, `pg_policy`, `pg_publication_tables`, `pg_stat_user_indexes`, `supabase_migrations.schema_migrations`. Exact version/name reconcile.
- **S4.2B** — Window: backup + timeouts + DO preflight (21 tickets, 0 invalid UUIDs, 0 orphans, depth1, audit 1/1) → `TEXT→UUID USING` → indexes → FKs (`RESTRICT`/`SET NULL`/`CASCADE`) → `VALIDATE` → drop `idx_ticket_guild_number` only.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/config.py`, `pyproject.toml` | Modified | RS256/JWKS + `PyJWT[crypto]` dep |
| `bot/services/schema_inventory.py` | Modified | DB/RPC adapter, identity, rename |
| `migrations/018*.sql` | Modified | Tracked execution + rollback |
| `bot/services/ticket_repair_service.py`, `bot/views/ticket_panel.py` | Modified | Polish 80% |
| `Diagramas/*.mmd` | Referenced | ER / sequence / ecosystem |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Creds window | Med | Short-lived `sb_secret_`/`DB_URL`, revoke after S4.2; acceptance FAILS without real creds |
| DDL lock (`VALIDATE`=`SHARE UPDATE EXCLUSIVE`) | Med | Timeouts + backup + approved window + abort on preflight fail |
| JWKS rotation lag | Med | Bounded `kid` refresh; explicit `iss/aud`; no HS256↔RS256 confusion |
| PGRST205 gap | Low | Direct catalog SQL; PostgREST fail-closed |

## Rollback Plan

Each PR `git revert`. S4.1 code-only. S4.2A evidence-only. S4.2B needs backup + `DOWN` before apply; abort pre-DDL on fail; validate or restore post-apply. No untracked `execute_sql`.

## Dependencies

Baseline `a80f129` (1968/87.80% mypy0 ruff0), project `vozkcckiybebhcclrasa` PG17.6 `sa-east-1`, staging creds this week, S3 archive 21/21, `Diagramas/*.mmd`.

## Success Criteria

- [ ] 4 PRs ≤800, mypy0 ruff0, 1968+ passed + live `1 passed 1 passed` real DB (not `FakeSupabase`); mocked `PASS_WITH_WARNINGS` rejected.
- [ ] 018 applied live: 9/7/0 RLS, 6+4 FKs, 4 pubs, `categoryId uuid`, only dupe index dropped.
- [ ] JWKS RS256 via `jwks_uri` + rotation; HS256 preserved; algo confusion blocked.
- [ ] Remaining 12 indexes dropped only if `EXPLAIN (ANALYZE, BUFFERS)` proves unused.
