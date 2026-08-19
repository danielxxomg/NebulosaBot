## Exploration: staging-live-parity — S4

### Current State

S4 starts from clean `master` at `a80f129`. The S3 archive is internally green but explicitly leaves remaining S4 concerns: real staging catalog access, live execution of migration 018, asymmetric JWT verification, the misleading historical guild-scope ledger name, and low changed-file coverage in repair/panel paths. The current checkout has no active `staging-live-parity` artifacts; this file is the first artifact for the change.

#### Repository and quality evidence

| Check | Current result | Assessment |
|---|---:|---|
| `uv run pytest -q` | 1968 passed, 5 skipped; 87.80% | Green baseline |
| `uv run mypy bot tests` | 0 errors, 173 files | Green hard gate |
| `uv run ruff check bot tests scripts` | Clean | Green hard gate |
| `uv run ruff format --check bot tests scripts` | 175 files formatted | Green formatting gate |
| Focused S3 verifier tests | 54 passed, 2 skipped | Structural/fake evidence only |
| `uv run pytest -m live --run-live --no-cov -q` | 1 passed, 1 skipped | **Not real live access**; both live tests use `FakeSupabaseClient` or mocked evidence |
| Migration files | 19 local SQL files | Includes 018, but repository has no `supabase/config.toml` or `supabase/` directory |
| PyJWT | 2.13.0 importable; `PyJWKClient` available; cryptography 49.0.0 | Transitive in `uv.lock`, not a direct project/runtime dependency |

The process environment has no `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWKS_URL`, `LIVE_SUPABASE`, or `RUN_LIVE`. A `.env` file exists with only `DISCORD_TOKEN`, `SUPABASE_URL`, and `SUPABASE_KEY` names; its values were not read or emitted. Therefore the local application/test process cannot currently prove a credential-backed path.

#### Credential and health paths

- `bot/core/db/base.py::DatabaseBase.health_probe()` performs two sequential read-only PostgREST probes: `guild.id`, then `ticket.id`. `connect()` clears `_client` and raises when either probe fails, so the existing `sb_secret_` path is fail-closed.
- `bot/config.py::validate_supabase_key()` accepts opaque `sb_secret_` keys for later probe validation and verifies legacy JWTs only through PyJWT HS256 with `SUPABASE_JWT_SECRET`. The existing payload decoder is not cryptographic verification. There is no RS256/JWKS branch, issuer/audience policy, JWKS URL configuration, or rotation test.
- The recommended S4 implementation should keep HS256 only for explicitly supported legacy keys, add a direct PyJWT dependency with RSA crypto support, and use `PyJWKClient`/`kid` selection with `algorithms=["RS256"]`, required `role`, `iss`, `aud`, and time claims. A cache refresh path is required when a rotated key is not found.

#### Guild-scope ledger

`bot/services/schema_inventory.py::GUILD_SCOPE_GAPS` is a 12-name historical inventory. The runtime DB methods and extracted callers now enforce guild ownership; S3 tests establish 12/12 runtime closure. However, the name still reads as an active defect list, and `SchemaInventory` plus tests continue to expose it as `guild_scope_gaps`. Rename the canonical constant to `GUILD_SCOPE_GAP_HISTORY` (or an equivalently explicit historical name), update report fields/tests/docs, and add a separate runtime assertion such as `guild_scope_runtime_closed == 12` rather than using the historical tuple as a blocker count.

#### Catalog and migration paths

`fetch_live_metadata()` currently issues four PostgREST reads against `pg_constraint`, `pg_policies`, `pg_publication_tables`, and `supabase_migrations`. It intentionally raises/fails closed on `PGRST205`, and its module docstring only documents a future DB/RPC staging path. The live project has no catalog/parity RPC function. The actual migration ledger is `supabase_migrations.schema_migrations`, not `public.supabase_migrations`.

The binder currently resolves any 19-row migration list containing `015`; it does **not** compare exact remote migration versions/names to the local ledger. S4 must make the identity reconciliation explicit: remote has 19 entries, including remote-only `005_rls_secure_default`, two Realtime publication entries, and `greeting_onboarding_channel`; local has 19 files including `005_rls_secure_default.sql`, `017_ticket_audit_repaired_outcome.sql`, and `018_ticket_integrity_fks.sql`. Count equality is not parity.

