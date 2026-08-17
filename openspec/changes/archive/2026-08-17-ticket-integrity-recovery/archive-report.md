# Archive Report: ticket-integrity-recovery

**Archived**: 2026-08-17
**Mode**: openspec, Strict TDD, stacked-to-main
**Status**: success — PASS WITH WARNINGS, 31/31 tasks, 11/11 requirements, 44/44 scenarios
**Evidence revision**: `sha256:cd1a49b262d2adc045901a95631f60a22df8a5d1a5be11655cad517eb4080f0d`
**Candidate**: `65dfca626a07937f3e97cc360545afa2c2aea903` (HEAD), base `d671a91` (product-artifact-audit archived)
**Branch**: `feat/ticket-integrity-recovery-pr2`
**Verify token**: `sha256:8c44fd92b54b6540fa8aff0cfe0cc9408d16e645c0eab8462ba7274506497f6c` (terminal-verification-final2, max 1500, settled passed, validator-admitted)
**Archived to**: `openspec/changes/archive/2026-08-17-ticket-integrity-recovery/`

## Summary

Ticket lifecycle integrity and zombie-ticket repair are restored. Migration 015 parity is tracked and verified, `IntegrityEvidence`/`RepairResult` give bounded, auditable, idempotent repair, the conditional `transition_ticket_to_closed` is the sole mutation, and three evidence-gated entry points — authoritative `on_guild_channel_delete`, startup/hourly bounded sweeps, and moderator manual fallback — all route through the shared `handle_channel_delete` / `sweep_integrity` / `repair_ticket_*` path. G.2 remains intentionally `gate_unresolved` until migration 017 rollout, so automatic repair stays fail-closed; live verification on 2026-08-17 12:43 (guild 1518709129403695154, 5× sweep denied/gate_unresolved, channel-delete apelaciones-d-0020 denied) corroborates the closed gate without mutation. 1761/3 tests pass, build passes, and the 44-scenario runtime matrix is fully compliant.

Archive executed mechanically: 3 delta specs merged into main specs (1 MODIFIED + 7 ADDED requirements, 33 scenarios), change folder moved with shell-only `git mv` + `diff -r` readback (empty diff), no re-verify, re-apply, commit, push, PR, or review performed.

## Task Completion Gate

| Metric | Value |
|--------|-------|
| Tasks total | 31 |
| Tasks complete | 31 |
| Tasks incomplete | 0 |
| Unchecked boxes | 0 |
| Gate | PASSED |

All 31 implementation + evidence tasks are checked per persisted `tasks.md` — 0 pending. No exceptional reconciliation was required; the orchestrator's final-state handoff (31/31 all_done) matches the persisted artifact.

Gate authority: persisted `tasks.md` (rank 2) corroborated by `apply-progress.md` final section (PR5 + E.1/E.2 live corroboration) and `verify-report.md` identity table (31/31).

## Native Review Receipt Gate

- `reviewGate` **absent** — no terminal receipt governs this candidate.
- Structured status reports `archive ready, nextRecommended archive, blocked []` with no `reviewGate` key present.
- Per the archive skill's Native Review Receipt Gate: `reviewGate` absent → archive proceeds under ordinary repository policy; there is no `disabled/unmanaged` value to check and no receipt to read.
- Zero `sdd/{change}/review/{transaction,ledger,receipt,gate-context}` topics exist for this candidate; none were read.
- No remediation, commit, push, PR, or review was launched by archive.

## Delta Specs Synced

| Domain | Action | Requirements | Scenarios | Notes |
|--------|--------|-------------|-----------|-------|
| `database-layer` | Updated (ADDED) | 2 added — Migration 015 on-disk parity tracking; Deployment/migration preflight evidence (G.2 gate) | 7 | Wrapped `<!-- BEGIN DELTA: ticket-integrity-recovery (database-layer) -->` |
| `ticket-model` | Updated (ADDED) | 2 added — Integrity evidence dataclass; Repair result dataclass | 8 | Wrapped `<!-- BEGIN DELTA: ticket-integrity-recovery (ticket-model) -->` |
| `ticket-service` | Updated (MODIFIED+ADDED) | 1 modified — Ticket close (close_reason + zombie + ValueError); 6 added — Authoritative channel-delete repair, Evidence-gated reconciliation sweep, Manual repair fallback, Repair idempotency/bounds/auditability, False-positive safe channel verification, Rollback/no-op behavior | 26 | MODIFIED replaced the Ticket close block; ADDED appended after product-artifact-audit marker |
| **Total** | — | **1 MODIFIED + 8 ADDED (9 effective)** | **41 (delta) → 44 runtime scenarios** | — |

Sync method: direct file merge preserving all pre-existing requirements (both base and `product-artifact-audit` deltas). No REMOVED/RENAMED deltas. No new domain was created. Existing requirements were preserved — verified by post-sync counts (database-layer 9 reqs, ticket-model 6 reqs, ticket-service 26 reqs).

