# Archive Report: greeting-templates — Per-Kind Greeting Templates

**Change**: `greeting-templates`
**Archived to**: `openspec/changes/archive/2026-09-03-greeting-templates/`
**Archive date**: 2026-09-03 (ISO, UTC; today per close instruction)
**Source change path (pre-archive)**: `openspec/changes/greeting-templates/`
**Artifact store**: `openspec` (filesystem source of truth) + `engram` hybrid mirror (`nebulosabot` — apply-progress rev4 + verify-report + this archive-report)
**Execution mode**: `sdd-archive` mechanical — no `gentle-ai` ledger mutation; no `sdd-attempt` operations; this agent performs spec sync + archive move + report + commit only
**Status**: ✅ Archived — SDD cycle complete (propose → 4 delta specs + 1 no-delta decision → design → tasks 12/12 → apply S1 + S2 `0bf701e` + S3 `7b7d27c` + remediation R1 `946b1ef` + Rev2 `7d043ed` → verify Rev3 PASS WITH WARNINGS → archive with 4-domain spec sync)

## Executive Summary

`greeting-templates` ships four code-owned Pillow greeting templates (`default`, `gaming_neon`, `sunset_wave`, `minimal_light`) with per-kind `welcome_template_id`/`goodbye_template_id` selection, migration `030` (idempotent `ADD COLUMN IF NOT EXISTS` + `COALESCE` backfill, one-cycle `themeId` dual-write), persistent `StringSelect` pickers in both `/setup` Welcome/Goodbye modules, resolved-template preview, and 16 `t()` locale keys in both locales — with `bot/cogs/greetings.py` byte-identical to `f811720` throughout. Rev3 independent verification returned **PASS WITH WARNINGS** (11/11 requirements, 51/51 scenarios; Rev1 3 CRITICALs + Rev2 3 CRITICALs all closed with fresh evidence including fault-injection falsifiability proofs). Fresh ledger: **175 files / 62,384 lines / 3,063 collected / 3,044 passed / 19 skipped dual-seed / 81.78% seed-42 coverage**; all gates green (`make ci`, `ty`, `ruff check`/`format`, `vulture`, `tach`, i18n, migration suite twice). Archive syncs 3 ADDED + 1 MODIFIED into `greeting-config`, 2 ADDED + 2 MODIFIED into `welcome-goodbye`, 1 ADDED into `i18n-system`, 2 ADDED into `setup-panel` — all wrapped `BEGIN/END DELTA: greeting-templates` per the `cov-headroom-guard` / `tests-slim-fase-2` mechanics. `brand-tokens` is a no-token decision (README travels with the archive; no canonical change).

## Final-State Authority

This report is the terminal record at close (2026-09-03) and outranks intermediate snapshots per hierarchy:

1. **Persisted `tasks.md`** (completion visibility) — `12/12` checked, zero unchecked, no reconciliation needed. `sdd-apply` owns completion; `sdd-archive` validates.
2. **Explicit final-state facts in orchestrator launch prompt** (rank 2) — verdict Rev3 PASS WITH WARNINGS, fresh ledger 175/62,384/3,063/cov 81.78% seed42, 3,044 passed / 19 skipped dual-seed, all gates green, 4 standing non-blocking warnings, tasks.md all S1–S3 + C1–C3 checked with S3 AC amended to `--no-cov` (commit `7d043ed`, maintainer-approved), `greetings.py` byte-identical to `f811720`. Supersedes any stale snapshot claim.
3. **`verify-report.md` + `apply-progress`** — intermediate snapshots valid only at their time. `verify-report.md` in this archive is the Rev3 canonical report (`evidence_revision sha256:a53d2efc…`, `verdict: pass_with_warnings`, `blockers: 0`, `critical_findings: 0`, `requirements: 11/11`, `scenarios: 51/51`). `apply-progress` is `missing` in native `sdd-status` (openspec store) but lives in Engram (`sdd/greeting-templates/apply-progress` rev4, obs `#5080`); no contradiction.

**Applied ranking:** no contradictions between sources required resolution. The launch prompt's final-state facts corroborate the archived `verify-report.md` and the git log (`0bf701e`, `7b7d27c`, `946b1ef`, `7d043ed`). Native `sdd-status` at archive time reported `apply: all_done / verify: all_done / archive: ready / tasks 12/12 / nextRecommended: archive` with zero blocked reasons and `actionContext.mode: repo-local` (no workspace-planning guard trip).

