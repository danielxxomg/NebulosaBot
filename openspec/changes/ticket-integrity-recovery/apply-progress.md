# Apply Progress: Ticket Integrity Recovery — PR1 + PR2

## Scope

- **Branch (PR1):** `feat/ticket-integrity-recovery-pr1`
- **Branch (PR2):** `feat/ticket-integrity-recovery-pr2` (targets PR1)
- **Mode:** Strict TDD
- **Completed scope:** tasks 1.1–1.7, E.3, 2.1–2.6
- **Out of scope:** startup/hourly sweeps, channel-delete listener (PR3), manual repair command (PR4), backup/restore, CI, greeting/dashboard changes

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

## Migration Parity Evidence (E.3)

- On-disk filename: `migrations/015_ticket_lifecycle_reliability.sql`.
- Production registry status reports migration `20260713153020 / 015_ticket_lifecycle_reliability` as applied.
- Structural tests verify: nullable `closeReason`, active slot/channel indexes, normalized active category-name index, guild ticket-number index, and guarded obsolete backup-table cleanup.
- No migration registry insert, re-apply command, rollback/down migration, or production write was performed.

## G.2 / Remaining Evidence

- **G.2 remains `gate_unresolved`.** `evaluate_preflight()` defaults `evidence_persisted=False`; repair activation is false until fresh deployment/schema evidence is explicitly persisted.
- **E.1 remains pending:** authoritative fresh deployment compatibility evidence must be recorded before any repair mutation.
- **E.2 remains pending:** ticket #3 must be re-verified against current DB/channel state without inheriting quarantine evidence.
- Phase 3 tasks 3.1–3.5 (authoritative channel-delete listener) and all later phase tasks remain pending.

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