Main spec verification (post-sync):
- `openspec/specs/database-layer/spec.md` — contains `Migration 015 on-disk parity tracking` and `Deployment/migration preflight evidence (G.2 gate)`
- `openspec/specs/ticket-model/spec.md` — contains `Integrity evidence dataclass` and `Repair result dataclass`
- `openspec/specs/ticket-service/spec.md` — contains `close_reason: str | None`, `Authoritative channel-delete repair`, `Evidence-gated reconciliation sweep`, `Manual repair fallback`, `Repair idempotency, bounds, and auditability`, `False-positive safe channel verification`, `Rollback and no-op behavior`

## Archive Contents

| Artifact | Present | Notes |
|----------|---------|-------|
| `proposal.md` | ✅ | Intent: restore lifecycle integrity + zombie repair; scope: 015 parity, evidence/preflight, bounded repair contracts, hybrid entry points; rollback: disable gates, retain reports |
| `specs/database-layer/spec.md` | ✅ | 2 ADDED requirements (7 scenarios) |
| `specs/ticket-model/spec.md` | ✅ | 2 ADDED requirements (8 scenarios) |
| `specs/ticket-service/spec.md` | ✅ | 1 MODIFIED + 6 ADDED requirements (26 scenarios) |
| `design.md` | ✅ | Authoritative event > sweep, conditional close, bounded evidence-gated sweeps, mod fallback, migration rollout |
| `tasks.md` | ✅ | 31/31 complete; PR1 (015+preflight) → PR2 (conditional DB+repair) → PR3 (channel-delete authoritative) → PR4 (sweeps/manual bounded) → PR5 (idempotency/audit+integration) + E.1/E.2/E.3 |
| `apply-progress.md` | ✅ | PR1 74 pass → PR2 163 pass → PR3 25+12 pass → PR4 14+1740 pass → PR5 481+1744 pass + Remediation 8+5+6 facets; TDD RED→GREEN per phase |
| `verify-report.md` | ✅ | PASS WITH WARNINGS, 11/11, 44/44, 1761/3, 88.47% coverage, validator-admitted |
| `archive-report.md` | ✅ | This report (additive-only, excluded from move diff) |

Archived to: `openspec/changes/archive/2026-08-17-ticket-integrity-recovery/`

Active changes directory: `openspec/changes/ticket-integrity-recovery/` no longer exists (verified before `diff -r`).

## Verification Summary (terminal verification, final state)

Per `verify-report.md` now at `openspec/changes/archive/2026-08-17-ticket-integrity-recovery/verify-report.md`:

- **Schema**: `gentle-ai.verify-result/v1`, `evidence_revision: sha256:cd1a49b262d2adc045901a95631f60a22df8a5d1a5be11655cad517eb4080f0d`
- **Verdict**: `pass_with_warnings` — `blockers: 0`, `critical_findings: 0`
- **Requirements / Scenarios**: **11/11**, **44/44** — all PASS with WARNINGS, 0 failing, 0 untested
- **Tests**:
  - Focused requested suites: 313 passed (`sha256:7adc1c…`)
  - Supplemental DB + cog: 49 + 136 passed
  - Complete change suite: **498 passed** (`sha256:9037532b…`)
  - Full configured suite: **1761 passed, 3 skipped**, 88.47% coverage (`sha256:8288b4b…`)
  - Build: `python -m py_compile bot/__main__.py` → exit 0 (`sha256:e3b0c44…`)
- **Changed production-file coverage**: 87% aggregate (threshold 75%) — 8 files 83–100%
- **Quality** (scoped, change paths only):
  - Ruff check: 2 current E501 findings at `tests/integration/test_ticket_flow.py:867` (132 chars) and `tests/test_verify_remediation_5_findings.py:87` (142 chars) — not remediated, non-blocking
  - Ruff format: 1 file would reformat (`tests/integration/test_ticket_flow.py`)
  - Mypy (8 changed source files): Success, no issues
  - Governance: 6 passed, `governance_guard.py` pass
- **TDD**: 4/6 fully confirmed, 2 warnings on historical chronology/evidence bookkeeping
- **Live read-only corroboration** (no mutation):
  - Supabase: 015 applied, 017 absent (tracked 36 lines, not applied), `ticket.closeReason` nullable, `ticket_audit.outcome` still `success|denied|error` (no `repaired`)
  - Discord: 3 channels NotFound corroboration
  - E.1/E.2 preserved: 2026-08-17 12:43 startup/sweeps 5× denied/gate_unresolved + channel-delete apelaciones-d-0020 denied + tickets #20/#99999 manual corroboration + 5-ticket sweep

### Live Evidence (preserved, not mutation-authorized)

| Signal | State | Meaning |
|--------|-------|---------|
| G.2 gate | `gate_unresolved` fail-closed by design | No automatic repair activation; manual `repaired` writes not live-rollout-ready |
| Migration 017 `ticket_audit.repaired` | Tracked on disk, not applied live | Audit vocabulary widening pending authorized rollout |
| Sweeps | Bounded batch 50, 250-candidate cap, 429 backoff | Probes are bounded but discovery still scans mappings before batch selection — no persistent cursor |
| Tests | 1761/3, build green | Full suite above threshold; no TDD violation |

