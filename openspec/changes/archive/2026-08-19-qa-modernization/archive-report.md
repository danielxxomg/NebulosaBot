# Archive Report — qa-modernization

**Change**: qa-modernization
**Archived**: 2026-08-19
**Archive path**: `openspec/changes/archive/2026-08-19-qa-modernization/`
**Artifact store mode**: openspec
**Delivery strategy**: auto-chain (stacked-to-main)
**HEAD at archive**: `4a272298bef3f8d3a05382957afd73596ac0ff03` — `chore(sdd): mark Phase 7 cleanup complete — 52/52 tasks (PR1-6 + cleanup)`
**Branch**: master
**Source PR**: none (stacked-to-main — 8 commits already landed on master)

## Summary

QA modernization: migrated the Python QA toolchain to a modern, SHA-pinned, machine-enforced stack. Replaced mypy with ty 0.0.18 (strict config + baseline defer), replaced `.pre-commit-config.yaml` with `prek.toml`, replaced bandit with Ruff `S` + zizmor blocking gate, replaced `pip-audit-weekly` with `uv audit`, added PEP 735 dependency-groups, added tach 7-layer boundary enforcement (with `TicketRef`/`parse_ticket_ref` moved to `bot/core/`), ratcheted Ruff progressive cleanup (274 TRY003/EM + 97 S + 75 quality/preview → 0 findings), and cleared all mypy/bandit/pip-audit/`.pre-commit-config.yaml` remnants. 52/52 tasks complete across 6 stacked PRs (8 slices) + Phase 7 cleanup.

## Final-State Authority

This report describes the state of the change AT CLOSE. Intermediate snapshots (`apply-progress.md`, `verify-report.md`) documented the state at their write times; final numbers here reflect the terminal state after the Phase 7 marker commit `4a27229` and the post-verify objective reset.

The `verify-report` HEAD field (`4a27229`), the runtime `objective/reset` record `reset_candidate_tree` (`d67eb017…` was the pre-marker intermediate tree), and the `attempt/begin` `begin_candidate_tree` (`e462893bcae4f32175c4b6468372f0609fdeb86f`) reconcile as follows: the final verify attempt began against the current working tree `e462893`, which equals the current `HEAD^{tree}` of `4a27229`. The `finish_candidate_tree` `d67eb017` was an earlier intermediate tree captured before the Phase 7 marker commit; the `objective/reset` at 2026-08-19T23:05 re-anchored the candidate identity to the final tree. All evidence hashes below are final-state.

## Native Review Receipt Gate

`reviewGate`: **structurally ABSENT** — no `sdd-review-bindings/v1/qa-modernization` binding exists, and no review transaction in `.git/gentle-ai/review-transactions/` references `qa-modernization`. This is the "kill switch engaged, verify passed, no review ever started for this candidate" case: archive proceeds under ordinary repository policy with no receipt to read or block on. The `reviewOffer` (post-verify invitation) was declined by proceeding to archive; nothing about the decline is recorded.

Runtime ledger records reviewed (`.git/gentle-ai/sdd-runtime/v1/qa-modernization/records/`):
- `825574a1` — `attempt/begin` ordinal 8, objective `verify: final qa-modernization 52/52 PASS_WITH_WARNINGS`, begin_candidate_tree `e462893` (= current HEAD tree), max_attempts 2, max_changed_lines 200
- `28d22103` — `attempt/finish` ordinal 8, outcome `passed`, evidence_revision `sha256:18af18949a2ba5a1cd2c5a9752b6be04fd167940c8dd8a46c43aa38ba7752e21`, diagnosis "verify qa-modernization PASS_WITH_WARNINGS 53/53 71/71 2267p 85pct clean", `changed_line_budget_exceeded: true`
- `a4cfb2d4` — `objective/reset` (archive-unblock-001), reason "52/52 verify PASS_WITH_WARNINGS 2267 tests 85%+ green — unblock archive after final verify stacked slices"

## Task Completion Gate

`tasks.md`: **52/52 `[x]`, 0 unchecked** — PASS. No stale-checkbox reconciliation was required; `sdd-apply` marked all implementation tasks complete in the persisted artifact. Phases: PR1(1.1-1.7), PR2(2.1-2.8), PR3(3.1-3.5), PR4a(4a.1-4a.4), PR4b(4b.1-4b.5), PR4c(4c.1-4c.5), PR5(5.1-5.7), PR6(6.1-6.8), Phase7(7.1-7.3).

## CRITICAL / Blocker Check

`verify-report.md` verdict: **PASS_WITH_WARNINGS** — 0 blockers, 0 critical findings, 0 suggestions deferred to a later pass. No CRITICAL issues exist; archive is not blocked.

## Verification Evidence (final state)