#### Live Supabase evidence

Read-only Supabase SQL/MCP evidence was obtained from project `nebulosabot` (`vozkcckiybebhcclrasa`, `ACTIVE_HEALTHY`, PostgreSQL `17.6.1.155`, `sa-east-1`):

- RLS: 9 public tables enabled, 7 forced, 0 public policies.
- Realtime: exactly `guild`, `greeting_config`, `ticket`, and `ticket_note`.
- Foreign keys: only the six existing child-to-`guild` `ON DELETE CASCADE` constraints. The four 018 ticket/note/audit constraints are absent.
- Types: `ticket.categoryId` remains nullable `text`; `ticket.parentId` is nullable `uuid`; `ticket_note.ticketId` and `ticket_audit.ticketId` remain `uuid NOT NULL`.
- Migration ledger: 19 rows in `supabase_migrations.schema_migrations`; 018 is not applied.
- Preflight facts: 21 tickets, 5 active; invalid category UUIDs 0; category orphans 0; missing parents 0; parent depth violations 0; note orphans 0; audit orphans 1; audit guild mismatches 1.
- Index evidence: `idx_ticket_guild_number` has 0 scans, the unique `idx_ticket_guild_ticket_number` has 11, and `idx_ticket_channel` has 1. `pg_stat_user_indexes` is cumulative and the database is small; this supports the already-approved duplicate-index decision but not broad index deletion.

Migration `018_ticket_integrity_fks.sql` is present and 327 lines long. Structural inspection confirms preflight → explicit `TEXT` to `UUID USING` cast → child indexes → parent/category/note/audit FKs → validation → only `idx_ticket_guild_number` drop. It contains backup, lock/statement timeouts, and a documented DOWN section. It has not been executed against staging in this exploration because it mutates schema/data and requires an explicit deployment/rollback window; Supabase documentation requires remote changes to go through tracked migrations/`supabase db push`, not an ad-hoc SQL editor change.

#### Coverage gaps for polish

The full run confirms the S3 warning values: `bot/services/ticket_repair_service.py` is 73% (72 missed statements) and `bot/views/ticket_panel.py` is 73% (54 missed). High-value missing ranges are:

- `ticket_repair_service.py`: denied/error audit branches `98-99`, `137-138`; channel-delete lookup failure `229-243`; sweep discovery/candidate error paths `280-335`; reference parse/lookup failures `457-481`; manual repair DB/not-found paths `639-670`; best-effort audit failure `729-730`; channel-row cleanup/rename failures `805-809`, `819-820`; transcript/config/silent-delete failures `838-860`, `872-875`; countdown NotFound/HTTP fallback paths `899-923`.
- `ticket_panel.py`: facade/i18n fallback `32-33`, `55-56`; modal config/category/Discord/invariant error paths `95-115`, `132-142`, `163-186`, `205-229`; modal error/fallback branches `333-334`, `375-376`, `389-398`; panel interaction fallback/no-category/select construction `432-433`, `459-478`.
- `bot/cogs/sentinel.py` is 77% in the full report, so sentinel error/no-result/permission branches should be targeted only where S4 changes or relies on them. Do not inflate S4 with unrelated sentinel debt.

### Affected Areas

- `bot/config.py` — add the RS256/JWKS verification path while preserving fail-closed HS256 and opaque `sb_secret_` behavior.
- `pyproject.toml`, `requirements.txt`, `uv.lock` — make PyJWT/RSA crypto a direct runtime dependency instead of relying on a transitive lock entry.
- `bot/services/schema_inventory.py` — replace PostgREST-only catalog assumptions with an explicitly credential-gated DB/RPC adapter; compare exact migration identity; rename the historical guild ledger.
- `tests/test_s3d1_guardrails.py`, `tests/test_config.py`, new JWKS tests — cover valid/invalid RSA signatures, `kid` rotation, issuer/audience/expiry, algorithm confusion, HS256 regression, and missing credentials.
- `tests/test_schema_inventory_verifier.py`, new live tests — retain mocked fallback for the default suite but add a real opt-in staging catalog assertion. A `LIVE_SUPABASE=1` flag must no longer turn a FakeSupabase test into a claimed live pass.
- `migrations/018_ticket_integrity_fks.sql` and migration harness/config — run preflight and DDL only through an approved staging migration path, capture before/after catalog evidence, and prove rollback or an accepted post-apply state.
- `bot/services/ticket_repair_service.py`, `bot/views/ticket_panel.py`, targeted Sentinel tests — cover the missing error, fallback, no-op, and Discord exception branches; keep the polish bounded to changed behavior and the 80% changed-file target.
- `tests/test_schema_inventory_verifier.py`, `tests/test_pr3_inventory.py`, and report models — rename `GUILD_SCOPE_GAPS` references and distinguish historical inventory from runtime closure.