### Warnings (non-blocking, intentionally preserved)

Per `verify-report.md` Issues Found (WARNING 1–6) + Suggestions, and the orchestrator's FINAL-STATE HANDOFF:

1. **Live migration 017 not applied** — `ticket_audit.outcome` still excludes `repaired`; automatic repair correctly remains `gate_unresolved`. Do NOT claim activation.
2. **2 current E501 test lines** — `test_ticket_flow.py:867`, `test_verify_remediation_5_findings.py:87` — intentionally not fixed in verify/apply; archive does not fix tests.
3. **2 assertion-quality observations** — zombie dual-skip local mocks not injected; no-op audit helper `idx` mismatch — non-blocking, source-backed behavior still verified.
4. **Historical apply-progress contradictions** — older paragraphs still say phase 5/E.1/E.2 pending; final top-level says 31/31 — per Final-State Authority, later 31/31 + live corroboration win.
5. **Sweep cursor starvation risk** — bounded probes but no persistent cursor; 26 inherited format/mypy candidates remain (full Ruff 32, full mypy 27 inherited).
6. **400 fixed to warning, 1744→1761/3 growth** — final full-suite count is 1761/3 per verify-report.

No CRITICAL issues remain; archive is not blocked.

## Final-State Authority Applied

- **Rank 1 (native review)**: absent → not applicable; no receipt governs.
- **Rank 2 (persisted tasks)**: 31/31 checked, 0 unchecked — authoritative for completion.
- **Rank 3 (orchestrator final-state facts)**: "31/31 tasks complete", "Warnings fixed in later commits already reflected in 31/31", "Remaining warnings intentionally preserved (017 not applied, 2 E501, 26 inherited, sweep cursor)", "All work units PR3/PR4/PR5 + verifications closed and evidenced" — these outrank stale snapshots and explain why verify-report still lists prior contradictory paragraphs.
- **Rank 4 (intermediate snapshots)**: `verify-report.md` and `apply-progress.md` historical pending claims (phase 5/E.1/E.2 pending) are stale relative to rank 2/3; carried as history, not current state.

Contradictions recorded: `apply-progress.md` historical pending vs final 31/31 — resolved in favor of final 31/31 per hierarchy; `verify-report.md` line-count 1744 vs final 1761 — resolved in favor of final verify-report 1761.

## Mechanical Copy Contract Evidence

### Spec sync (3 domains — 1 MODIFIED + 8 ADDED)

- Method: direct file edit preserving all prior requirements; database-layer and ticket-model delta blocks wrapped with `<!-- BEGIN DELTA: ticket-integrity-recovery -->` markers; ticket-service MODIFIED block replaced in place and ADDED block appended after `product-artifact-audit` marker — no model Read→Write blob copy for the archive move.
- Post-sync verification counts (see Delta Specs Synced).

### Archive move

```sh
snapshot_root="$(mktemp -d "${TMPDIR:-/tmp}/sdd-archive.XXXXXX")"
cp -R "openspec/changes/ticket-integrity-recovery" "$snapshot_root/source"
mkdir -p openspec/changes/archive
git mv openspec/changes/ticket-integrity-recovery openspec/changes/archive/2026-08-17-ticket-integrity-recovery
# source must be gone before readback
diff -r "$snapshot_root/source" "openspec/changes/archive/2026-08-17-ticket-integrity-recovery"
```

**Verbatim `diff -r` output**: *(empty — no differences)*

Mechanical copy verified: snapshot 21 entries (6 artifacts + 3 delta specs) byte-identical after move.

## Risks and Follow-Up

| Risk | Status | Action |
|------|--------|--------|
| G.2 intentionally unresolved | Intentional fail-closed | Do NOT activate repair, apply migration 017 live, or mutate live tickets/channels until authorized rollout |
| Migration 017 rollout | Tracked, not applied | Apply only through authorized rollout, then re-read `ticket_audit` constraint and persist fresh resolved G.2 evidence |
| 2 E501 + format candidate | Non-blocking test style | Clean in a separate work unit |
| Sweep cursor starvation | Operational | Add persistent cursor if large-guild scans become expensive |
| 26 inherited repo quality findings | Inherited | Outside change scope |

No backup/restore, CI quality delta, or greeting/dashboard work was introduced.

## SDD Cycle Complete

The `ticket-integrity-recovery` change has been fully planned, implemented, verified (PASS WITH WARNINGS, 11/11, 44/44, 1761/3), synced to the source of truth, and archived. The repair lifecycle is closed and fail-closed until migration 017 rollout.

## Source of Truth Updated

- `openspec/specs/database-layer/spec.md` — now reflects Migration 015 parity + G.2 preflight (recovery delta)
- `openspec/specs/ticket-model/spec.md` — now reflects IntegrityEvidence + RepairResult (recovery delta)
- `openspec/specs/ticket-service/spec.md` — now reflects conditional close + 6 integrity repair requirements (recovery delta)

All three specs preserve the prior `product-artifact-audit` deltas and base requirements.