| Gate | Result | Evidence |
|------|--------|----------|
| Verdict | PASS_WITH_WARNINGS | 0 blockers, 0 critical |
| Requirements | 53/53 compliant | |
| Scenarios | 71/71 compliant | across 7 specs |
| Tasks | 52/52 complete | |
| Tests | 2267 passed, 17 skipped, 0 failed | exit 0, hash `sha256:2791fca4a055d85e66d231ddce14d37b3176c103f019cf98b2a115885f9973de` |
| Coverage | 85.05% (threshold 75%) | 7048 stmts, 1054 missed; baseline 87.85% |
| Build | exit 0 | hash `sha256:719e316f0c58d2ecdcf7431660f2fed95899e16715939021b00b2b6da6385483` |
| evidence_revision | `sha256:18af18949a2ba5a1cd2c5a9752b6be04fd167940c8dd8a46c43aa38ba7752e21` | verify-report |
| test_command | `PYTHONASYNCIODEBUG=1 uv run pytest --cov-fail-under=75 -q` | filterwarnings error, asyncio debug on, randomly seeded |
| ruff check + format | All checks passed! / 189 files formatted | exit 0 |
| ty check bot/ tests/ | 0 errors, 346 diagnostics (warn-tier) | exit 0 |
| ty check bot/ | 0 errors, 13 diagnostics (cogs warn-tier) | exit 0 |
| tach check | All modules validated! | exit 0 |
| tach check-external | All external dependencies validated! | exit 0 |
| zizmor | 0 findings (5 suppressed) | exit 0, `--format=github` |
| uv lock --check | 75 packages, exit 0 | no mypy/bandit/pip-audit |
| uv audit | 0 blocking vulns | Pillow advisories tracked, exit 0 |
| prek run --all-files | 8/8 Passed (builtin4 + ruff2 + ty + gga) | exit 0 |

## Stacked Commits (8, afeb386 → 4a27229)

| Commit | Subject | Slice |
|--------|---------|-------|
| `afeb386` | build(deps): migrate to PEP735 dependency-groups + ty 0.0.18 | PR1 |
| `ca2ad3c` | build(typing): replace mypy with ty 0.0.18 — strict config + baseline defer | PR2 |
| `08c89fe` | build(hooks): replace pre-commit with prek — builtin + ruff + ty + gga, pre-push gates | PR3 |
| `39ee287` | refactor(lint): clear TRY003/EM101/EM102 raise message style (274 findings) | PR4a |
| `07e23af` | refactor(lint): clear Ruff security S101/S310/S311/S110 (97 findings) | PR4b |
| `036eeac` | refactor(lint): clear Ruff quality ARG/TRY300/TRY301/FURB/C901/F841 + ANN preview (PR4c) | PR4c |
| `cf31cce` | security(ci): delete bandit, SHA-pin workflows, add zizmor blocking gate (PR5) | PR5 |
| `e0681d3` | feat(tach): enforce 7-layer boundaries + move TicketRef to core (PR6) | PR6 |
| `4a27229` | chore(sdd): mark Phase 7 cleanup complete — 52/52 tasks (PR1-6 + cleanup) | Phase 7 marker |

Each slice is independently revertible. No diff to master (stacked-to-main already landed).

## Review Budget Acknowledgement

Stacked-to-main 6 PRs (8 slices) against a 1200 change-wide / 400 per-slice budget. PR4 slices exceeded the per-slice budget (`changed_line_budget_exceeded: true` in the finish record) — this was acknowledged in `apply-progress.md` as an intentional single mechanical sweep (each PR4 batch is a ratchet of a single rule family, all revertible). No blockers resulted.

## Warnings Deferred (non-blocking, recorded for future work)