### Approaches

1. **Direct staging Postgres verifier (recommended for catalog evidence)** — Add an opt-in test/diagnostic adapter using a staging-only database URL (for example `SUPABASE_DB_URL`) and a read-only SQL transaction against `pg_catalog`, `pg_policies`, `pg_publication_tables`, `pg_stat_user_indexes`, and `supabase_migrations.schema_migrations`.
   - Pros: system catalogs are available; exact migration identity and 018 preflight can be measured; no public API exposure; aligns with PostgreSQL catalog semantics.
   - Cons: requires a separate secret and driver; must prevent the bot runtime from receiving database-owner credentials; transaction/rollback harness needs careful isolation.
   - Effort: Medium–High.

2. **Restricted staging catalog RPC** — Create a narrowly scoped, read-only function that returns normalized catalog evidence and grant execution only to the staging verifier role; call it through Supabase RPC.
   - Pros: reuses the existing Supabase client; no direct database URL in the test process; returns a stable typed payload.
   - Cons: a security-definer function in an API-exposed schema is sensitive; a private-schema function is not reachable through ordinary PostgREST RPC; the function itself becomes migration/security surface. Supabase guidance says not to expose security-definer functions in public API schemas.
   - Effort: Medium–High, with a security review required.

3. **PostgREST plus mocked fallback only** — Keep the four current catalog SELECTs and treat `PGRST205` as unresolved while all acceptance tests use fakes.
   - Pros: smallest diff and no new credentials/dependencies.
   - Cons: cannot satisfy S4's real catalog or 018-live blockers; migration identity remains weak; a fake live marker can still report a misleading pass.
   - Effort: Low, but unacceptable as the S4 completion path. It should remain only as the credential-independent default-suite fallback.

### Recommendation

Use PyJWT `PyJWKClient` for RS256 and a **direct, read-only staging Postgres verifier** for catalog evidence unless the product owner explicitly chooses the narrower RPC surface. Keep the standard suite fully credential-independent and make real staging tests skip with a clear reason when credentials are absent; never mark the S4 parity gate resolved from the mock path.

Use three S4 workstreams with four physical PRs at most under the cached `auto-chain`/`stacked-to-main`/800-line guard:

1. **S4.1 — Guardrails and bounded polish (target 550–750 authored lines).** Add direct PyJWT crypto dependency, RS256/JWKS verification and rotation tests, `GUILD_SCOPE_GAP_HISTORY` rename plus a 12/12 runtime-closure assertion, and only the focused sentinel/repair/panel error-branch tests needed to raise changed files to at least 80%. If measured additions plus deletions approach 800, move polish to the optional S4.3 follow-up rather than accepting a size exception.
2. **S4.2a — Real catalog and credential-gated live verifier (target 350–650 lines).** Add the direct DB adapter or approved RPC contract, exact migration-name reconciliation, real catalog assertions (`9/7/0`, six existing FKs, four publication tables, 19 exact remote migrations), and one genuine credential-gated live test. The default fake/binder tests remain and must still pass.
3. **S4.2b — Migration 018 staging execution (target 250–500 lines).** First capture read-only preflight evidence, then apply 018 through the tracked migration mechanism during the approved window, verify constraints/types/index policy/data retention, and record rollback/post-apply evidence. Do not use `execute_sql` or the SQL editor as an untracked substitute for migration execution. The repository needs a Supabase CLI migration configuration or a documented wrapper because it currently stores SQL under `migrations/`, not `supabase/migrations/`.

