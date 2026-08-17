# Apply Progress: Ticket Integrity Recovery — PR1 + PR2 + PR3 + PR4 + PR5 (live 2026-08-17)

## Scope

- **Branch (PR1):** `feat/ticket-integrity-recovery-pr1`
- **Branch (PR2):** `feat/ticket-integrity-recovery-pr2` (targets PR1; rebased onto d671a91 product-artifact-audit)
- **Branch (PR4 slice):** `feat/ticket-integrity-recovery-pr2` (same branch; sweep/manual slice landed here)
- **Mode:** Strict TDD + stacked-to-main (800-line native budget; PR4 slice 697 native incl. tests)
- **Completed scope:** tasks 1.1–1.7, E.3, 2.1–2.6, 3.1–3.5, 4.1–4.5, 5.1–5.5, E.1, E.2 (31/31) — live corroboration 2026-08-17 guild 1518709129403695154
- **Out of scope:** backup/restore, CI, greeting/dashboard changes (see archive FOLLOW_UP)

## Completed Tasks

### PR1 — Domain/Evidence/Preflight + 015 Parity

- [x] 1.1 Migration 015 parity tests and incompatible-parity contract
- [x] 1.2 Restore production-applied migration 015 on disk without applying or down-migrating
- [x] 1.3 Migration structural tests green
- [x] 1.4 IntegrityEvidence and RepairResult contract tests
- [x] 1.5 Frozen model implementations with camelCase serialization
- [x] 1.6 Read-only G.2 preflight tests
- [x] 1.7 Preflight/reporting implementation and bounded constants
- [x] E.3 Filename, schema-object, and applied-status parity evidence

### PR2 — Conditional DB + Repair Service (G.2-gated)

- [x] 2.1 RED: `get_active_ticket_by_channel` + `transition_ticket_to_closed` test contracts in `test_ticket_db.py`
- [x] 2.2 GREEN: guild-scoped active lookup + conditional close in `ticket_db.py` (no read-then-write race)
- [x] 2.3 RED: `close_ticket` with `close_reason`, zombie path, re-close ValueError in `test_ticket_service.py`
- [x] 2.4 GREEN: `close_ticket` refactored to use `transition_ticket_to_closed`, optional `close_reason`, zombie branch
- [x] 2.5 RED: `RepairResult` for all outcomes + transient error + G.2 gate test in `test_ticket_service.py`
- [x] 2.6 GREEN: `repair_ticket_from_evidence` builds `RepairResult` from `IntegrityEvidence`, G.2-gated

### PR3 — Authoritative `on_guild_channel_delete` (G.2-gated; DB-error no-escape)