## Task Completion Gate

- **Gate result**: PASS — no reconciliation, no repair. `grep "^- \[ \]"` → `0`; `grep "^- \[x\]"` → `12`.
- **Persisted artifact**: `openspec/changes/archive/2026-09-03-greeting-templates/tasks.md` (moved mechanically, unmodified)
  - Slice S1 Registry — S1.1/S1.2/S1.3 — `3/3`
  - Slice S2 Persistence — S2.1/S2.2/S2.3 — `3/3`
  - Slice S3 Pickers+i18n — S3.1/S3.2/S3.3 — `3/3` (S3 AC amended to `--no-cov` house pattern, commit `7d043ed`, maintainer-approved)
  - Work-Unit Commits — C1/C2 (`0bf701e`)/C3 (`7b7d27c`) — `3/3`
- **Strict-vs-OpenSpec policy**: 0 CRITICAL in Rev3 verify-report, 0 unchecked tasks, all artifacts present (proposal, 5 spec dirs, design, tasks, verify-report). No partial-archive override needed.
- **tasks.md archive-date annotation**: deliberately NOT applied to the archived file — the post-move `diff -r` byte-identity proof forbids mutating archived artifacts; the archive date is recorded here (2026-09-03) instead.

## Specs Synced — Delta → Source of Truth

All four target canonical specs existed, so deltas merged in place (MODIFIED replaced section-for-section, ADDED appended), each block wrapped `<!-- BEGIN DELTA: greeting-templates ({domain}) -->` / `<!-- END DELTA: ... -->`. Inserted bodies asserted byte-identical to the delta slices by the merge script (`/tmp/opencode/gt-archive-merge.py`, repo-external tool). Non-delta requirements preserved; the two pre-existing delta blocks in `greeting-config` (`welcome-neon-timer-banana`, `ops-zero-lite`) and `welcome-goodbye` (same) untouched.

| Domain | Action | Delta type | Requirements / Scenarios | Sync method | Verification |
|--------|--------|------------|--------------------------|-------------|--------------|
| `greeting-config` | **Updated** | 3 ADDED + 1 MODIFIED (`Greeting columns`) | 4 req / 18 scen (migration 030, dual-write chain, CDC unchanged, per-kind columns) | MODIFIED replaced in place wrapped ×1; ADDED appended wrapped ×1 | `git diff --stat` part of 4-file `+372/-40`; `BEGIN DELTA` ×2; req count `24→27`; removals confined to replaced `Greeting columns` section |
| `welcome-goodbye` | **Updated** | 2 ADDED + 2 MODIFIED (`GreetingRenderer interface`, `Pillow is the default renderer`) | 4 req / 17 scen (registry, selection policy, interface, Pillow-4) | Both MODIFIED replaced in place under one combined wrapper; ADDED appended wrapped ×1 | `BEGIN DELTA` ×2; req count `11→…` (+2 net, 2 replaced); removals confirmed confined to the two replaced sections via `grep "^-"` |
| `i18n-system` | **Updated** | 1 ADDED (16 keys) | 1 req / 6 scen | Appended wrapped ×1 | Pure append — zero `-` lines in diff |
| `setup-panel` | **Updated** | 2 ADDED (pickers, preview) | 2 req / 10 scen | Appended wrapped ×1 | Pure append — zero `-` lines in diff |
| `brand-tokens` | **No change** | No-delta decision | 0 req / 0 scen | None — `specs/brand-tokens/README.md` travels with the archive as historical context (cov-headroom-guard no-op pattern) | Canonical `brand-tokens/spec.md` untouched; hex-guard + token reuse verified by `test_brand_no_hex` per verify-report |

**Merge preservation:** every non-delta requirement in all four canonical specs preserved byte-identical (verified: `welcome-goodbye` removals limited to the two replaced MODIFIED sections; `i18n-system`/`setup-panel` pure appends; `greeting-config` removals limited to the replaced `Greeting columns` section). All other 70 specs untouched.

## Verification Lineage (Final-State) — Rev3 PASS WITH WARNINGS

### Admission envelope — canonical Rev3 (archived verify-report.md front-matter)

