# Apply Progress: Ticket Integrity Recovery — PR1

## Scope

- **Branch:** `feat/ticket-integrity-recovery-pr1`
- **Boundary:** PR1 child branch targeting `feat/ticket-integrity-recovery`
- **Mode:** Strict TDD
- **Completed scope:** tasks 1.1–1.7 and migration parity evidence E.3 only
- **Out of scope:** all repair mutations, startup/hourly sweeps, channel-delete wiring, manual repair, conditional close, backup/restore, CI, greeting/dashboard changes, and quarantine artifacts

## Completed Tasks

- [x] 1.1 Migration 015 parity tests and incompatible-parity contract
- [x] 1.2 Restore production-applied migration 015 on disk without applying or down-migrating
- [x] 1.3 Migration structural tests green
- [x] 1.4 IntegrityEvidence and RepairResult contract tests
- [x] 1.5 Frozen model implementations with camelCase serialization
- [x] 1.6 Read-only G.2 preflight tests
- [x] 1.7 Preflight/reporting implementation and bounded constants
- [x] E.3 Filename, schema-object, and applied-status parity evidence

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_migrations.py` | Unit/structural | 29 existing migration tests passed in RED run | 3 missing-015 failures | 31/31 pass with `--no-cov` | Schema fragments plus forbidden apply/down checks | Clean |
| 1.2 | `tests/test_migrations.py` | Unit/structural | N/A — new migration file | Missing-file RED from 1.1 | 31/31 pass | Four indexes, nullable column, guarded cleanup | Clean |
| 1.3 | `tests/test_migrations.py` | Unit/structural | 31/31 | Inherited missing-file RED | 31/31 pass | Parity and no-apply assertions | Clean |
| 1.4 | `tests/test_ticket_model.py`, `tests/test_ticket_integrity.py` | Unit | 27/27 existing model tests | Import/collection failure for missing contracts | 32 model + 10 integrity tests pass | Live/closed edge paths, all four outcomes, serialization | Clean |
| 1.5 | `tests/test_ticket_model.py` | Unit | 27/27 | Missing model import | 32/32 pass | Round-trip and immutable evidence cases | Clean |
| 1.6 | `tests/test_ticket_integrity.py` | Unit | N/A — new focused file | Import failure for missing preflight/constants | 10/10 pass | Mismatch, unsupported mode, drift, missing fresh evidence | Clean |
| 1.7 | `tests/test_ticket_integrity.py` | Unit | N/A — new service/config surface | Import failure for missing constants/report | 10/10 pass | Explicit `incompatible` parity and bounded values | Clean |

## Work Unit Evidence

| Evidence | Result |
|----------|--------|
| Focused test command and exact result | `uv run pytest --no-cov tests/test_migrations.py tests/test_ticket_model.py tests/test_ticket_integrity.py -q` → prior **73 passed**; bounded correction for `review-5f8215f32dd03408` rerun **74 passed** |
| Static checks | `uv run ruff check bot/config.py bot/models/ticket.py bot/services/integrity_report.py tests/test_migrations.py tests/test_ticket_model.py tests/test_ticket_integrity.py` → **All checks passed**; `uv run ruff format --check bot/config.py bot/models/ticket.py bot/services/integrity_report.py tests/test_migrations.py tests/test_ticket_model.py tests/test_ticket_integrity.py` → **6 files already formatted**; `python -m py_compile bot/config.py bot/models/ticket.py bot/services/integrity_report.py` → **pass** |
| Runtime harness command/scenario and exact result | **N/A** — this unit contains read-only models/preflight and migration text only; it has no Discord/API runtime boundary and performs no live ticket mutation |
| Rollback boundary | Revert `migrations/015_ticket_lifecycle_reliability.sql`, the `IntegrityEvidence`/`RepairResult` additions in `bot/models/ticket.py`, `bot/services/integrity_report.py`, the three bounded constants in `bot/config.py`, and their focused tests. Leave all other ticket behavior untouched. |

## Migration Parity Evidence (E.3)

- On-disk filename: `migrations/015_ticket_lifecycle_reliability.sql`.
- Production registry status was checked read-only and reports migration `20260713153020 / 015_ticket_lifecycle_reliability` as applied.
- Structural tests verify the production schema contract: nullable `closeReason`, active slot/channel indexes, normalized active category-name index, guild ticket-number index, and guarded obsolete backup-table cleanup.
- No migration registry insert, re-apply command, rollback/down migration, or production write was performed.

## G.2 / Remaining Evidence

- **G.2 remains `gate_unresolved`.** `evaluate_preflight()` defaults `evidence_persisted=False`; repair activation is false until fresh deployment/schema evidence is explicitly persisted.
- **E.1 remains pending:** authoritative fresh deployment compatibility evidence must be recorded before any repair mutation.
- **E.2 remains pending:** ticket #3 must be re-verified against current DB/channel state without inheriting quarantine evidence.
- Phase 2 tasks 2.1–2.6 and all later phase tasks remain pending.

## Verification Notes

- Full verification was intentionally not run in this apply phase.
- No review, bind/recover, commit, push, archive, live migration application, or repair activation was performed.