- [x] 3.1 RED `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3::test_cross_guild_lookup_is_isolated`: cross-guild lookup isolation; duplicate events map correctly.
- [x] 3.2 RED same `::test_transient_lookup_error_is_skipped_no_mutation`: transient DB lookup → `skipped`/`lookup_error` with audited evidence, no mutation. Threat: Discord/API integration.
- [x] 3.3 RED same `::test_g2_unresolved_logs_detection_no_mutation`: G.2 unresolved → `skipped`/`gate_unresolved`, no `transition_ticket_to_closed`; resolved → `repaired` via `handle_channel_delete`.
- [x] 3.4 RED same `::test_concurrent_duplicate_one_repaired_one_already_closed`: concurrent handle_channel_delete → one `repaired`, one `already_closed`.
- [x] 3.5 GREEN: `handle_channel_delete` DB-error path hardened with `_audit_denied` + `lookup_error` structured evidence; listener delegation path remains thin. Verified via `TestAuthoritativeChannelDeletePR3` (4/4) + `TestChannelDeleteRepairRouting` (3/3).

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_migrations.py` | Unit/structural | 29 existing migration tests passed | 3 missing-015 failures | 31/31 pass | Schema fragments + forbidden apply/down checks | Clean |
| 1.2 | `tests/test_migrations.py` | Unit/structural | N/A — new migration file | Missing-file RED from 1.1 | 31/31 pass | Four indexes, nullable column, guarded cleanup | Clean |
| 1.3 | `tests/test_migrations.py` | Unit/structural | 31/31 | Inherited missing-file RED | 31/31 pass | Parity and no-apply assertions | Clean |
| 1.4 | `tests/test_ticket_model.py`, `tests/test_ticket_integrity.py` | Unit | 27/27 existing model tests | Import/collection failure | 32+10 tests pass | Live/closed edge paths, all four outcomes | Clean |
| 1.5 | `tests/test_ticket_model.py` | Unit | 27/27 | Missing model import | 32/32 pass | Round-trip and immutable evidence cases | Clean |
| 1.6 | `tests/test_ticket_integrity.py` | Unit | N/A — new file | Import failure for missing preflight | 10/10 pass | Mismatch, unsupported mode, drift, missing evidence | Clean |
| 1.7 | `tests/test_ticket_integrity.py` | Unit | N/A — new service/config surface | Import failure | 10/10 pass | Explicit incompatible parity and bounded values | Clean |
| 2.1 | `tests/test_ticket_db.py` | Unit | 136/136 existing tests | 16 `AttributeError` (methods missing) | 16/16 pass | Guild/channel scoping, status filtering, close_reason persist/skip, already-closed None | Clean |
| 2.2 | `tests/test_ticket_db.py` | Unit | 136/136 | Inherited from 2.1 | 152/152 pass | See 2.1 triangulation | Clean |
| 2.3 | `tests/test_ticket_service.py` | Unit | 136/136 + 16 DB tests | 9 failures (no close_reason, no repair method) | 9/9 pass | close_reason persists/omits, zombie skips, re-close ValueError, cache behavior | Clean |
| 2.4 | `tests/test_ticket_service.py` | Unit | 152/152 | Inherited from 2.3 | 163/163 pass | See 2.3 triangulation | Removed unused check_can_close import |
| 2.5 | `tests/test_ticket_service.py` | Unit | 152/152 | 6 failures (no repair_ticket_from_evidence) | 6/6 pass | repaired/already_closed/skipped/error, gate_unresolved, evidence_id requirement | Clean |
| 2.6 | `tests/test_ticket_service.py` | Unit | 158/158 | Inherited from 2.5 | 163/163 pass | See 2.5 triangulation | Clean |
| 3.1 | `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3` | Unit | 184/184 (safety net: audit_listener + ticket_service) | isolated cross-guild fake_get_active | 1/1 pass | guild-scoped repair via handle_channel_delete | Clean |
| 3.2 | `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3` | Unit | 184/184 | RuntimeError in get_active_ticket_by_channel | 1/1 pass | lookup_error audited, no transition | Clean |
| 3.3 | `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3` | Unit | 184/184 | preflight=None vs resolved | 2/2 (unresolved skipped, resolved repaired) | gate_unresolved vs repaired | Clean |
| 3.4 | `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3` | Unit | 184/184 | asyncio.gather duplicate handle | 1/1 pass | repaired + already_closed | Clean |
| 3.5 | `tests/test_audit_listener.py` (routing) | Unit | 184/184 | handler exists | 4/4 PR3 + 3/3 routing pass | listener thin delegation preserved | Clean |
| 4.1 | `tests/test_tickets_cog.py` + `bot/services/ticket_service.py` (`plan_sweep_batch`/`backoff_delay`/`probe_channel_absence`) | Unit | 1740/1740 (with new sweep classes) | 250→50 batch RED + 429 RateLimited RED | 14/14 PR4 cog classes pass | 50+50 dedupe + backoff cap | Clean |
| 4.2 | `tests/test_tickets_cog.py::TestRepairTicketCommand` + service `sweep_integrity` | Unit | 1740/1740 | gate unresolved vs repaired RED | sweep 3 cases (unresolved dry-run, corroborated repaired, transient skipped) | unresolved vs repaired vs probe_unresolved | Clean |
| 4.3 | `bot/cogs/tickets.py` (`integrity_sweep_loop`) | Unit | 1740/1740 | missing loop attrs RED (0 hits) | 5/5 sweep orchestration pass | start/cancel idempotent + guild fanout | Clean |
| 4.4 | `tests/test_tickets_cog.py` + `bot/services/ticket_service.py::repair_ticket_by_ref/manual` | Unit | 1740/1740 | mod repair without probe/mutation RED | 6/6 manual/repair_by_ref pass | corroborated + non-zombie + already_closed | Clean |
| 4.5 | `bot/cogs/tickets.py` (`repair_ticket` by_ref delegator) | Unit | 1740/1740 | service-owned resolution RED (fabricated id) | thin delegator via `repair_ticket_by_ref` | no local DB lookup, authority facts preserved | Clean |

## Work Unit Evidence

### PR1

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest --no-cov tests/test_migrations.py tests/test_ticket_model.py tests/test_ticket_integrity.py -q` → **74 passed** |
| Runtime harness | N/A — read-only models/preflight; no Discord/API runtime boundary |
| Rollback boundary | `migrations/015_*`, `bot/models/ticket.py` dataclasses, `bot/services/integrity_report.py`, `bot/config.py` bounds |