Source: `openspec/changes/archive/2026-09-03-greeting-templates/verify-report.md` front-matter YAML (schema `gentle-ai.verify-result/v1`), `evidence_revision sha256:a53d2efcf7019bc75726b158cb702483a88ce0f321862d23d273f5ab4e7c0ae2`. Admitted by native `sdd-verify-validate` (`pass_with_warnings`, report sha256 `b6e29ef2…`); native dispatcher reports `verify: all_done / archive: ready`.

```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:a53d2efcf7019bc75726b158cb702483a88ce0f321862d23d273f5ab4e7c0ae2
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 11/11
scenarios: 51/51
test_command: "uv run pytest -q --cov=bot --cov-fail-under=80 --randomly-seed=42"
test_exit_code: 0
test_output_hash: sha256:f928a40422a322c92d36600740bf6a12633dfd88f8b99f8363400b704c9b6603
build_command: "make ci"
build_exit_code: 0
build_output_hash: sha256:2d12ce61562bc9315226e85ef5054d2aee79d3b644a3c32524b8ae0ce71670dc
```

**Verdict in prose:** **PASS WITH WARNINGS** — 11/11 requirements, 51/51 scenarios, 0 CRITICAL. All three Rev1 CRITICALs and all three Rev2 CRITICALs closed with fresh evidence (Rev2 closures independently falsifiable via fault-injection probes: opposite-kind corruption `gaming_neon` vs captured `minimal_light` fails the repaired assertion; plain-`View` impostor registrations fail the real-`setup_hook` proof).

### Fresh suite ledger + gates (final-state facts, corroborated by verify-report §§ Build/Quality)

| Metric | Value |
|--------|-------|
| Python test files / lines | 175 / 62,384 |
| Collected / passed / skipped | 3,063 / 3,044 / 19 (dual-seed: 42 `--cov` + 777 `--no-cov`) |
| Coverage (seed 42) | 81.78% (threshold 80%) |
| Build | `make ci` exit 0 (`ty`, `ruff check`, `ruff format --check`, `vulture`, `tach` internal+external all 0) |
| Focused setup gate | `uv run pytest -k setup_module -q --no-cov` → 55 passed |
| Migration suite | `tests/test_migrations.py` 65/65 twice |
| i18n coverage | 17 passed |
| Invariant | `git diff --exit-code f811720..HEAD -- bot/cogs/greetings.py` empty (re-verified at archive time: `GREETINGS-IDENTICAL`) |

### The 4 standing non-blocking WARNINGs (registered, not fixed — carried as final state)

1. **Suite governance ceiling** — 62,384 lines vs permanent `<61,480` ceiling. The change's approved forecast adds ~1,065 test lines; governance accounting belongs to a future `tests-slim` cleanup slice.
2. **Weighted changed-file coverage 73.79%** — below the 80 changed-file bar (`welcome.py` 59.01%, `setup_panel.py` 62.08%, `goodbye.py` 66.95%, `live_catalog.py` 71.51%); total project coverage remains 81.78% and passes the configured gate.
3. **Migration 030 structural-only proof** — guarded DDL + `COALESCE` + twice-passed Python suite, but no live Supabase apply in this env; applies at deploy.
4. **Weak retained-controls assertion** — `tests/test_setup_panel_pickers.py:193-198` checks only `view is not None`; stronger adjacent tests (both picker IDs, real setup-hook registration) cover the scenarios, so compliance is unaffected.

## Mechanical Copy Contract — Verbatim `diff -r` Readback

**Spec sync (MODIFIED merge path — scripted merge, not mechanical `cp`):** `diff -r` for the `cp` path is N/A per precedent; verification is the `git diff` evidence above (4 files `+372/-40`, byte-identical inserted bodies asserted by the merge script, removals confined to replaced MODIFIED sections, two domains pure-append).

**Archive move (MANDATORY `diff -r`):** one shell transaction per the skill block — recursive snapshot `cp -R` before either move attempt, `git mv` (succeeded: tracked `tasks.md` staged as rename; untracked siblings moved physically along), source-gone guard, then mandatory readback.

Verbatim `diff -r "$snapshot_root/source" "$destination"` output:

```
(empty — no differences)
```

`diff_status=0`, source `openspec/changes/greeting-templates` gone, destination contains `proposal.md`, `design.md`, `specs/` (brand-tokens/README + 4 delta specs), `tasks.md` (12/12), `verify-report.md` (this `archive-report.md` additive-only and excluded per contract — written after the readback). Active `openspec/changes/` now contains only `archive/`. Any non-empty output would have FAILED the phase; a skipped `diff -r` also FAILS — neither occurred.