1. **Deferred preview debt** — `bot/**/*.py` ignores `ANN,RUF052,RUF029,RUF069,RUF050,RUF100` (38 ANN + preview RUF). Intentional per PR4c; acknowledged tech debt for a future annotation pass. Not a violation.
2. **ty warns** — 13 warns on `bot/` (greetings decorator gaps + `ticket_repair` config possibly-undefined + view `TYPE_CHECKING` names); 346 warns on full suite (tests override widens warn-tier to preserve 177 `type:ignore`). Expected per design cogs warn-tier.
3. **`code-quality.yml` tag-pin** — retains `actions/setup-python@a26af69… # v5.6.0` tag-pinned on a separate report-only workflow. zizmor offline run did not flag it this invocation, but tag-pin diverges from the SHA-pin policy (severity low, report-only, not blocking CI QA job). Pre-existing debt, not introduced by qa-modernization slices (which SHA-pin `ci.yml`). Suggestion: SHA-pin code-quality.yml setup-python or document a zizmor exception.
4. **Pillow advisory pending** — `uv audit` exits 0 but reports Pillow PYSEC/GHSA advisories fixed in 12.3.0; Pillow 11.x remains pinned. Track the 11→12.3 bump separately before the next weekly audit (not a qa-modernization fail; audit gate would block on a future HIGH).
5. **prek managed-tool install** — currently invoked via `uv run --with prek prek`; bare `prek run` does not work for contributors. CI already uses prek via system language hooks. Suggestion: install prek as a managed tool.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| ci-workflow-file | Updated (merge) | MODIFIED triggers/matrix/coverage/asyncio-debug; REMOVED dependency-caching, blocking-QA-job, mypy/bandit/pip-audit steps; ADDED setup-uv SHA-pin, three-job structure, minimal perms, pip-audit-weekly removed. cleanup-stability delta block subsumed. |
| makefile-dx | Updated (merge) | MODIFIED type target (ty), ci target (no bandit); REMOVED security target, pip-audit audit; ADDED uv audit target, tach targets, lint-full/type-full. Preserved lint/test/cov targets. |
| pre-commit-config-file | Updated (merge) | MODIFIED ruff hooks, full-QA gate; REMOVED mypy hook, bandit hook; ADDED prek.toml single-source, builtin hooks, ty local hook, GGA preserved, pre-push uv-check/tach, priorities. cleanup-stability delta block subsumed. |
| pyproject-toml-qa-config | Updated (merge) | MODIFIED ruff config (preview ANN/PYI/PGH003, progressive suppression removal), dev deps (PEP 735); REMOVED mypy config, bandit config; ADDED ty config, uv lockfile freshness. Preserved coverage gate, warning filter, pytest-randomly. cleanup-stability delta block subsumed. |
| qa-pre-commit | Updated (merge) | MODIFIED pre-commit-runs-QA (ty, no bandit/mypy), hook ordering; REMOVED bandit-finding-blocks, mypy-error-blocks; ADDED pre-push gate, SKIP bypasses (updated hook ids). |
| tach-boundaries | **Created (NEW)** | Mechanical copy from delta. 7 requirements: seven-layer architecture, module declarations, utils→services violation resolved, strict flags, interfaces, CI/pre-push blocking, baseline captures current arch. |
| workflow-security | **Created (NEW)** | Mechanical copy from delta. 7 requirements: zizmor blocking gate, SHA-pinned actions, minimal perms, output format, code-quality master trigger, pip-audit-weekly removed. |

The 5 existing main specs had a prior `cleanup-stability` delta block (an intermediate S1 snapshot). That block is subsumed by the terminal qa-modernization state (ty fully replaces mypy, prek replaces pre-commit, tach/zizmor added, bandit/pip-audit removed) and was removed during merge — its requirements are preserved and ratcheted in the merged specs above.

## Archive Contents

- proposal.md ✅
- exploration.md ✅ (1 violation, 426 latent ruff, bandit 95 vs 97)
- design.md ✅ (7 layers, tach.toml, ty rule corrections)
- specs/ ✅ (7 specs: 5 delta + 2 new)
- tasks.md ✅ (52/52 tasks complete)
- apply-progress.md ✅ (PR1-6 + Phase 7, stacked commits)
- verify-report.md ✅ (PASS_WITH_WARNINGS, evidence sha256:18af189…)
- archive-report.md ✅ (this file)

## Mechanical Copy Contract — Readback Evidence

All archive operations used native shell commands (`cp -R`, `git mv`, `mv`); no artifact content passed through model Read/Write. Verbatim `diff -r` readback output:

**New specs (tach-boundaries, workflow-security) — mechanical `cp` + `diff -r`:**
```
diff -r openspec/changes/qa-modernization/specs/tach-boundaries/spec.md <temp>
(empty — PASS)
diff -r openspec/changes/qa-modernization/specs/workflow-security/spec.md <temp>
(empty — PASS)
```

**Change folder move — pre-move recursive snapshot + `git mv` + `diff -r`:**
```
cp -R openspec/changes/qa-modernization <snapshot_root>/source
git mv openspec/changes/qa-modernization openspec/changes/archive/2026-08-19-qa-modernization
diff -r <snapshot_root>/source openspec/changes/archive/2026-08-19-qa-modernization
(empty — PASS, exit 0)
```

All diffs empty — byte-identical archive. The `archive-report.md` is additive (did not exist in the source change folder) and excluded from the source/destination comparison.

## Remnants Cleared (Phase 7)

- No `mypy`, `bandit`, `pip-audit`, or `.pre-commit-config.yaml` remnants in active code
- `requirements.txt` `uv pip dry-run` produces no changes (Pterodactyl-safe)
- Ledger reset applied after verify (runtime `objective/reset` record)

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Source of truth (`openspec/specs/`) now reflects the modernized QA stack. Ready for the next change.

## Action Context Guard

`actionContext.mode`: not `workspace-planning` (no workspace-planning constraint present). `allowedEditRoots`: not present; archive operations stayed within the repo root. Stale untracked `openspec/changes/archive/2026-08-19-hygiene-and-qa-standardization/` left untouched (no conflict — separate untracked hygiene folder).