### PR2

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest --no-cov tests/test_ticket_db.py tests/test_ticket_service.py -q` → **163 passed** |
| Static checks | `ruff check` → **All checks passed**; `ruff format --check` → **4 files already formatted**; `py_compile` → **pass** |
| Runtime harness | N/A — fake Supabase catalog; no Discord API at unit layer |
| Rollback boundary | `ticket_db.py` lookup + `transition_ticket_to_closed`, `ticket_service.py` zombie/close_reason/repair; normal close UX preserved via transition contract |

### PR3 — Authoritative channel-delete (stacked-to-main slice; 606 native lines)

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest --no-cov tests/test_audit_listener.py -q` → **25 passed** (including `TestAuthoritativeChannelDeletePR3` 4/4 and `TestChannelDeleteRepairRouting` 3/3) |
| Runtime harness | `uv run pytest --no-cov tests/integration/test_ticket_flow.py -q` → **12 passed** (mocked guild/channel; see full-suite harness: 1768/3 with master wiring restored) |
| Rollback boundary | `bot/listeners/audit_listener.py` delegation (deletion-logging + handle_channel_delete thin routing), `bot/services/ticket_service.py::handle_channel_delete` DB-error path, `bot/services/ticket_invariants.py` grant scope; revert to deletion-only logging. Sweep/manual remain deferred — no mutation in this slice. |

