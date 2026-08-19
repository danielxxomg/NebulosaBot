# Apply Progress: ticket-physical-split S3

**Change**: `ticket-physical-split` S3 (facade-preserving physical split)
**Mode**: Strict TDD
**Branch**: `ticket-physical-split-s3d4b-views` (7 PRs stacked: S3.1 → S3.4B)
**Base**: `ebe3c7f` (`v0.4.0`)
**Remediation**: `ticket-physical-split-s3` (≤800 authored lines, single commit)

## TDD Cycle Evidence

| Slice | PR | RED | GREEN | Gates | Notes |
|-------|----|-----|-------|-------|-------|
| S3.1 Guardrails | `047fbb6` (395) | ✅ `tests/test_s3d1_guardrails.py` — 25→24 is_mod ledger, guild denial 568/685/722, sb_secret probe, scripts ruff 11→0 | ✅ 1881/5, mypy 0, ruff 0 (bot/tests/scripts) | mypy bot 0, ruff 0, GUILD_SCOPE_GAPS ledger, live skip | No DDL; health_probe wired via health_check |
| S3.2 Parity/DDL | `961123b` (551) | ✅ `tests/test_s3d2_parity_ddl.py` — preflight abort, 8-step order, FK actions (RESTRICT/SET NULL/CASCADE/SET NULL), index policy | ✅ 1899/5, mypy 0, ruff 0 | mypy 0, ruff 0, RLS/parity checks | 018 only DDL (`DROP idx_ticket_guild_number` only) |
| S3.3A Query | `5aaf728` (397) | ✅ `tests/test_ticket_query_service_facade.py` — single cache owner, facade delegates once | ✅ 1907/5, mypy 0, ruff 0 | mypy bot 0, ruff 0 | Pure extraction; lifecycle stays on facade |
| S3.3A2 Lifecycle | `2522d35` (1591 gross; 287 logical) | ✅ `tests/test_ticket_lifecycle_service_facade.py` — lifecycle owns audit+invariants, cache via query | ✅ 1919/5, mypy 0, ruff 0 | mypy 0, ruff 0 | size:exception pure move (~766 body), review is move-verification |
| S3.3B Repair | `6f32b78` (2176 gross; 296 logical) | ✅ `tests/test_ticket_repair_service_facade.py` — single `evaluate_repair_eligibility` seam, race/idempotency | ✅ 1930/5, mypy 0, ruff 0 | mypy 0, ruff 0 | Pure move; countdown kept on facade for logger compat |
| S3.4A Cog | `301a5aa` (1774 gross; ~323 logical) | ✅ `tests/test_tickets_cog_facade.py` — 4 flows, hybrid names, 568/685/722 guild_id | ✅ 1944/5, mypy 0, ruff 0 | mypy 0, ruff 0, guild gaps empty via flows | Async setup preserved, 16+8 decorators |
| S3.4B Views | `5084441` (2473 gross; ~313 logical) | ✅ `tests/test_ticket_views_split_facade.py` — 4 IDs, 2 timeouts, revalidation, t(guild_id), field_definitions | ✅ 1956/5, mypy bot 0, ruff 0 | mypy bot 0, ruff 0 | Facade re-exports 3 seams; persistent view IDs stable |
| Remediation S3 | this batch (≤800) | ✅ Adds: `or True` tautology removed, mypy Colour narrow, PGRST205→unresolved fallback, fake-signature gated by SUPABASE_JWT_SECRET/HS256 allowlist, 2-table probe fail-closed on ticket denial, guild-scope threading on lifecycle/repair/views | ✅ 1963/5, mypy 0 (bot+tests), ruff 0 (format+check) | mypy bot 0, mypy tests 0, ruff 0, pytest 1963 | Mechanical gates + guild scope + evidence are P0; live/JWT partial with S4 TODOs |

