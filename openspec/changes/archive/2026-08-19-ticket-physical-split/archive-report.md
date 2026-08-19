# Archive Report: ticket-physical-split S3

**Change**: `ticket-physical-split` S3
**Archived to**: `openspec/changes/archive/2026-08-19-ticket-physical-split/`
**Archived at**: 2026-08-19
**Branch**: `ticket-physical-split-s3d4b-views` @ `1310167`
**Base**: `ebe3c7f` (v0.4.0)
**Verdict at close**: `PASS_WITH_WARNINGS` — archivable (0 critical, 13/13 req, 41/41 scenarios, S4 warnings documented)

## Goal

Physical decomposition behind stable facades: `ticket_service.py` 2108 → `TicketService` + `TicketLifecycleService` + `TicketQueryService` + `TicketRepairService`; `tickets.py` 1079 → `TicketsCog` + 4 flow modules; `views/tickets.py` 1011 → facade + 3 view seams. Ordered DDL 018 (preflight → cast → FKs → validate → drop duplicate only), guild-scope close, `sb_secret_` 2-table probe, and live-schema guardrails. Refs `Diagramas/DiagramaSecuencia.mmd`, `DiagramaEntidad-Relacion.mmd`.

## Accomplished

**7 stacked PRs** (S3.1 7e35a08, S3.2 961123b, S3.3A-query 1cf60ba, S3.3A2 4883f18, S3.3B 6f32b78, S3.4A b9d531d, S3.4B adc74be) + remediation 4cc25bd + final fix 1310167. Tests 1968 passed / 5 skipped (87.8%), `mypy bot` 0, `mypy tests` 0, `ruff check` 0, `ruff format` 0.

