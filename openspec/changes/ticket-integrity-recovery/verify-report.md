```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:fd4b72edea5af0c195b132e19bf64aed88d14b4a8a408800e38539bab297902c
verdict: fail
blockers: 5
critical_findings: 5
requirements: 3/11
scenarios: 32/44
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:4b8d4f77e2266670920102c81b8c562fd892cedc238a281387b396e53f989637
build_command: python -m py_compile bot/__main__.py
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: `ticket-integrity-recovery`  
**Version**: N/A  
**Mode**: Strict TDD  
**Artifact store**: OpenSpec  
**Verifier**: independent terminal verification  
**Date**: 2026-08-17  
**Branch**: `feat/ticket-integrity-recovery-pr2`  
**Base**: `d671a91` (`product-artifact-audit` archived)  
**Active attempt**: ordinal 7, work unit `terminal-verification-rerun`, token `sha256:71b7cdbea9f4b4d08b2e8ce7285f1ae239ca8f280e8131001964ae6d364a101d`, native budget 800

### Executive Summary

The remediation runtime is green: the requested boundary suite passed 343 tests, the complete change suite passed 488 tests, and the full suite passed 1,751 tests with 3 skips at 88.34% coverage. Independent specification verification nevertheless **FAILS**: automatic and manual audit rows still persist `success` instead of the required `repaired`, the unresolved-gate sweep does not return a dry-run candidate with `corroborated=True`, and the narrowed `RepairResult` enum leaves a cross-guild reference path raising `ValueError`.

The live reads remain read-only and fail-closed. Migration 015 is applied and `ticket.closeReason` is nullable, while the current `ticket_audit` database check still permits only `success|denied|error`; G.2 therefore remains intentionally `gate_unresolved` and no repair activation is authorized.

### Current Identity and Completeness

| Dimension | Status | Evidence |
|---|---:|---|
| Proposal | ✅ Present | `openspec/changes/ticket-integrity-recovery/proposal.md` |
| Specs | ✅ Present | 3 spec files; 11 requirements and 44 scenarios counted from source |
| Design | ✅ Present | `openspec/changes/ticket-integrity-recovery/design.md` |
| Tasks | ✅ 31/31 | `gentle-ai sdd-status ticket-integrity-recovery --json` reports pending 0 |
| Apply progress | ✅ Present / ⚠️ contradictory history | `apply-progress.md` has current 31/31 rows plus stale lines saying phase 5/E.1/E.2 remain pending |
| Prior verify report | ⚠️ Replaced | Previous validator-admitted FAIL report was read before this candidate |
| Action context | ✅ Repo-local | Workspace and allowed edit root are `/home/danielxxomg/Projects/NebulosaBot` |

Actual spec totals are **11 requirements / 44 scenarios**. The candidate reports **3 fully complete requirements / 32 fully compliant scenarios**, with 8 partial and 4 failing scenarios.

### Completeness

| Task group | Checkbox state | Verification judgment |
|---|---:|---|
| 1.1–1.7, E.3 | 8/8 | Migration/model/preflight artifacts and focused tests present; parity is only partially bound to live evidence in one flow |
| 2.1–2.6 | 6/6 | Conditional DB and coordinator tests execute successfully |
| 3.1–3.5 | 5/5 | Authoritative class is restored and its four tests pass; duplicate assertions remain incomplete |
| 4.1–4.5 | 5/5 | Sweep/manual/cog tests pass; exact audit and dry-run contracts remain divergent |
| 5.1–5.5 | 5/5 | Idempotency, best-effort warning, disabled-slice, integration, and full-suite checks pass |
| E.1–E.2 | 2/2 | Existing 2026-08-17 12:43 read-only fail-closed evidence is preserved; no activation is authorized |
| **Total** | **31/31** | **Task checkboxes complete; specification compliance is not complete** |

### Build, Test, Coverage, and Quality Evidence

#### Runtime tests

| Layer/file | Exact command | Exit | Result | Output hash |
|---|---|---:|---|---|
| Final full suite + configured coverage | `uv run pytest -q` | 0 | 1,751 passed, 3 skipped; 88.34% coverage; threshold 75% reached | `sha256:4b8d4f77e2266670920102c81b8c562fd892cedc238a281387b396e53f989637` |
| Complete change suite | `uv run pytest --no-cov tests/test_ticket_integrity.py tests/test_ticket_model.py tests/test_ticket_db.py tests/test_ticket_service.py tests/test_audit_listener.py tests/test_tickets_cog.py tests/test_remediation_7_missing_scenarios.py tests/integration/test_ticket_flow.py tests/test_migrations.py -q` | 0 | 488 passed | `sha256:e70d277c1ed98a3d38242eedfa337c0572a56103418b830ef535a83105e01782` |
| Requested remediation boundary suite | `uv run pytest --no-cov tests/test_audit_listener.py tests/test_ticket_service.py tests/test_tickets_cog.py tests/test_remediation_7_missing_scenarios.py tests/integration/test_ticket_flow.py -q` | 0 | 343 passed | `sha256:cef3083f30bbcd243603cda7a0efe2dbd13dd33dd692db5defb92651c778a822` |
| Governance guard | `uv run pytest --no-cov tests/test_product_artifact_audit_governance.py -q` | 0 | 6 passed | `sha256:d5be81bbe49b412357ba177be7fae47b32ba70b563d2a01ec6ee15df362cc215` |

#### Build and quality checks

| Check | Exact command | Exit | Result | Output hash |
|---|---|---:|---|---|
| Required build | `python -m py_compile bot/__main__.py` | 0 | Passed; empty output | `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Changed-path compile | `uv run python -m py_compile bot/cogs/tickets.py bot/config.py bot/core/db/ticket_db.py bot/listeners/audit_listener.py bot/models/ticket.py bot/services/integrity_report.py bot/services/ticket_invariants.py bot/services/ticket_service.py governance_guard.py tests/contract/test_ticket_invariants.py tests/integration/test_ticket_flow.py tests/test_audit_listener.py tests/test_remediation_7_missing_scenarios.py tests/test_ticket_model.py tests/test_ticket_service.py tests/test_tickets_cog.py` | 0 | Passed | `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Changed-path Ruff | `uv run ruff check bot/cogs/tickets.py bot/config.py bot/core/db/ticket_db.py bot/listeners/audit_listener.py bot/models/ticket.py bot/services/integrity_report.py bot/services/ticket_invariants.py bot/services/ticket_service.py governance_guard.py tests/contract/test_ticket_invariants.py tests/integration/test_ticket_flow.py tests/test_audit_listener.py tests/test_remediation_7_missing_scenarios.py tests/test_ticket_model.py tests/test_ticket_service.py tests/test_tickets_cog.py` | 1 | 1 import-order error in new `tests/test_remediation_7_missing_scenarios.py` | `sha256:f9f89e6584fb14ab13ffe18040210793e0db94763180dd12b5af658e58c2f206` |
| Changed-path format | `uv run ruff format --check bot/cogs/tickets.py bot/config.py bot/core/db/ticket_db.py bot/listeners/audit_listener.py bot/models/ticket.py bot/services/integrity_report.py bot/services/ticket_invariants.py bot/services/ticket_service.py governance_guard.py tests/contract/test_ticket_invariants.py tests/integration/test_ticket_flow.py tests/test_audit_listener.py tests/test_remediation_7_missing_scenarios.py tests/test_ticket_model.py tests/test_ticket_service.py tests/test_tickets_cog.py` | 1 | `bot/services/ticket_invariants.py` would be reformatted; pre-existing outside this remediation diff | `sha256:04ae341833a645e3ef98b81ca1fef3dcc39f068667ee8b765d3bdf45c957c10a` |
| Changed-path type check | `uv run mypy bot/services/ticket_service.py bot/services/integrity_report.py bot/core/db/ticket_db.py bot/listeners/audit_listener.py bot/cogs/tickets.py bot/models/ticket.py bot/config.py governance_guard.py` | 0 | Success: no issues found in 8 source files | `sha256:157a09cfcdfdfb5977479c5a1c08345149263a3e990a2ec976ef28aaeec9ca6e` |
| Full Ruff | `uv run ruff check` | 1 | 31 findings, all outside changed integrity production paths except the new test import order | `sha256:e2dd2e8b6e29afdc3e6501a729f12a4b5b7b6ca07c88351740b767acaed0d7c7` |
| Full format | `uv run ruff format --check` | 1 | 26 unrelated files would be reformatted, including pre-existing `ticket_invariants.py` | `sha256:59684c38974f2064cffcbba30cd1426d028141a1877485771ff41c73bded0f7d` |
| Full production type check | `uv run mypy bot governance_guard.py` | 1 | 27 inherited errors in `stellar.py`, `ocio.py`, `greetings.py`, and `core.py`; none in changed integrity paths | `sha256:dc2dcaf103293622bd47eb111fdb3d5a996b2189d55d964f4fa5251264b9fd43` |

Repository coverage is 88.34%. Changed production-file coverage is listed below; branch coverage was not emitted.

| Changed production file | Line coverage | Rating |
|---|---:|---|
| `bot/cogs/tickets.py` | 83% | ⚠️ Acceptable |
| `bot/core/db/ticket_db.py` | 88% | ✅ Good |
| `bot/listeners/audit_listener.py` | 87% | ⚠️ Acceptable |
| `bot/models/ticket.py` | 100% | ✅ Excellent |
| `bot/services/integrity_report.py` | 96% | ✅ Excellent |
| `bot/services/ticket_service.py` | 83% | ⚠️ Acceptable |
| `bot/config.py` | 100% | ✅ Excellent |
| `bot/services/ticket_invariants.py` | 98% | ✅ Excellent |

Average changed production-file coverage: **91.9%**.

### Strict TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | `apply-progress.md` contains the TDD Cycle Evidence table |
| All implementation task rows have test files | ✅ | 28/28 implementation rows reference files present in the tree; E.1/E.2/E.3 are evidence rows |
| RED files confirmed | ✅ | All referenced test files exist; historical RED chronology is not independently reconstructable |
| GREEN runtime confirmation | ✅ | All referenced test files pass in the 488-test change suite or full suite |
| Triangulation adequate | ⚠️ | Listener duplicate results, dry-run candidate shape, and exact audit contracts remain under-asserted |
| Safety-net evidence | ⚠️ | Current tests pass, but apply-progress retains contradictory historical completion rows |

**TDD Compliance**: 4/6 checks fully confirmed; 2 checks carry warnings.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit/structural | 474 | 8 | pytest, pytest-asyncio, mocks/fake DB |
| Integration | 14 | 1 | pytest-asyncio, mocked Discord/Supabase boundary |
| E2E | 0 | 0 | Not configured (`e2e: false`) |
| **Total** | **488** | **9** | |

### Assertion Quality

No tautologies, ghost loops, or assertion-only tests were found. The following meaningful assertions are under-specified for the corresponding scenarios:

| File | Lines | Assertion | Issue | Severity |
|---|---:|---|---|---|
| `tests/test_audit_listener.py` | 629–630 | `assert db.transition_ticket_to_closed.await_count == 2` | Does not assert one `repaired` and one `already_closed` result for the real listener race | WARNING |
| `tests/test_remediation_7_missing_scenarios.py` | 84–112 | Close-reason assertions | Test name claims audit actions but never inspects `ticket_audit` calls or outcomes | WARNING |
| `tests/integration/test_ticket_flow.py` | 855–858 | Filters only `outcome == "success"` | A denied repair audit row would pass unnoticed in the no-op scenario | WARNING |

**Assertion quality**: 0 CRITICAL, 3 WARNING.

### Live Read-Only Corroboration

No live write was performed. Fresh Supabase operations were `list_projects`, `list_migrations`, and `list_tables`; the Discord boundary used an authenticated REST `fetch_channel` probe. The Discord MCP frontend was not ready, so the read-only `discord.py` REST client was used without gateway mutation.

| Boundary | Observed evidence | Judgment |
|---|---|---|
| Supabase project | `nebulosabot`, ref `vozkcckiybebhcclrasa`, `ACTIVE_HEALTHY` | ✅ |
| Migration 015 status | `20260713153020 / 015_ticket_lifecycle_reliability` is applied | ✅ |
| Ticket schema | `public.ticket.closeReason` is nullable | ✅ |
| Ticket-audit schema | `public.ticket_audit.outcome` check is `success|denied|error` | ⚠️ Contradicts the ticket-integrity spec's `repaired` value |
| Discord fetches | Guild `1518709129403695154`: #3 `1524826303507730563`, #16 `1527169412849995788`, and #17 `1527174095249215588` all returned `NotFound` | ✅ read-only corroboration |
| E.1/E.2 operational evidence | Apply artifacts preserve 2026-08-17 12:43 startup/hourly/channel-delete denials and per-ticket probes with no mutation | ✅ fail-closed evidence |
| G.2 activation | Remains `gate_unresolved` by design; no persisted activation evidence was supplied | ✅ intentional gate |

Fetch output hash: `sha256:29694254859e43acbe553563f075effb5db734313747053c0e34b84edfcf7450`.

### Spec Compliance Matrix

Status meanings: ✅ `COMPLIANT` means a covering runtime test passed; ⚠️ `PARTIAL` means only part of the scenario is asserted; ❌ `FAILING` means current behavior or independent runtime evidence contradicts the scenario.

| ID | Requirement / scenario | Covering runtime test or evidence | Result |
|---|---|---|---|
| DB-1.1 | Production-applied migration restored on disk | `tests/test_migrations.py::TestMigrationParity::test_015_schema_objects_match_production_definition` + tracked-file check + live migration read | ✅ COMPLIANT |
| DB-1.2 | Parity checked before reliance | `tests/test_ticket_integrity.py::test_preflight_resolves_only_with_complete_fresh_evidence` + live reads; no runtime binding joins disk and production facts | ⚠️ PARTIAL |
| DB-1.3 | Parity mismatch blocks reliance | `tests/test_ticket_integrity.py::test_migration_parity_reports_compatible_or_incompatible` + `test_preflight_keeps_gate_unresolved_for_incomplete_evidence` | ✅ COMPLIANT |
| DB-2.1 | Compatible evidence resolves G.2 | `tests/test_ticket_integrity.py::test_preflight_resolves_only_with_complete_fresh_evidence` | ✅ COMPLIANT |
| DB-2.2 | Missing evidence blocks activation | `tests/test_ticket_integrity.py::test_preflight_keeps_gate_unresolved_for_incomplete_evidence` + `test_missing_live_evidence_fails_closed` | ✅ COMPLIANT |
| DB-2.3 | Unsupported deployment or drift blocks activation | Parameterized incomplete-preflight tests + `test_stale_live_evidence_fails_closed` | ✅ COMPLIANT |
| DB-2.4 | Preflight does not mutate tickets | `tests/test_ticket_integrity.py::test_preflight_is_read_only_no_ticket_mutation` | ✅ COMPLIANT |
| MODEL-1.1 | Deserialize active missing-channel evidence | `tests/test_ticket_model.py::test_integrity_evidence_derives_corrobated_zombie_from_active_missing_channel` | ✅ COMPLIANT |
| MODEL-1.2 | Existing channel is not corroborated | `tests/test_ticket_model.py::test_integrity_evidence_does_not_corrobate_live_or_closed_ticket` | ✅ COMPLIANT |
| MODEL-1.3 | Closed ticket is not corroborated | `tests/test_ticket_model.py::test_integrity_evidence_does_not_corrobate_live_or_closed_ticket` | ✅ COMPLIANT |
| MODEL-1.4 | Evidence serializes camelCase | `tests/test_ticket_model.py::test_integrity_evidence_serializes_camelcase_without_mutating_input` | ✅ COMPLIANT |
| MODEL-2.1 | Corroborated repair returns close/repaired with evidence | `tests/test_ticket_service.py::TestRepairTicketFromEvidence::test_repaired_when_evidence_corroborated` | ✅ COMPLIANT |
| MODEL-2.2 | Already-closed repair is no-op | `tests/test_ticket_service.py::TestRepairTicketFromEvidence::test_already_closed_returns_no_op` | ✅ COMPLIANT |
| MODEL-2.3 | Non-corroborated evidence is skipped | `tests/test_ticket_service.py::TestRepairTicketFromEvidence::test_not_corroborated_returns_skipped` | ✅ COMPLIANT |
| MODEL-2.4 | Transient verification error records exception class | `test_transient_discord_error_returns_error` injects a generic DB exception rather than a Discord verification exception | ⚠️ PARTIAL |
| SERVICE-1.1 | Normal close generates transcript and deletes after countdown | `tests/integration/test_ticket_flow.py::TestTicketFlow::test_close_ticket_generates_transcript` | ✅ COMPLIANT |
| SERVICE-1.2 | Unclaimed close preserves null claimant | `tests/test_ticket_service.py::test_close_ticket_updates_status` uses an unclaimed fixture but does not assert `claimedBy is None` | ⚠️ PARTIAL |
| SERVICE-1.3 | Provided close reason persists | `tests/test_ticket_service.py::TestCloseTicketConditional::test_close_reason_persists_when_provided` | ✅ COMPLIANT |
| SERVICE-1.4 | None close reason is not overwritten | `tests/test_ticket_service.py::TestCloseTicketConditional::test_close_reason_none_does_not_overwrite` | ✅ COMPLIANT |
| SERVICE-1.5 | Zombie close skips transcript and channel deletion | `tests/test_ticket_service.py::TestCloseTicketConditional::test_zombie_path_skips_transcript_and_channel_deletion` asserts the result but not both skipped operations | ⚠️ PARTIAL |
| SERVICE-1.6 | Re-closing raises ValueError without mutation | `tests/test_ticket_service.py::TestCloseTicketConditional::test_reclosed_ticket_raises_value_error` | ✅ COMPLIANT |
| SERVICE-2.1 | Resolved authoritative event repairs active zombie | `tests/test_audit_listener.py::TestAuthoritativeChannelDeletePR3::test_resolved_preflight_reaches_conditional_close` proves the real listener reaches the close, but does not assert the returned `RepairResult` | ⚠️ PARTIAL |
| SERVICE-2.2 | No active ticket is a no-op | `tests/test_ticket_service.py::TestHandleChannelDelete::test_channel_delete_no_match_returns_none_no_mutation` | ✅ COMPLIANT |
| SERVICE-2.3 | Unresolved G.2 logs detection and skips repair | `TestAuthoritativeChannelDeletePR3::test_gate_unresolved_is_fail_closed_no_mutation` + preserved live denials | ✅ COMPLIANT |
| SERVICE-2.4 | Duplicate event race yields repaired then already_closed | `TestAuthoritativeChannelDeletePR3::test_two_resolved_events_one_repaired_one_already_closed` only asserts two transitions; coordinator-level result test is separate | ⚠️ PARTIAL |
| SERVICE-3.1 | Unresolved-gate sweep returns corroborated dry-run candidates | Independent probe returned only `RepairResult(... outcome=skipped, evidenceId=...)`; no `corroborated` field or covering test exists | ❌ FAILING |
| SERVICE-3.2 | Resolved sweep closes with `zombie:sweep` | `tests/test_remediation_7_missing_scenarios.py::test_exact_close_reasons_and_audit_actions` + `TestSweepIntegrity::test_corroborated_absence_repairs`; result reason is not asserted | ⚠️ PARTIAL |
| SERVICE-3.3 | Batch size 50 bounds 250 candidates | `tests/test_ticket_service.py::TestSweepIntegrity::test_bounded_batch_limits_probes` and `TestPlanSweepBatch::test_batch_is_bounded_and_deduped` | ✅ COMPLIANT |
| SERVICE-3.4 | 429 backs off, skips candidate, and proceeds | `tests/test_remediation_7_missing_scenarios.py::test_sweep_429_ratelimited_continues_with_backoff` | ✅ COMPLIANT |
| SERVICE-3.5 | Incomplete channel evidence skips without mutation | `tests/test_ticket_service.py::TestSweepIntegrity::test_unresolved_probe_dry_runs` | ✅ COMPLIANT |
| SERVICE-4.1 | Moderator repair uses manual reason and manual audit actor/outcome | Close reason/action are attempted, but direct probe shows `repair/success` plus `manual_repair/success`, not the required `manual_repair/repaired` row | ❌ FAILING |
| SERVICE-4.2 | Manual repair on live channel is a no-op | `tests/test_ticket_service.py::TestRepairTicketManual::test_allowed_live_channel_skipped` | ✅ COMPLIANT |
| SERVICE-4.3 | Manual repair is idempotent | `tests/test_remediation_7_missing_scenarios.py::test_manual_rerun_is_idempotent` | ✅ COMPLIANT |
| SERVICE-5.1 | Re-run does not create a second close mutation | `test_duplicate_repair_one_repaired_one_already_closed` + `test_manual_rerun_is_idempotent` | ✅ COMPLIANT |
| SERVICE-5.2 | Automatic audit uses repair/system/repaired | Direct probe shows `('123', 't1', 'repair', 'system', 'success', None)`; current DB constraint also excludes `repaired` | ❌ FAILING |
| SERVICE-5.3 | Manual audit uses manual_repair/mod/repaired | Direct probe shows two rows: `repair/mod1/success` and `manual_repair/mod1/success` | ❌ FAILING |
| SERVICE-5.4 | Audit failure does not block persisted close and warns | `tests/test_ticket_service.py::TestPR5IdempotencyAndBestEffort::test_successful_close_persists_despite_audit_warning` | ✅ COMPLIANT |
| SERVICE-5.5 | Finite batch mutates at most configured batch | `TestSweepIntegrity::test_bounded_batch_limits_probes` | ✅ COMPLIANT |
| SERVICE-6.1 | Transient Discord error skips candidate | `TestSweepIntegrity::test_unresolved_probe_dry_runs` | ✅ COMPLIANT |
| SERVICE-6.2 | 429 is a skip and never a mutation | `test_sweep_429_ratelimited_continues_with_backoff` + `TestProbeChannelAbsence::test_rate_limit_is_unresolved` | ✅ COMPLIANT |
| SERVICE-6.3 | DB mapping without channel check returns skipped | `tests/test_ticket_service.py::test_repair_quarantines_unknown_evidence` now asserts `skipped/evidence_unresolved` | ✅ COMPLIANT |
| SERVICE-7.1 | Disabled slice leaves tickets untouched | `tests/integration/test_ticket_flow.py::TestPR5DisabledSliceAndAuditDeterminism::test_disabled_slice_leaves_tickets_untouched` | ✅ COMPLIANT |
| SERVICE-7.2 | Deletion-only audit logging continues | Same integration test + `TestChannelDeleteRepairRouting` | ✅ COMPLIANT |
| SERVICE-7.3 | No-op run has no repair audit rows | `test_no_op_run_emits_no_close_and_no_repair_audit` checks only successful rows; source skips the live-channel audit, but exact all-row coverage is absent | ⚠️ PARTIAL |

**Compliance summary**: 32/44 scenarios are fully compliant; 8 are partial and 4 are failing. The envelope requirement count is 3/11 because only DB-2, MODEL-1, and SERVICE-6 have every scenario fully compliant.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---:|---|
| Migration 015 parity | ⚠️ Partial | File is tracked and structurally matches live migration/schema facts; no single runtime path binds all parity facts before reliance |
| G.2 preflight | ✅ Implemented | Read-only, explicit evidence gate, unsupported mode/drift fail closed |
| IntegrityEvidence | ✅ Implemented | Frozen model, camelCase mapping, fresh/unknown evidence handling |
| RepairResult | ⚠️ Divergent | Documented enum is narrowed, but `repair_ticket_by_ref` still constructs forbidden `no_op/denied` on cross-guild rows |
| Ticket close | ⚠️ Partial | Conditional close/reason preservation work; operation and unclaimed-field assertions are incomplete |
| Authoritative channel delete | ⚠️ Partial | Resolved preflight is forwarded through the real listener; result semantics are not exposed/asserted at the event boundary |
| Reconciliation sweep | ❌ Divergent | Gate-denied dry-run does not return a corroborated candidate report; no persistent cursor is present |
| Manual fallback | ❌ Divergent | G.2 bypass and close reason are correct, but audit action/outcome persistence is not |
| Idempotency/auditability | ❌ Divergent | Automatic/manual audit outcomes remain database `success`, not specified `repaired`; manual emits an extra automatic-style row |
| False-positive safety | ✅ Implemented | Only explicit `NotFound` corroborates absence; transient/unknown probes skip without mutation |
| Rollback/no-op | ⚠️ Partial | Disabled/no-op source behavior is conservative, but no-op audit absence is under-tested |

### Design Coherence

| Design decision | Followed? | Notes |
|---|---:|---|
| One shared evidence-gated coordinator and conditional DB race boundary | ✅ | Automatic, sweep, and manual paths reach the shared coordinator/conditional transition |
| Read-only migration/deployment rollout boundary | ✅ | Migration and live reads were inspected without applying/down-migrating or mutating tickets |
| Authoritative channel-delete event is stronger than a sweep | ✅ | Real listener now forwards a resolved live preflight and exact guild/channel facts |
| Bounded, rate-limit-safe sweeps | ⚠️ | Probe batch and 429 backoff are bounded; all candidate mappings are loaded before selection and no persistent cursor exists |
| Manual moderator fallback bypasses automatic G.2 | ✅ | Manual path performs fresh corroboration without relying on caller preflight |
| Best-effort audit must not block mutation | ❌ | Mutation survives audit failure, but persisted repair action/outcome vocabulary is not spec-compliant |
| G.4 backup/restore remains separate | ✅ | No backup, retention, or archive activation was performed |

### Issues Found

#### CRITICAL

1. **Automatic audit outcome remains non-compliant.** `repair_ticket_from_evidence` persists `action="repair"`, `actorId="system"`, and `outcome="success"`; the ticket-service spec requires `outcome="repaired"`. The live `ticket_audit` check also accepts only `success|denied|error`, and no current caller uses the separate `RepairAuditRecord` mapping. Direct runtime probe: `sha256:0d24a170f33877c6e84eac225f59e682131b1e0d470fd6f023ddc93efd7e0874`.
2. **Manual audit action/outcome still violates the contract.** Manual repair writes an initial `repair/mod1/success` row and a compensating `manual_repair/mod1/success` row; the required row is `manual_repair/mod1/repaired`, with no automatic-style duplicate. The close reason is now correct, but the audit contract is not.
3. **Unresolved sweep dry-run does not return the required corroborated candidate report.** The result contains only `evidenceId`, `outcome=skipped`, and `reason=gate_unresolved`; `RepairResult` has no `corroborated` field and no covering runtime test lists the candidates with `corroborated=True`. Direct probe: `sha256:dcd3d33505818d3545e76f77d404e6a74e256ae765937bfd5a583c160df0762e`.
4. **Enum narrowing introduced a cross-guild service regression.** `repair_ticket_by_ref` still returns `RepairResult(outcome="denied")` on a foreign-guild row, but `RepairResult` now rejects that combination. A real cross-guild reference therefore raises `ValueError` instead of returning a deterministic skipped result. Direct probe: `sha256:94682ce39e7b3d6c089cd484b29bb107c4c7da198cfacaa54ed8d89b5d936c68`.
5. **Required scenario proof remains incomplete despite green tests.** The new listener tests do not assert `repaired/already_closed` results, the new audit-named test does not inspect audit calls, no dry-run scenario test exists, and no exact automatic/manual `repaired` audit test passes. These gaps prevent a claim of 44/44 runtime compliance.

#### WARNING

1. G.2 remains `gate_unresolved` by design. Live schema facts and missing-channel reads do not authorize activation; no automatic repair should be enabled by this report.
2. DB parity is represented as caller-supplied booleans; the runtime does not itself bind the on-disk SQL bytes, production migration registry, and schema objects into one preflight transaction.
3. `sweep_integrity` resolves every active channel mapping before selecting the bounded fetch batch and has no persistent cursor, so repeated runs can revisit the first batch and starve later candidates.
4. Scoped Ruff fails on the new remediation test import order; scoped format fails on pre-existing `bot/services/ticket_invariants.py`. Full Ruff/format/mypy also retain unrelated repository debt.
5. `apply-progress.md` contains contradictory historical statements that phase 5 and E.1/E.2 remain pending after the current top-level section says 31/31 complete.
6. Model transient-error coverage injects a generic DB exception rather than a Discord verification exception, and zombie-close tests do not assert every skipped operation.

#### SUGGESTION

1. Resolve the audit vocabulary at the database/domain boundary before another verification: either migrate the persisted outcome contract to `repaired` or explicitly revise the spec and add a tested mapping.
2. Add direct runtime assertions for dry-run candidate corroboration, manual/automatic audit rows, and both listener race outcomes.
3. Add a service-owned cross-guild `repair_ticket_by_ref` regression test before accepting the narrowed result enum.

### Diagnosis

**FAIL — remediation required; do not archive or activate repair.** The implementation is conservatively fail-closed and the test/build safety net is green, but independent source inspection plus runtime probes show unresolved specification contradictions and a new cross-guild exception path. G.2/E.1/E.2 evidence remains intentionally non-authorizing.

### Canonical Verification Evidence

The evidence revision is the SHA-256 of the following exact preimage bytes: `sha256:fd4b72edea5af0c195b132e19bf64aed88d14b4a8a408800e38539bab297902c`.

```text
schema: gentle-ai.verify-evidence/v1
change: ticket-integrity-recovery
captured_on: 2026-08-17
branch: feat/ticket-integrity-recovery-pr2
base: d671a91
attempt_revision: sha256:71b7cdbea9f4b4d08b2e8ce7285f1ae239ca8f280e8131001964ae6d364a101d
attempt_work_unit: terminal-verification-rerun
attempt_outcome: running
tasks: 31/31
requirements: 11
scenarios: 44
test.full.command: uv run pytest -q
test.full.exit: 0
test.full.output: sha256:4b8d4f77e2266670920102c81b8c562fd892cedc238a281387b396e53f989637
test.change.command: uv run pytest --no-cov tests/test_ticket_integrity.py tests/test_ticket_model.py tests/test_ticket_db.py tests/test_ticket_service.py tests/test_audit_listener.py tests/test_tickets_cog.py tests/test_remediation_7_missing_scenarios.py tests/integration/test_ticket_flow.py tests/test_migrations.py -q
test.change.exit: 0
test.change.output: sha256:e70d277c1ed98a3d38242eedfa337c0572a56103418b830ef535a83105e01782
test.boundary.command: uv run pytest --no-cov tests/test_audit_listener.py tests/test_ticket_service.py tests/test_tickets_cog.py tests/test_remediation_7_missing_scenarios.py tests/integration/test_ticket_flow.py -q
test.boundary.exit: 0
test.boundary.output: sha256:cef3083f30bbcd243603cda7a0efe2dbd13dd33dd692db5defb92651c778a822
build.command: python -m py_compile bot/__main__.py
build.exit: 0
build.output: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
quality.scoped.ruff.exit: 1
quality.scoped.ruff.output: sha256:f9f89e6584fb14ab13ffe18040210793e0db94763180dd12b5af658e58c2f206
quality.scoped.format.exit: 1
quality.scoped.format.output: sha256:04ae341833a645e3ef98b81ca1fef3dcc39f068667ee8b765d3bdf45c957c10a
quality.scoped.mypy.exit: 0
quality.scoped.mypy.output: sha256:157a09cfcdfdfb5977479c5a1c08345149263a3e990a2ec976ef28aaeec9ca6e
quality.scoped.pycompile.exit: 0
quality.scoped.pycompile.output: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
quality.governance.exit: 0
quality.governance.output: sha256:d5be81bbe49b412357ba177be7fae47b32ba70b563d2a01ec6ee15df362cc215
quality.full.ruff.exit: 1
quality.full.ruff.output: sha256:e2dd2e8b6e29afdc3e6501a729f12a4b5b7b6ca07c88351740b767acaed0d7c7
quality.full.format.exit: 1
quality.full.format.output: sha256:59684c38974f2064cffcbba30cd1426d028141a1877485771ff41c73bded0f7d
quality.full.mypy.exit: 1
quality.full.mypy.output: sha256:dc2dcaf103293622bd47eb111fdb3d5a996b2189d55d964f4fa5251264b9fd43
probe.audit_contract.exit: 0
probe.audit_contract.output: sha256:0d24a170f33877c6e84eac225f59e682131b1e0d470fd6f023ddc93efd7e0874
probe.sweep_dry_run.exit: 0
probe.sweep_dry_run.output: sha256:dcd3d33505818d3545e76f77d404e6a74e256ae765937bfd5a583c160df0762e
probe.cross_guild_by_ref.exit: 0
probe.cross_guild_by_ref.output: sha256:94682ce39e7b3d6c089cd484b29bb107c4c7da198cfacaa54ed8d89b5d936c68
live.supabase.project: nebulosabot / vozkcckiybebhcclrasa / ACTIVE_HEALTHY
live.supabase.migration_015: 20260713153020 / 015_ticket_lifecycle_reliability / applied
live.supabase.ticket.closeReason: nullable
live.supabase.ticket_audit.outcomes: success|denied|error
live.discord.fetch_channel.guild: 1518709129403695154
live.discord.fetch_channel: #3=1524826303507730563 NotFound; #16=1527169412849995788 NotFound; #17=1527174095249215588 NotFound
live.E1_E2: preserved 2026-08-17 12:43 fail-closed gate_unresolved evidence; no mutation
live.G2: intentionally gate_unresolved; automatic activation not authorized
native_lines.declared: 733
native_lines.attempt_accounting: 0 (no acquire/reset/settle mutation)
process: no remediation, archive, commit, push, PR, review, or live write
```

### Harness, Cleanup, and Process Evidence

| Boundary | Evidence |
|---|---|
| Test harness | pytest unit/structural tests, mocked Discord guild/channel probes, fake Supabase DB, and direct local contract probes; no test writes to live services |
| Live reads | Supabase metadata/schema reads and authenticated Discord `fetch_channel` reads only; no ticket, audit, channel, migration, or deployment mutation |
| Temporary outputs | Exact command outputs, contract probes, and evidence preimage retained under `/tmp/opencode`; no temporary repository files were created |
| Git/VCS | No commit, push, branch, PR, review, archive, or rebase performed |
| Implementation | No remediation performed by this verifier; only the admitted report artifact is written |
| Attempt lifecycle | No acquire, reset, settle, or token mutation performed; supplied token remains running |
| Native line budget | Remediation declared at 733 native lines under the 800-line budget; native attempt accounting remains 0 because lifecycle was not mutated |
| Report admission | Candidate bytes must be admitted by `gentle-ai sdd-verify-validate --requirements 11 --scenarios 44` before replacing the OpenSpec report |

### Next Steps and Settlement Readiness

1. Keep G.2 `gate_unresolved`; do not enable automatic repair.
2. Resolve the five critical findings, especially audit vocabulary/schema alignment, dry-run candidate reporting, cross-guild result handling, and exact runtime assertions.
3. Rerun the same focused/full/static/live-read verification and produce a new evidence revision.
4. **Settlement readiness: NOT READY.** This is a validator-admitted failure only; the active attempt must remain running as requested, and archive/commit/push/PR/review are not authorized.
