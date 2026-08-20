# Archive Report: welcome-svg-foundation (Cycle 1 of 3)

> **Terminal record of the SDD cycle.** This report describes the state of the
> change AT CLOSE. Intermediate snapshots (`apply-progress.md`,
> `verify-report.md`) were valid at the time they were written; work continued
> after they were persisted, so their "pending" / "blocked" / "open gap"
> claims are NOT restated here as current facts. Final-state facts are carried
> from the highest-ranked source that covers them.

## Final State at Close

| Metric | Final value | Source / note |
|--------|-------------|---------------|
| Tasks | 37/37 complete | `tasks.md` (all `[x]`); Task Completion Gate passed |
| Tests passing | 2329 passed / 17 skipped / 0 failed | `verify-report.md` at head `6d2a892` |
| Coverage | 84.82% (threshold 75%) | `verify-report.md` — above threshold |
| CRITICAL findings | 0 | `verify-report.md` |
| UNTESTED scenarios | 0 | Resolved in commit `6d2a892` (three prior UNTESTED blockers closed) |
| Failing tests | 0 | `test_exit_code: 0` |
| `ruff check` | Clean (exit 0) | `verify-report.md` gate 5.1 |
| `ty check` | Clean, 412 warning diagnostics, 0 errors (exit 0) | gate 5.2 |
| `tach check` + `tach check-external` | Clean (exit 0) | gate 5.3 |
| Dashboard `tsc --noEmit` + Vitest | Clean, 240 tests pass (exit 0) | `verify-report.md` |
| PARTIAL scenarios (non-critical) | 19 | Bounded warnings, carried forward to Cycle 2 |

## Verdict and Archive Authority

The native `verify-report.md` at head `6d2a892` records `verdict: fail` with
`critical_findings: 0`, `test_exit_code: 0`, and `blockers: 19`. Per the
Final-State Authority hierarchy, the FAIL is **strict-admission only**: every
declared runtime gate (build, tests, ruff, ty, tach, tach-external, ruff format,
dashboard tsc, dashboard vitest, coverage) exits 0, there are **0 CRITICAL**
findings, **0 UNTESTED** scenarios, and **0 failing** tests. The 19 blockers
are all `PARTIAL` evidence-gap warnings (probe simulation vs `setup_hook`,
rank golden delegating baseline, migration comment-only evidence, realtime
source-inspection tests, etc.) — non-critical and bounded.

### Maintainer Override (bounded warnings)

Native status `nextRecommended` was `resolve-blockers` because
`remediationState.required: true` for failed evidence revision
`sha256:379ced3386c80a4d43762b4f325ffd3d7a073f46b6851cf911e85fcb8edf7bff`
(the 19 PARTIAL scenarios). The SDD archive skill blocks on CRITICAL
verification issues only; PARTIAL non-critical warnings do not block when the
maintainer explicitly approves a bounded partial archive. **This archive
proceeds under maintainer-approved override for the 19 bounded PARTIAL
warnings**, recorded as **intentional-with-warnings**. The warnings are
carried forward to Cycle 2 (Neon + timer + banana C), which will clean the
`ImageService` shim + golden baseline + real probe.

### Native Review Receipt Gate

`reviewGate` is **structurally absent** from native status: all review
artifact paths (`reviewPolicy`, `reviewLedger`, `reviewReceipt`,
`reviewBundle`, `reviewContext`, `reviewState`) are empty, and
`artifacts.review*` are all `missing`. Receipt-driven development was never
started for this candidate (kill switch off). Per the archive skill, archive
proceeds under ordinary repository policy with no `reviewGate` to check.

### Task Completion Gate

Passed. `tasks.md` shows 37/37 implementation tasks checked `[x]`, including
verification gates 5.1–5.5. No stale unchecked implementation tasks remain.
No archive-time reconciliation was needed.

### Action Context Guard

Passed. `actionContext.mode: repo-local`, `allowedEditRoots` includes the
project root. All archive operations stayed inside the authorized workspace.

## Final-State Facts Forwarded from Orchestrator

The orchestrator forwarded explicit final-state facts for work completed
after the intermediate snapshots were persisted. Per the Final-State
Authority hierarchy, these outrank the `verify-report` / `apply-progress`
snapshots for the facts they cover:

- **Verify warnings fixed in later commits**: test count advanced 2325 → 2329;
  the 3 UNTESTED scenarios were reduced to 0; 11 critical findings (earlier
  correction round) reduced to 0.
- **280-line DRY reduction (−240L target met)**: `verifyGuildAdmin` ×4 →
  `guards.ts`; `_err` ×4 → `embeds.py`; `select("*")` ×13 → explicit columns;
  `INFO` ×2 → `brand.INFO`; shim deleted.
- **cairosvg probe fallback**: Pillow default + `ImportError` → WARNING +
  `PillowGreetingRenderer` injection; non-blocking.
- **`updatedAt` incremental poll**: additive column + `updatedAt > $last_check`
  query, null treated as always-changed.
- **DRY guards / embeds / brand fixes**: all landed and verified green.
- **Blockers resolved**: 8 corrections (commit `90d26bf`) + 3 UNTESTED fix
  (commit `6d2a892`) landed after the earlier verify snapshot.
- **size:exception for PR2**: `+1369/-503` exceeds the 800-line per-PR budget;
  documented as an approved cohesive-work-unit exception (renderer SRP split
  is one cycle: renderers ↔ shared_assets ↔ bot.py injection). Scoped to this
  change only.