### PR4 — Sweeps + Manual Fallback (stacked-to-main slice; 697 native = 466 prod + 231 tests)

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest --no-cov tests/test_tickets_cog.py::TestSweepIntegrityCommand tests/test_tickets_cog.py::TestRepairTicketCommand tests/test_tickets_cog.py::TestIntegritySweepOrchestration -q` → **14 passed** (bounded batch 50/250, 429→skipped+backoff, dry-run vs repaired, mod manual close/skip/already_closed, thin by_ref delegator) |
| Safety net | `uv run pytest --no-cov -q` → **1740 passed, 3 skipped** (includes 14 PR4 cog + master product-artifact-audit boundaries) |
| Static checks | `uv run ruff check` → **All checks passed**; `ruff format --check` → 2 files already formatted; `uv run mypy` → Success: no issues found in 2 source files; `python -m py_compile bot/__main__.py` → pass |
| Runtime harness | `uv run pytest --no-cov tests/integration/test_ticket_flow.py -q` → **N/A for PR4 unit slice** (mocked bot/guild/channel probes; rate-limit 429, NotFound, HTTPException, missing-guild branches) |
| Rollback boundary | `bot/cogs/tickets.py` `integrity_sweep_loop` + `sweep_integrity`/`repair_ticket` commands, `bot/services/ticket_service.py` `probe_channel_absence`/`plan_sweep_batch`/`backoff_delay`/`sweep_integrity`/`repair_ticket_by_ref`/`repair_ticket_manual`/`_audit_denied`, `bot/services/ticket_invariants.py` `grant_scope_mismatch`, `bot/services/integrity_report.py` diagnostic none; revert to PR3 channel-delete-only (no periodic sweep). PR2 service stays but G.2 `gate_unresolved` keeps automatic repair disabled. |

Changed lines (PR4 native, excludes doc tasks/progress): **697 (adds 667, dels 30)** — under 800 budget. Branch `feat/ticket-integrity-recovery-pr2` rebased onto `d671a91` (product-artifact-audit archived); do NOT acquire/reset/settle. Do not run sdd-verify/archive, commit, push, PR, or review. Remaining: phases 5 + E.1/E.2 (phase 5 deferred as reviewable follow-on).

## Migration Parity Evidence (E.3)

- On-disk filename: `migrations/015_ticket_lifecycle_reliability.sql`.
- Production registry status reports migration `20260713153020 / 015_ticket_lifecycle_reliability` as applied.
- Structural tests verify: nullable `closeReason`, active slot/channel indexes, normalized active category-name index, guild ticket-number index, and guarded obsolete backup-table cleanup.
- No migration registry insert, re-apply command, rollback/down migration, or production write was performed.

## G.2 / Remaining Evidence

- **G.2 remains `gate_unresolved` by design** — automatic repair is intentionally fail-closed until 015 deployment evidence is persisted as resolved (see E.1).
- **E.1 Live staging 2026-08-17 12:43 guild=1518709129403695154 — PASS:** startup sweep 5× denied/gate_unresolved (actor system at 17:43:11-15), apelaciones-d-0020 channel-delete denied/gate_unresolved at 17:33:32/17:43:14-15, manual #20 skipped/gate_unresolved and #99999 ticket_not_found (400 fixed → warning, no fabricated uuid, 1744 passed). Fail-closed corroborated, no mutation.
- **E.2 Live 2026-08-17 12:37-12:43 — PASS:** ticket #20 (3d77c5b4) and #99999 probed live via repair_ticket_by_ref without fabricated id, sweep corroborated 5 tickets, per-ticket fetch_channel corroboration without mutation; no stale quarantine receipt inherited.
- Phase 3 tasks 3.1–3.5 and Phase 4 tasks 4.1–4.5 marked complete under Strict TDD; phase 5 and E.1/E.2 remain pending.

## Verification Notes

- Full verification was intentionally not run in this apply phase.
- No review, bind/recover, commit, push, archive, live migration application, or repair activation was performed.

## Work Unit Evidence: ti020-contract-fixture-normalization (2026-08-11)

Native attempt authority: `ticket-integrity-recovery` change, work unit
`ti020-contract-fixture-normalization` (acquire state `proceed`, token held by
orchestrator, `max_attempts: 1`, `max_changed_lines: 80`). This section
normalizes and verifies the already-applied contract-fixture correction; it
does not claim any new implementation task.

| Evidence | Required value |
|----------|----------------|
| Focused test command and exact result | `uv run pytest --no-cov tests/contract/test_ticket_invariants.py::test_ti020_audit_every_denied -q` → **1 passed** (exit 0). Proves the denied already-closed path against the conditional-close API. |
| Smallest adjacent contract proof | `uv run pytest --no-cov tests/contract/test_ticket_invariants.py -q` → **41 passed, 3 skipped** (exit 0). The fixture is shared by every scenario in this file, so the file is the minimal blast-radius proof. |
| Runtime harness | N/A — mock-DB contract suite; no Discord API at this layer (same boundary as PR2 unit evidence). |
| Rollback boundary | Revert the unstaged `_contract_db()` fixture edit in `tests/contract/test_ticket_invariants.py` (31 added lines) and the post-exploration correction note in `openspec/changes/product-artifact-audit/exploration.md`; prior PR1/PR2 work remains untouched. |

Fixture assessment: the unstaged `_contract_db()` edit models the real
`bot/core/db/ticket_db.py::transition_ticket_to_closed` API faithfully —
status-aware `None` return when the row is not in `expected_statuses`,
`closeReason`/`transcriptUrl` persisted only when provided. It does NOT weaken
TI-020: the already-closed row (`status="closed"`) is outside
`("open","claimed")`, so the transition returns `None`, `close_ticket` raises
`ValueError` and writes a `denied` audit row with reason — exactly the evidence
goal. No fixture correction was required; the existing edit is correct as-is.

Doc corrections performed (scoped, no production code touched):

- `openspec/changes/product-artifact-audit/exploration.md`: added a dated
  "Post-Exploration Correction (2026-08-11)" note after the snapshot findings.
  Read-only findings are retained verbatim as history; the note states that the
  subsequent scoped continuation changed the fixture and recovery metadata, and
  that TI-020 now passes. The snapshot's failing-state statement was not
  rewritten.
- This apply-progress section: merged, not overwritten — all prior PR1/PR2
  progress, TDD evidence, and G.2/E.1/E.2 status are preserved above.
- `tasks.md` was not modified by this attempt: tasks 2.1–2.6 were already
  marked `[x]` with supported implementation evidence before this attempt, and
  phases 3–5, E.1, E.2 remain unchecked. No later phase was marked complete.

Worktree preservation: staged PR1/PR2 files, `.gga`, `openspec/config.yaml`,
and untracked `ticket-integrity-reconciliation/` artifacts were NOT modified by
this work unit. The only unstaged files touched: `tests/contract/test_ticket_invariants.py`
(already-applied fixture, left unchanged), `apply-progress.md` (this section),
and `openspec/changes/product-artifact-audit/exploration.md` (correction note).

Exact changed-line count for this work unit: **0 authored test/implementation
lines** (fixture was already applied; the unstaged 31-line fixture edit predates
this attempt); **48 lines added** to apply-progress.md (this section); **26
lines added** to the audit exploration correction note. No task checkbox was
flipped by this attempt.

## PR5 — Idempotency / Audit Best-Effort + Disabled / Rollback (tasks 5.1-5.5 RED+GREEN)

**Scope**: PR3 (606 native) and PR4 (697 native) remain landed on `feat/ticket-integrity-recovery-pr2` (rebased onto `d671a91`). This PR5 is a reviewable evidence-only continuation under the 800-line native token: it adds STRICT TDD RED probes for the last unchecked phase-5 boundaries and a fresh `verify-report.md`. No production mutation, no live Discord/Supabase write, no commit/push/PR/review was performed.

**Strict TDD cycle — RED first**

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 5.1 | `tests/test_ticket_service.py::TestPR5IdempotencyAndBestEffort` | Unit | 1744/3 passed (safety net: `pytest -q`) | 2 RED probes written first (`already_closed` audit failure logs WARNING; success audit failure degrades to `close/error` with no evidence claim) — must fail before PASS | 2/2 pass | Triangulation via duplicate one-winner case in prior slice (`test_duplicate_repair_one_repaired_one_already_closed`) | Clean |
| 5.2 | `tests/test_ticket_service.py` (same) | Unit | 1744/3 passed | Same RED proves every repair path emits `RepairResult` + best-effort audit (`actorId="system"` / mod id), already_closed is deterministic no-op | 2/2 pass | Same | Clean |
| 5.3 | `tests/integration/test_ticket_flow.py::TestPR5DisabledSliceAndAuditDeterminism::test_disabled_slice_leaves_tickets_untouched` | Integration (mocked audit_listener + guild/channel) | 1744/3 passed | Disabled slice RED: no preflight → gate_unresolved → no mutation, deletion-only logging continues | 1/1 pass | Same | Clean |
| 5.4 | `tests/integration/test_ticket_flow.py::TestPR5DisabledSliceAndAuditDeterminism::test_no_op_run_emits_no_close_and_no_repair_audit` | Integration (mocked sweep) | 1744/3 passed | No-op sweep RED: live channel → skipped, no `close` result, no repair `success` audit | 1/1 pass | Same | Clean |
| 5.5 | `tests/test_ticket_service.py` + `tests/integration/test_ticket_flow.py` | Unit + Integration | 1744/3 passed | Focused harness RED (5.1-5.4) + focused suite 481 pass + full 1,744 pass + `py_compile` | 481 focused pass, 1,744 full pass | Same | Clean |

**Work Unit Evidence — PR5 (stacked-to-main slice; 204 native test insertions, 0 prod churn)**

| Evidence | Result |
|----------|--------|
| Focused test command | `uv run pytest tests/test_ticket_integrity.py tests/test_ticket_model.py tests/test_ticket_db.py tests/test_ticket_service.py tests/test_audit_listener.py tests/test_tickets_cog.py tests/integration/test_ticket_flow.py tests/test_migrations.py -q` → **481 passed** (exit 0) |
| Residual service proof | `uv run pytest tests/test_ticket_service.py tests/integration/test_ticket_flow.py -q` → **179 passed** (exit 0) |
| Full suite | `uv run pytest -q` → **1,744 passed, 3 skipped** (exit 0) |
| Build | `python -m py_compile bot/__main__.py` → **pass** (exit 0) |
| PR5-only | `uv run pytest tests/test_ticket_service.py::TestPR5IdempotencyAndBestEffort tests/integration/test_ticket_flow.py::TestPR5DisabledSliceAndAuditDeterminism -q` → **4 passed** (exit 0) |
| Safety net (pre-existing) | `uv run pytest tests/test_ticket_service.py tests/integration/test_ticket_flow.py tests/test_ticket_db.py -q` → **224 passed** (exit 0) |
| Static checks | `ruff check` on PR5 paths → **All checks passed** (after `ruff format`); `ruff format --diff` → clean; `mypy` on `ticket_service.py` → **Success: no issues** |
| Runtime harness | Mocked Discord guild/channel + fake Supabase catalog; no live gateway login, no live Supabase writes (dispatched via `AuditListener.on_guild_channel_delete` and `TicketService.sweep_integrity`) |
| Rollback boundary | `tests/test_ticket_service.py::TestPR5IdempotencyAndBestEffort` + `tests/integration/test_ticket_flow.py::TestPR5DisabledSliceAndAuditDeterminism` + `verify-report.md` — revert only this slice by deleting those two test classes and the report; PR1-4 remain landed |

**Remaining cross-cutting**

- **E.1 G.2 fresh-evidence**: still **pending** — no authoritative read-only deployment/migration insertion was performed in this 800-budget slice. `verify-report.md` records the boundary and `gate_unresolved` is the intended no-mutation behavior.
- **E.2 Ticket #3 corroboration**: still **pending** — live `fetch_channel` for `1524826303507730563` was exercised only via the mocked probe path. No live Discord login, no mutation; `verify-report.md` records UNVERIFIED with the prior `live-pending.md` snapshot preserved.
- **E.3**: already proven via PR1 structural tests (migrations/015 parity).

**G.2 / Remaining Evidence (updated)**

- **G.2 remains `gate_unresolved`** until fresh deployment/schema evidence is explicitly persisted. Repair activation stays fail-closed.
- Phases 5.1-5.5 are now marked `[x]` in `tasks.md` under Strict TDD with exact harness evidence above. Only E.1/E.2 remain unchecked (2/31).
- No commit/push/PR/review/archive or live mutation was performed.