## Archive Verification Checklist

- [x] Main specs updated correctly — 4 files, 7 wrapped blocks, non-delta content preserved
- [x] Change folder moved to `openspec/changes/archive/2026-09-03-greeting-templates/` — source absent
- [x] Archive contains all artifacts: `proposal.md` ✅, `specs/` (5 dirs) ✅, `design.md` ✅, `tasks.md` ✅ (12/12), `verify-report.md` ✅, `archive-report.md` ✅ (additive)
- [x] Archived `tasks.md` has no unchecked implementation tasks (`grep "^- \[ \]"` → `0`) — no reconciliation needed or performed
- [x] Active `openspec/changes/` no longer contains `greeting-templates` — only `archive/`
- [x] Verbatim `diff -r` readback included above and is empty (no differences) — byte-identity proven
- [x] `verify-report.md` verdict PASS WITH WARNINGS, 0 CRITICAL — no archive block
- [x] `bot/cogs/greetings.py` invariant re-verified at archive time (empty diff `f811720..HEAD`)

## Risks After Archive

All four warnings above are non-blocking and tracked; no CRITICAL remains. Notes for future work: (1) a `tests-slim` governance slice must reclaim the ~904-line ceiling overrun plus this change's ~1,065-line forecast; (2) execute migration `030` twice against an isolated PostgreSQL/Supabase test database before production rollout; (3) strengthen the retained-controls test to assert the selected picker ID in `view.children`; (4) S2/S3/remediation local commits ride stacked delivery per orchestrator (this archive commit covers `openspec/` only). The prior `2026-09-02-tests-slim-fase-2` archive folder is absent from the working tree and untracked — unrelated to this change; flagged for orchestrator awareness, not resolved here.

## Traceability

- **Commits**: S2 `0bf701e` (per-kind columns + dual-write) → S3 `7b7d27c` (pickers + 16 keys) → R1 `946b1ef` (panel wiring + resolved preview) → Rev2 `7d043ed` (test-integrity + `--no-cov` AC amendment); S1 merged earlier (`e20c515` via #89, base `f811720`)
- **Verify report**: `openspec/changes/archive/2026-09-03-greeting-templates/verify-report.md` — `evidence_revision sha256:a53d2efc…`, `verdict: pass_with_warnings`, `blockers: 0`, `critical_findings: 0`, `requirements: 11/11`, `scenarios: 51/51`
- **Tasks**: `…/archive/2026-09-03-greeting-templates/tasks.md` — 12/12 `[x]`
- **Spec sync**: `openspec/specs/{greeting-config,i18n-system,setup-panel,welcome-goodbye}/spec.md` — 7 wrapped `BEGIN/END DELTA: greeting-templates` blocks, 8 ADDED + 3 MODIFIED requirements, 51 scenarios
- **Archive location**: `openspec/changes/archive/2026-09-03-greeting-templates/` — `git mv` + empty `diff -r`
- **Engram observations read**: `#5080` (`sdd/greeting-templates/apply-progress` rev4, cumulative S1+S2+S3+R1+Rev2) · `#5083` (`sdd/greeting-templates/verify-report` Rev3) · `#5077` (`sdd/tests-slim-fase-2/archive-report`, mechanics precedent)
- **Engram mirror**: `sdd/greeting-templates/archive-report` (this report, `project: nebulosabot`, `capture_prompt: false`)
- **Native status at close**: `apply: all_done / verify: all_done / archive: ready / nextRecommended: archive`, `actionContext.mode: repo-local`

## Delivery — Next Recommended

**Next**: `delivery` — PR sequencing per orchestrator. This archive stages ONLY `openspec/` paths (deleted-from-changes + added-to-archive + 4 canonical specs) in one commit `docs(sdd): archive greeting-templates — merge delta specs`, NO push. Local implementation commits S2/S3/remediations ride stacked delivery per orchestrator (S1 already merged via #89).

## Skill Resolution

- `/home/danielxxomg/.config/opencode/skills/sdd-archive/SKILL.md` (dedicated `sdd-archive` executor role; Sections B/C/D via shared-contract references resolved through native `sdd-status` + precedent #5077 mechanics: Python merge with byte-identity asserts, `mv`/`git mv` + snapshot + `diff -r`, additive archive-report)