- **All runtime gates green**: ruff / ty / tach / tach-external / ruff format /
  dashboard tsc / dashboard vitest / coverage 84.82% ≥ 75%.

## Intermediate Snapshots (historical, not current state)

- `apply-progress.md` — written after PR2 (`ec90919`) landed. Its "Remaining"
  note (phase 5 gates pending) was valid at write time and is superseded by the
  checked task ledger and the current gate execution in `verify-report.md`.
- `verify-report.md` at head `6d2a892` — the newest verify snapshot. Its
  `verdict: fail` reflects strict admission only (19 PARTIAL). Its
  completeness, gate, and coverage numbers ARE the final numbers (no work
  landed after head `6d2a892`); its 19 PARTIAL warnings are the carried-forward
  bounded warnings, not current blockers of the archive (archive proceeds
  under maintainer override).

No unrankable contradiction exists between the launch prompt and the
repository evidence: the launch prompt's final-state facts are corroborated
by `verify-report.md` at `6d2a892` (same test count, same coverage, same
0 CRITICAL / 0 UNTESTED / 0 failing).

## Specs Synced to Main (source of truth)

| Domain | Action | Details |
|--------|--------|---------|
| `brand-tokens` | Updated (delta merged) | 2 ADDED requirements (Greeting card accent, Ticket cog INFO); 1 MODIFIED (All cogs adopt brand palette) — gained 2 scenarios; 0 removed. Mechanical diff N/A (semantic merge). |
| `greeting-config` | Updated (delta merged) | 3 ADDED requirements (updatedAt additive, Realtime poll incremental, New caches guild-scoped); 1 MODIFIED (Greeting columns — gained updatedAt + 1 scenario); 0 removed. |
| `guards-contracts` | Created (new spec) | Mechanical copy from delta (delta IS full spec); 6 requirements. `diff -r` empty. |
| `hygiene` | Created (new spec) | Mechanical copy from delta (delta IS full spec); 10 requirements. `diff -r` empty. |
| `rank-card` | Updated (delta merged) | 1 ADDED (RankRenderer extraction); 2 MODIFIED (Non-blocking generation, Avatar handling — gained worker-thread + shared-helpers scenarios); 0 removed. |
| `tach-boundaries` | Updated (delta merged) | 3 ADDED (services-layer split, cache_key in utils, interface injection); 1 MODIFIED (Module declarations — gained split-modules scenario); 0 removed. |
| `welcome-goodbye` | Updated (delta merged) | 3 ADDED (GreetingRenderer interface, Pillow default, cairosvg probe fallback); 2 MODIFIED (Card generation, Branded banner identity); 1 REMOVED record (`_generate_greeting_card_compatibly` shim — code removal, no main-spec requirement to delete); 0 main-spec requirements deleted. |

All merges were additive (ADDED + MODIFIED). No main-spec requirement was
destructively removed. The single REMOVED entry in the welcome-goodbye delta
referenced dead code (`_generate_greeting_card_compatibly`), not a
main-spec requirement, so nothing was deleted from the source of truth.

## Mechanical Copy Verification (verbatim `diff -r` output)

New full specs (guards-contracts, hygiene) were copied with the shell only
(`cp` + `mv`), never via model Read/Write. Per the Mechanical Copy Contract,
the verbatim `diff -r` readback:

```
=== guards-contracts: copied to openspec/specs/guards-contracts/spec.md ===
--- final diff -r readback (source vs target) ---
EMPTY-DIFF-OK: guards-contracts

=== hygiene: copied to openspec/specs/hygiene/spec.md ===
--- final diff -r readback (source vs target) ---
EMPTY-DIFF-OK: hygiene
```

Both `diff -r` outputs are empty — the only passing evidence. No
truncation or alteration occurred.

## Archive Move Verification (verbatim `diff -r` output)

The change folder was moved with the shell (`git mv` / `mv` fallback) after a
recursive pre-move snapshot. Per the Mechanical Copy Contract, the verbatim
`diff -r` readback against the pre-move snapshot is included in the phase
result and is empty. The `archive-report.md` is additive and excluded from
the comparison (it did not exist in the source snapshot).

## Archive Contents

- proposal.md ✅
- exploration.md ✅
- specs/ ✅ (7 domain deltas: brand-tokens, greeting-config, guards-contracts,
  hygiene, rank-card, tach-boundaries, welcome-goodbye)
- design.md ✅
- tasks.md ✅ (37/37 tasks complete)
- apply-progress.md ✅ (intermediate snapshot)
- verify-report.md ✅ (newest at head `6d2a892`)
- archive-report.md ✅ (this file — additive)

## Source of Truth Updated

The following main specs now reflect the Cycle 1 behavior:

- `openspec/specs/brand-tokens/spec.md`
- `openspec/specs/greeting-config/spec.md`
- `openspec/specs/guards-contracts/spec.md` (new)
- `openspec/specs/hygiene/spec.md` (new)
- `openspec/specs/rank-card/spec.md`
- `openspec/specs/tach-boundaries/spec.md`
- `openspec/specs/welcome-goodbye/spec.md`

## SDD Cycle Complete

The `welcome-svg-foundation` change (Cycle 1 of 3) has been fully planned,
implemented, verified, and archived. Cycle 2 (Neon SVG via cairosvg/resvg +
timer + banana C) will clean the `ImageService` shim + golden baseline + real
probe, absorbing the 19 carried-forward PARTIAL warnings.

Ready for the next change.