- **S3.1 Guardrails** — 24 `is_mod` decorators (16 tickets + 8 sentinel, unclaim claimer-or-mod; PR #64), 3 deferred callers 568/685/722 + 14 DB refs guild-scoped, 11 scripts Ruff findings closed.
- **S3.2 Parity/DDL** — Migration `018_ticket_integrity_fks.sql` 8-step ordered DDL: TEXT→UUID `USING` cast, `LOCK_TIMEOUT`, child indexes, FKs `RESTRICT/SET NULL/CASCADE/SET NULL`, validate, drop `idx_ticket_guild_number` only (keep `idx_ticket_channel`); 17↔19 reconciliation (+005 stub, 19 local). PR #65.
- **S3.3A Query + S3.3A2 Lifecycle** — `TicketQueryService` single cache owner + `TicketLifecycleService` single audit owner, facade delegates once, 20 facade tests. PRs #66, #67.
- **S3.3B Repair** — `TicketRepairService` single `evaluate_repair_eligibility` seam for event/sweep/manual/reference/uuid, race/idempotency/quarantine, countdown kept on facade. PR #68.
- **S3.4A Cog** — 4 flows `ticket_admin/lifecycle/notes/integrity_flow.py`, `TicketsCog` 464 facade via composition, hybrid names stable, `async def setup(bot)`. PR #69.
- **S3.4B Views** — `ticket_panel.py`/`ticket_actions.py`/`ticket_category_select.py` behind `views/tickets.py` facade: 4 `custom_id`s (`ticket:open|claim|close|edit-category`), `timeout=None` persistent + 300s ephemeral 12/12 revalidation (`is_mod_check` + `status==closed`), `field_definitions` via `_CategorySelect`. PR #70. `Bot.setup_hook` registers via facade.

**Final 3-critical closure** (verify-report `1310167`): guild-scope threading on lifecycle/notes/views/repair; `sb_secret_` probe fail-closed clears `DatabaseBase._client` and `ServiceRoleValidationError`; legacy JWT requires `SUPABASE_JWT_SECRET` HS256 PyJWT verification (payload-only rejected). `GUILD_SCOPE_GAPS` static 12-name inventory retained; runtime 12/12 closed proven by `test_s3_final_strict_contracts.py` strict doubles (5/5).

**Live-marker note**: `pytest -m live --run-live --no-cov` 1 passed / 1 skipped / 0 failures (no real creds; masked DB/RPC/JWKS is S4); coverage 1-exit on live selection only.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| ticket-service | Added | Facade-preserving composition + single repair seam |
| ticket-commands | Added | Flow-aligned cog split + guild boundary + S3 guardrail gate |
| ticket-views | Modified + Added | Panel facade wording + stable lifecycle contracts (4 IDs / timeouts / revalidation) |
| database-layer | Added | Read-only preflight, ordered DDL, guild-scoped entries |
| live-schema-verifier | Added | `sb_secret_` 2-table probe + catalog parity (9/7/0, 6 FKs, 4 pub, 17↔19) |
| permission-model | Added (supersedes) | 24 decorators (S3 truth; co-exists with prior S2.2 23 count in same file) |

All 6 deltas appended with `<!-- BEGIN DELTA: ticket-physical-split S3 -->` markers. Main specs updated: `openspec/specs/*/spec.md`.

## Archive Contents

- `proposal.md` ✅ — S3 intent/scope/approach (6 PRs, Q1–Q5 success)
- `specs/` ✅ — 6 deltas (ticket-service, ticket-commands, ticket-views, database-layer, live-schema-verifier, permission-model)
- `design.md` ✅ — facade/composition architecture
- `exploration.md` ✅ — discovery
- `tasks.md` ✅ — 21/21 complete (0 unchecked)
- `apply-progress.md` ✅ — 7 slices + remediation TDD evidence, blocker closure map
- `verify-report.md` ✅ — `1310167` PASS_WITH_WARNINGS (1968/5, 13/13, 41/41, 0 critical)

Active `openspec/changes/ticket-physical-split/` removed; `diff -r` snapshot vs archive empty (mechanical `git mv`).

## Source of Truth Updated

`openspec/specs/ticket-service/spec.md`, `ticket-commands/spec.md`, `ticket-views/spec.md`, `database-layer/spec.md`, `live-schema-verifier/spec.md`, `permission-model/spec.md` now reflect S3 behavior.

## Final-State Authority

Highest-ranked source: `verify-report.md` at `1310167` (covers 3-critical closure, 1968 passed, 13/13, 41/41, warnings). Earlier `apply-progress.md` snapshot claims are history only. `verify PASS_WITH_WARNINGS` is correctly archivable: 3 critical resolved, 4 S4 warnings are staging catalog/DDL deferrals with fail-closed behavior, not S3 blockers. No `reviewGate` was present for this candidate (kill switch off / no review started); `verify-report` is terminal receipt.

## Next Steps — S4 (warnings, not blockers)

- **JWKS RS256** — full asymmetric verification (S3 has HS256 allowlist + opaque `sb_secret_`; legacy JWT retained).
- **DB/RPC catalog parity with real creds** — FK/RLS `9/7/0`, publication 4, migration ledger; PGRST205 → unresolved proven, real staging credential path deferred.
- **018 live staging execution** — `DO $preflight$` → cast → FKs → validate → drop against real PG; currently branch + FakeSupabase.
- Triangulation/safety-net columns in `apply-progress.md` remain process-evidence warnings.

## Relevant Files

- `bot/services/ticket_service.py` — stable facade
- `bot/services/ticket_query_service.py`, `ticket_lifecycle_service.py`, `ticket_repair_service.py` — sub-services (single owners)
- `bot/cogs/tickets.py` (464) + `bot/cogs/ticket_{admin,lifecycle,notes,integrity}_flow.py` — cog split, `guild_id=gid` 568/685/722
- `bot/views/tickets.py` facade + `bot/views/ticket_{panel,actions,category_select}.py` — 4 IDs, `timeout=None`/`300`, revalidation
- `bot/core/db/base.py`, `bot/config.py`, `bot/services/schema_inventory.py` — `sb_secret_` probe + `SUPABASE_JWT_SECRET` + `fetch_live_metadata` PGRST205 fail-closed
- `migrations/018_ticket_integrity_fks.sql` — 8-step DDL
- `tests/test_s3d1_guardrails.py`, `test_s3d2_parity_ddl.py`, `test_ticket_*_facade.py`, `test_s3_final_strict_contracts.py` — 619 change tests collected

## SDD Cycle Complete

Planned, implemented (TDD 7 slices), verified, and archived. Ready for next change. Do not modify `openspec/changes/archive/2026-08-19-ticket-physical-split/` — audit trail.