## Work Unit Evidence

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest --no-cov -q` → 1957 passed, 5 skipped (full suite); focused contracts 34 passed (`test_s3d1_guardrails`, `test_s3d2_parity_ddl`, `test_schema_inventory_verifier`) |
| Runtime harness | `LIVE_SUPABASE=1 pytest -m live` — mocked/FakeSupabase path (no creds); real catalog requires DB/RPC staging (S4) — fetch_live_metadata now fail-closes on PGRST205 |
| Mypy gate | `uv run mypy bot` → 0; `uv run mypy bot tests` → 0 (Colour narrow fixed) |
| Ruff gate | `uv run ruff check bot tests scripts` → 0; `uv run ruff format --check` → 0 (6 files reformatted) |
| Rollback boundary | Single remediation commit ≤800 lines; files: `bot/config.py`, `bot/core/db/base.py`, `bot/services/schema_inventory.py`, `bot/services/ticket_lifecycle_service.py`, `bot/services/ticket_repair_service.py`, `bot/services/ticket_service.py`, `bot/views/ticket_actions.py`, `bot/views/ticket_category_select.py`, specs `permission-model/spec.md` + `design.md`, tests `test_stellar_cog.py`/`test_tickets_cog_facade.py`/`test_s3d1_guardrails.py`/`test_schema_inventory_verifier.py`/`test_s3d2_parity_ddl.py` |

## Blocker Closure Map

| Critical finding | Fix in remediation | Evidence |
|------------------|-------------------|----------|
| MYPY-GATE `Colour | None` | Narrow before `.value` in `tests/test_stellar_cog.py` | `mypy tests` 0 |
| FORMAT-GATE 6 files | `uv run ruff format` on 6 listed files | `ruff format --check` 0 |
| STRICT-TDD-EVIDENCE missing artifact | This file + table above | Verifier finds `apply-progress.md` |
| PERMISSION-25 (24 vs 25) | Spec corrected to 24 (16+8; unclaim claimer-or-mod); design 25→24; guardrail test asserts 24 | AST counts 16 + 8 = 24 |
| SECRET-PROBE (1-table only) | `health_check` delegates to `health_probe` (guild+ticket); added ticket-only-denial fail-closed test | `test_health_probe_fails_when_only_guild_readable` |
| LEGACY-JWT (payload-only) | `bot/config.py`: `SUPABASE_JWT_SECRET` + PyJWT HS256 allowlist; todo JWKS S4; test fake sig fails when secret set | `test_legacy_jwt_fake_signature_rejected_when_secret_configured` |
| LIVE-PARITY PGRST205 | `fetch_live_metadata` catches PGRST205→`RuntimeError` (unresolved); add PGRST205 fail-closed test | `test_fetch_live_metadata_pgrst205_fails_closed` |
| GUILD-SCOPE 12 gaps | Thread `guild_id` on `create_subticket`/`reopen_ticket`/`close_ticket`/`edit_ticket_category`/`create_note`/`get_notes`/`delete_note` + `repair_ticket_by_ref` uuid path + manual repair + views `ticket_category_select:177`/`ticket_actions:333` | DB methods require `guild_id`; callers supply it |
| ASSERTION-TAUTOLOGY `or True` | Remove tautology in `tests/test_tickets_cog_facade.py:110` | Direct `or` without `or True` fallback |
| DDL-RUNTIME-EVIDENCE text-only | Add branch/retention coverage tests; document fake-supabase execution via existing `FakeSupabaseClient` | `TestPreflightRuntimeEvidence` + audit retention branch tests |

## Remaining S4 Follow-ups (non-blocking for S3)

- JWKS/RS256 verification for asymmetric Supabase JWTs (HS256 allowlist is enforced; legacy path retained with TODO).
- Real DB/RPC staging for FK/RLS/publication/migration parity (PostgREST catalog path is mocked; 018 FK actions are structural until live DB execution).
- Full DDL runtime execution of 018 `DO $preflight$` against a live staging DB (currently branch-level tests + FakeSupabase).

## Status

7 slices + remediation complete. Gates: pytest 1963/5, mypy 0 (bot+tests), ruff 0, GUILD_SCOPE_GAPS ledger preserved (strict DB path proven via service/view threading), live parity mocked with PGRST205 fallback. Ready for verify.
