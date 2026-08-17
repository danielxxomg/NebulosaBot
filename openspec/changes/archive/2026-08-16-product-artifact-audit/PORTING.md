# PORTING — Product Artifact Audit → Canonical Lifecycle

## Purpose

This file records how requirements and evidence from the superseded
`ticket-integrity-reconciliation` change are ported into the canonical
`ticket-integrity-recovery` lifecycle, so no useful contract is lost when the
conflicting active change is retired. It is a governance ledger only — it
does not modify either change's artifacts.

## Canonical Lifecycle

- **Canonical change:** `openspec/changes/ticket-integrity-recovery/`
- **Retiring change:** `openspec/changes/ticket-integrity-reconciliation/`
- **Canonical rule:** no completion/archive claim for the cluster may proceed
  without a `verify-report.md` (see `tests/test_product_artifact_audit_governance.py`
  and `governance_guard.py`).

## Reconciliation Requirements → Recovery Mapping

| Reconciliation requirement | Recovery location | Ported? | PR |
|---|---|---|---|
| `CloseResult` dataclass (frozen, success/denied/error, reason, transcript URL, evidence_id) | `bot/models/ticket.py::CloseResult` | Yes | PR1 |
| `IntegrityEvidence` tri-state (`channel_exists=None` → `corroborated=None`, never coerced to `False`) | `bot/models/ticket.py::IntegrityEvidence` | Yes (extended with `observed_at`, `evidence_id`) | PR1 |
| `RepairResult` deterministic outcomes + required evidence_id on `close/repaired` | `bot/models/ticket.py::RepairResult` | Already present (PR2 of recovery) | PR1/PR2 |
| Close-reason mapping incl. `zombie:*` skip (transcript/countdown/delete) | `bot/services/ticket_service.py::close_ticket` | Already present | PR2 |
| Localized close-result UX keys | `bot/locales/{en,es}.json` (`tickets.close.result_*`) | **Not ported — close UX is a non-goal for this recovery cluster** (see `FOLLOW_UP.md`; tracked as reconciliation close-UX debt) | n/a |
| Atomic conditional close (one winner, no read-then-write race) | `bot/core/db/ticket_db.py::transition_ticket_to_closed` | Already present | PR2 |
| Denied close audit with non-empty reason | `bot/services/ticket_service.py::close_ticket` denied path | Already present | PR2 |
| Channel-delete event routing → shared repair path | `bot/listeners/audit_listener.py::on_guild_channel_delete` + `bot/services/ticket_service.py::handle_channel_delete` | Yes | PR4a |
| Bounded sweep + manual fallback (fresh probe, 403/429/timeout fail-closed) | `bot/services/ticket_service.py::sweep_integrity`/`repair_ticket_manual` + `probe_channel_absence`/`plan_sweep_batch`/`backoff_delay` | **Landed — service primitives (PR4b-a) + command adapters `/sweep_integrity` `/repair_ticket` (PR4b-b)** | PR4b-a / PR4b-b |
| Guild audit vs operator diagnosis (truthful `mutated=False` without grant) | `bot/services/logging_service.py::build_repair_audit_record`/`build_operator_diagnosis_record` | **Landed (PR4b-b)** | PR4b-b |

## Evidence Porting

| Reconciliation evidence | Disposition |
|---|---|
| PR1B1 evaluator tests (`tests/test_integrity_report.py`) | Not re-created — recovery's `integrity_report.py` + `test_ticket_integrity.py` cover the G.2 gate contract. Historical evidence preserved in reconciliation `apply-progress.md`. |
| PR2 close-UX claims (C12–C17) | **Not landed** — recorded as historical claims only; close UX is out of scope for this recovery cluster (see `FOLLOW_UP.md`). |
| PR3/PR4 claims (C18–C26) | **PR4a landed (channel-delete routing)**, **PR4b-a landed (sweep/manual service primitives + coordinator)**, and **PR4b-b landed (command adapters `/sweep_integrity` `/repair_ticket`, `build_repair_audit_record`/`build_operator_diagnosis_record`, integration proof, docs)**. Backup revalidation remains a separate non-goal. |
| Live Supabase evidence | Superseded by the fresh read-only refresh in `product-artifact-audit/evidence/live-pending.md` (2026-08-12). |
| TI-020 contract fixture | Restored in `tests/contract/test_ticket_invariants.py` (work unit `ti020-contract-fixture-normalization`). |

## Guard Rule

`archive_claim_allowed(change_dir, tasks_checked, tasks_total)` returns
`(False, reason)` unless the change folder exists, every task box is checked,
AND `verify-report.md` is present. The reconciliation change claims full
completion without a verify report — its archive is therefore blocked by this
guard until independently verified evidence exists.

## Non-goals

- Advisor WARN/INFO findings (leaked-password protection, `rls_enabled_no_policy`)
  are not ported and never authorize repair.
- No `/setup` audit, dashboard expansion, or broad RLS remediation is ported.