**Optional S4.3 — polish-only follow-up (target 150–300 lines).** Use this only if S4.1's JWKS/ledger work leaves the repair, panel, or Sentinel changed-file coverage below 80%; it must not become a catch-all for unrelated coverage debt. Each physical PR remains below 800 lines, and tests/docs stay with the behavior they verify.

The acceptance receipt should report both `uv run pytest -q` (baseline 1968 passed, 5 skipped, or higher after S4 tests) and a separate real live command with at least one network-backed pass. The existing `1 passed, 1 skipped` live selection is not sufficient because it currently exercises fakes.

#### Evidence sources

- CodeGraph: `DatabaseBase.health_probe`, `DatabaseBase.health_check`, `validate_supabase_key`, `fetch_live_metadata`, `SchemaInventory.bind_live_evidence`, `TicketRepairService`, `deploy_ticket_panel` and their callers/tests.
- Context7/official Supabase: pg-meta exposes read-only catalog inspection; migration tracking is `supabase_migrations.schema_migrations`; remote deployment uses tracked migrations and `supabase db push`.
- Context7/official PostgreSQL: `pg_constraint` and `pg_policy` catalog semantics; `ALTER TABLE ... VALIDATE CONSTRAINT` scans existing data and takes a `SHARE UPDATE EXCLUSIVE` lock.
- Context7/official PyJWT: `PyJWKClient.get_signing_key_from_jwt()` plus explicit algorithm allowlists.
- Official Supabase signing-key documentation: `https://project-id.supabase.co/auth/v1/.well-known/jwks.json`; rotation can trust current and previously used keys, and discovery/client caches can delay key visibility.
- Web search was used to locate the official Supabase and PyJWT documentation; authoritative claims above are based on those primary sources rather than search snippets.

#### Product questions for proposal

1. What staging credential window is available for the real verifier and 018 execution, and will it include a short-lived `sb_secret_`, a direct `SUPABASE_DB_URL`, or an approved restricted RPC role?
2. Is the catalog source approved as direct read-only Postgres, a staging-only RPC, or both—and who owns the function/credential rotation if RPC is selected?
3. Is Supabase's project JWKS endpoint the authoritative rotation source, with which issuer/audience values and cache/forced-refresh policy? Should S4 support only RS256 or also ES256 signing keys later?
4. For index decisions, is `EXPLAIN (ANALYZE, BUFFERS)` on representative staging workload required, or is cumulative `pg_stat_user_indexes` plus the already-approved duplicate-index policy sufficient? No index should be dropped solely because its current scan count is zero.
5. Are real DB/RPC catalog evidence and real 018 staging execution hard acceptance gates, with mocked fallback allowed only for the default no-credential suite? Confirm the exact full-suite/live counts and whether the 80% changed-file target is blocking or informational.

### Risks

- No application-process Supabase credentials are currently available; MCP SQL proves the project state but not the bot's credential path.
- PostgREST cannot be treated as a system-catalog transport; the current four-table path will continue to produce `PGRST205` against the live API and must fail closed.
- Migration 018 changes types, constraints, indexes, and one audit row; applying it without an approved staging window, tracked CLI configuration, and rollback evidence is unsafe.
- A 19-versus-19 migration count can conceal different migration identities; exact version/name comparison is required before calling parity resolved.
- JWKS discovery and client caches can lag rotations or revocations; unknown `kid` must trigger bounded refresh, not algorithm fallback or payload-only acceptance.
- `GUILD_SCOPE_GAPS` is consumed by existing tests and reports; a rename must not accidentally reintroduce a runtime blocker or erase historical audit evidence.
- Repair/panel error branches are broad enough to push S4 over 800 authored lines if all missing coverage is pursued at once; keep optional polish explicitly bounded.

### Ready for Proposal

**Yes, conditionally.** The code, quality gates, live catalog facts, migration structure, and external documentation are sufficient for a proposal. The proposal must first record the five product answers—especially the staging credential/RPC choice, JWKS rotation policy, real-versus-mocked acceptance gate, and whether S4.2 is approved as two stacked physical PRs. No live 018 application should begin from exploration.
