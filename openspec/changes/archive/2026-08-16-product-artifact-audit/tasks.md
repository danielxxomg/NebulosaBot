# Tasks: Product Artifact Audit

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 660–920 |
| 800-line budget risk | High |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1→PR2→PR3→PR4a→PR4b |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main (PR4a = channel-delete event + single-use evidence adapter; PR4b = sweep/manual/logging/integration)
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Test | Harness | Rollback |
|------|------|----|------|---------|----------|
| 1 | Evidence+preflight | PR1 | `uv run pytest tests/test_ticket_model.py tests/test_ticket_integrity.py -q` | N/A SELECT-only | `ticket.py`, `integrity_report.py` |
| 2 | Coordinator+DB | PR2 | `uv run pytest tests/test_ticket_service.py tests/test_ticket_db.py -q` | N/A fake DB | `ticket_service.py`, `ticket_db.py` |
| 3 | Authority+audit | PR3 | `uv run pytest tests/contract/test_ticket_invariants.py -q` | N/A mocked | `ticket_invariants.py` |
| 4 | Adapters | PR4a/PR4b | `uv run pytest tests/test_audit_listener.py -q` (PR4a) | N/A mocked | `audit_listener.py`, `ticket_service.py::handle_channel_delete` (PR4a); `tickets.py`, `ticket_repair.py`, `logging_service.py` (PR4b) |

## Phase 0: Governance

- [x] 0.1 `PORTING.md` port recon; recovery canonical. EV:file.
- [x] 0.2 RED→GREEN `tests/test_product_artifact_audit_governance.py` block archive until verify. EV:`uv run pytest -k governance -q`.
- [x] 0.3 Live SELECT-only (health/015+`fetch_channel`/ticket) → `evidence/live-pending.md`; no writes. EV:file.

## Phase 1: Foundation

- [x] 1.1 RED `tests/test_ticket_model.py` `IntegrityEvidence` `bool|None`+window; `corroborated` iff active∧False∧fresh else unresolved. Threat:false positives.
- [x] 1.2 GREEN `bot/models/ticket.py` frozen camelCase. EV:`uv run pytest tests/test_ticket_model.py -q`.
- [x] 1.3 RED `tests/test_ticket_model.py` `RepairResult`/`CloseResult` `repaired/already_closed/quarantined/error` with reason/evidence_id.
- [x] 1.4 RED `tests/test_ticket_integrity.py` preflight `resolved` iff 015∧mode∧no-drift∧persisted else `gate_unresolved`. Threat:env/migration.
- [x] 1.5 GREEN `bot/services/integrity_report.py` read-only. EV:`uv run pytest tests/test_ticket_integrity.py -q`.

## Phase 2: Coordinator

- [x] 2.1 RED `tests/test_ticket_service.py` deny if preflight unresolved or not corroborated → `quarantined/skipped` no DB. Covers ambiguous/stale/advisor/rollback.
- [x] 2.2 RED `tests/test_ticket_db.py` `transition_ticket_to_closed(guild_id,ticket_id,("open","claimed"))` one-winner. Threat:guild isolation/race.
- [x] 2.3 GREEN `bot/services/ticket_service.py::repair_ticket_from_evidence`+DB; adapters never mutate. EV:`uv run pytest tests/test_ticket_db.py tests/test_ticket_service.py -q`.
- [x] 2.4 RED duplicate→one `repaired` one `already_closed`; TRIANGULATE unknown→quarantine; REFACTOR `evaluate_evidence`. Threat:duplicate.

## Phase 3: Authority & Audit

- [x] 3.1 RED `tests/test_ticket_invariants.py` one mod role; owner/Admin same-guild bypass only; cross-guild denied; actor info only. Threat:permissions.
- [x] 3.2 RED `tests/test_ticket_invariants.py` operator read-only; explicit confirmed audited grant else denied.
- [x] 3.3 GREEN `bot/services/ticket_invariants.py`. EV:`uv run pytest tests/contract/test_ticket_invariants.py -q`.
- [x] 3.4 RED `tests/test_ticket_service.py` denied/quarantined/error→non-empty reason; `insert_audit_row` fail→WARNING never `repaired`. Threat:audit-write.

## Phase 4: Adapters — PR4a landed / PR4b-a landed / PR4b-b landed

> Real split (maintainer-approved): **PR4a = channel-delete event + single-use
> evidence adapter only**; **PR4b = sweep/manual/logging/integration**, further
> split into **PR4b-a = sweep/manual service primitives + coordinator
> behavior** (this candidate) and **PR4b-b = command adapters + structured
> logging + integration proof + localization/docs** (deferred).
> Only PR4a and PR4b-a (service layer) are implemented in the working tree.
> PR4b-b is deferred, not complete.

- [x] 4.1 RED `tests/test_audit_listener.py` `on_guild_channel_delete` single-use event evidence; non-ticket log only. Threat:event routing. → **PR4a**
- [x] 4.2 RED `tests/test_ticket_service.py` sweep/manual `fetch_channel` fresh/attempt (`probe_channel_absence`); 403/timeout/429/unknown/missing-guild/malformed-id→unresolved (`None`); only `NotFound`→corroborated (`False`). Threat:Discord/rate/false positives. → **PR4b-a**
- [x] 4.3 RED `tests/test_ticket_service.py` bounded `plan_sweep_batch` (50) + `backoff_delay` (clamped) no duplicate; unresolved→reviewable `skipped` dry-run (no mutation). Threat:backoff/rollback. → **PR4b-a**
- [x] 4.4 GREEN `bot/services/ticket_service.py` coordinator (`sweep_integrity` + `repair_ticket_manual` delegating to shared `repair_ticket_from_evidence`). PR4a portion done (`audit_listener.py`→`handle_channel_delete`→coordinator). **Service-level portion done (PR4b-a); `bot/cogs/tickets.py` command adapters (`/sweep_integrity` `/repair_ticket`) deferred (PR4b-b).** EV (PR4a):`uv run pytest tests/test_audit_listener.py -q`; EV (PR4b-a):`uv run pytest tests/test_ticket_service.py -q`. → **PR4a + PR4b-a service done; PR4b-b commands pending**
- [x] 4.4-b GREEN `bot/cogs/tickets.py` `sweep_integrity` + `repair_ticket` hybrid commands (thin delegators, `@is_mod()`, `RepairAuthority` from ctx) + `bot/core/i18n.py` registry + `bot/locales/{en,es}.json` keys + `docs/MANUAL.md` rows. → **PR4b-b**

## Phase 5: Verify (no archive) — PR4b-b done

- [x] 5.1 RED `tests/test_logging_service.py` guild scoped; operator `mutated=False` without grant; reason/source (`build_repair_audit_record` / `build_operator_diagnosis_record`). → **PR4b-b**
- [x] 5.2 GREEN `bot/services/logging_service.py`. EV:`uv run pytest tests/test_logging_service.py -q`. → **PR4b-b**
- [x] 5.3 RED `tests/integration/test_ticket_flow.py` disabled→no mutation; e2e delete→evidence→preflight→repair→close→audit across entry points. → **PR4b-b**
- [x] 5.4 Finalize `PORTING.md`; keep recon unarchived until `verify-report.md`; `FOLLOW_UP.md` for `/setup` audit non-goal. → **PR4b-b**
