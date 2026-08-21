# Archive Report — welcome-neon-timer-banana (Cycle 2 of 3)

**Archived**: 2026-08-21
**Change**: welcome-neon-timer-banana
**Cycle**: 2 of 3 (welcome-svg-foundation → **welcome-neon-timer-banana** → welcome-ocio-assets)
**Head at archive**: `d87c9fe` (24 commits ahead of `origin/master`)

---

## Final State (Terminal Authority)

Per `verify-report.md` (ordinal 13, `verify-cycle2-22-partial-closure`), verified
at head `d87c9fe`:

| Metric | Final Value |
|--------|-------------|
| Verdict | `pass_with_warnings` |
| Requirements | 44/44 |
| Scenarios | 152/152 (✅ COMPLIANT, 0 PARTIAL, 0 UNTESTED, 0 FAILING) |
| Tests | 2512 passed, 18 skipped |
| Coverage | 84.38% (threshold 75%) |
| Assertion quality | 0 CRITICAL, 8 WARNING (non-blocking) |
| Blockers | 0 |
| Critical findings | 0 |

**Test run**: `uv run pytest --cov=bot --cov-fail-under=75` → exit 0, output hash
`sha256:e7cd6b5f85b0475a7d74ac3be896ac17c2cfbf847e2cc419cc1ee63ccaa39b2a`.

The d87 remediation closed the prior 22 PARTIAL evidence gaps via production-path
behavioral probes (`test_remediation_final_partials.py`, `test_remediation_cycle2_behavior.py`,
`test_remediation_final7_untested.py`). The final 69-probe remediation sweep
passed: `69 passed, 1 skipped`, output hash
`sha256:94a326e725c9e22aa3f4184265512be9a2630429968ed70ab83388ac7df252c6`.

### Live Supabase evidence (read-only SQL)

- `supabase_migrations.schema_migrations` contains versions `018`, `019`, `020`, `021`, `022`, `023`.
- RLS enabled on `guild`, `member`, `infraction`, `ticket`, `ticket_category`, `economy_config`, `greeting_config` (the seven previously-unguarded tables).
- Nullable additive columns (`scheduledCloseAt`, `scheduledCloseReason`, `theme_id`) present.
- Both ticket indexes present (`idx_ticket_active_channel`, partial scheduled-close index).
- Focused live probe (`--run-live --no-cov`): `1 passed`, hash `sha256:abeed460b7c0c575cfda0413dd2e4e83869742df3b313ca646967d4ae09de3f1`.

### GGA (Gentleman Guardian Angel) review

- Reviewer model: `glm-5.2`
- Review timeout: `1500` (raised from 500 in commit `acd6fa5` for the large Cycle 2 changeset)
- Result: PASSED without bypass

### Budget (commits ahead of `origin/master`)

3× stacked slices + 2 fixups + 2 remediations + 1 GGA config ≈ 24 commits:

- `8b46de3` merge PR1 (theming+cache) into master
- `76d224c` PR1 theming+cache — brand neon + theme_id + renderer + avatar cache + dashboard
- `4751bbb` PR2a parser+model — time strict + ticket fields
- `5fc9b7b` PR2b migration+db — scheduledClose timestamp + index
- `5cb0069` PR2c services+config — schedule/loop coexistence
- `cfcae3b` PR2d timer listener — ,12h / ,cancel + 60s loop + embed
- `0e303a2` PR3a ocio+assets — banana pool + 8ball + OcioService
- `05b71b1` PR3b security — hierarchy + RLS + hardening
- `fde0790` brand tokens in ticket timer embeds — SUCCESS/WARNING
- `bde6c0f` extract timer business logic to service — GGA architecture
- `acd6fa5` chore(gga): timeout 500→1500
- `9c1e322` remediate 8 blockers — TDD table + lint + behavioral probes
- `49673b7` remediate 2 remaining critical — live RLS + loop e2e
- `b8b7e76` make 018 idempotent post-live — pg_typeof guard + live push 018-023
- `33daac6` make /banana ephemeral per spec S6
- `f46b92b` close final 7 UNTESTED — anon/Guards/8ball/banana/missing-comma/blur/Sentinel
- `d87c9fe` close 22 PARTIAL via behavioral probes

### Warnings (non-blocking, 8 WARNING / 0 CRITICAL)

1. `apply-progress.md` leading metadata still says Head `acd6fa5` and 2460 tests although the verified head is d87 with 2512 passing tests — stale intermediate snapshot, corrected by final verify.
2. `test_pr2_ticket_db_red.py` lines 15-34 — query shape source-inspected; live/index evidence covers deployed shape.
3. `test_pr2_migration_022_red.py` lines 10-37 — migration shape text-inspected; destructive rollback not executed against live.
4. `test_migrations.py` lines 255-283 — migration 021 identity/rollback text-inspected; live identity separately verified.
5-8. (See verify-report.md § Assertion quality for the full list; all are evidence-shape warnings, no behavioral failures.)

### Ephemeral fix

`/banana` made ephemeral per spec S6 (commit `33daac6`).

---

## Gate Validation

### Task Completion Gate — PASSED
- Persisted tasks artifact: `openspec/changes/welcome-neon-timer-banana/tasks.md`
- Checked tasks: 58/58 (`- [x]`)
- Unchecked tasks: 0 (`- [ ]`)
- No stale unchecked implementation tasks; `sdd-apply` marked all completed.

### Native Review Receipt Gate — PASSED (structurally absent)
- `reviewGate` structurally absent: no `review/` directory exists, no review code ran for this candidate.
- Kill switch off; archive proceeds under ordinary repository policy.
- No `reviewOffer` action required.

### Action Context Guard — PASSED
- No `workspace-planning` mode; archive operations are repo-local.
- No `allowedEditRoots` restriction in effect.

---

## Spec Sync (Delta → Main Specs)

Mode: `openspec` (filesystem merge).

14 delta specs merged into main specs. Merge script parsed `## ADDED Requirements` and
`## MODIFIED Requirements` sections, replaced MODIFIED requirements in-place, and appended
ADDED requirements with `<!-- BEGIN/END DELTA -->` markers.

| Domain | ADDED | MODIFIED | Notes |
|--------|-------|----------|-------|
| brand-tokens | 1 | 2 | Neon accent tokens; brand color + all-cogs-palette updated |
| close-confirmation | 1 | 0 | Timer confirmation flow |
| close-countdown | 0 | 1 | Countdown display updated |
| database-layer | 3 | 1 | RLS on remaining tables; AsyncClientOptions; 23505 idempotent. MODIFIED target had duplicate name (cleanup-stability vs product-artifact-audit) — manually replaced the cleanup-stability occurrence (the RLS-enabled-tables version), preserving the product-artifact-audit version. |
| greeting-config | 3 | 3 | theme_id, neon theme, greeting config expansion |
| guards-contracts | 2 | 1 | escape_markdown, AllowedMentions hygiene |
| ocio-commands | 3 | 1 | banana pool, 8ball, OcioService |
| permission-model | 1 | 1 | delete_category→is_admin. MODIFIED target had duplicate name (ticket-physical-split S3 vs refactor-ticket-domain) — manually replaced the ticket-physical-split S3 occurrence (the "24 decorator" version), preserving the refactor-ticket-domain version. |
| sentinel-commands | 1 | 0 | Sentinel hardening |
| tach-boundaries | 2 | 2 | Boundary contracts for new services |
| ticket-model | 3 | 1 | scheduledCloseAt/Reason columns + partial index |
| ticket-service | 4 | 1 | Timer service, prefix listener, scheduled-close path |
| time-parsing | 2 | 0 | parse_duration_strict, strict time parser |
| welcome-goodbye | 3 | 1 | Neon greeting theme, avatar cache |
| **Total** | **29** | **14** | |

### Duplicate-name reconciliation (manual fixes)

Two main specs had pre-existing duplicate requirement names from different
historical deltas. The merge script replaces the first occurrence by name,
which would hit the wrong target. Both were reverted and re-merged manually
against the correct occurrence:

1. **database-layer** — "Explicit non-goals for advisor findings" appears twice
   (product-artifact-audit version + cleanup-stability version). The Cycle 2 delta
   `(Previously:)` references the cleanup-stability version ("All nine public tables
   MUST remain RLS-enabled"). Manually replaced the cleanup-stability occurrence;
   preserved the product-artifact-audit version ("MUST remain out of scope for this change").

2. **permission-model** — "`is_mod` dual-path characterization" appears twice
   (refactor-ticket-domain version + ticket-physical-split S3 version). The Cycle 2
   delta `(Previously:)` references the S3 version ("24 `@is_mod()` decorator
   applications"). Manually replaced the ticket-physical-split S3 occurrence;
   preserved the refactor-ticket-domain version ("23 decorator callers").

Remaining duplicate requirement names in the merged specs (database-layer:
Credential-gated/Evidence-based/Explicit-non-goals; permission-model: is_mod;
ticket-service: Shared-idempotent) are pre-existing historical naming collisions
from prior cycles. Cycle 2 did not introduce them and only MODIFIED the
correctly-targeted occurrence in each case.

### Merge verification

- `git diff --stat openspec/specs/` → 14 files changed, 1106 insertions(+), 74 deletions(-).
- Cycle 2 content grep across main specs: `gaming_neon`, `scheduledCloseAt`,
  `parse_duration_strict`, `ENABLE ROW LEVEL SECURITY`, `get_random_banana`,
  `delete_category requires administrator`, `8ball command` — all found in the
  expected domain specs.

---

## Archive Contents

Moved to `openspec/changes/archive/2026-08-21-welcome-neon-timer-banana/`:

- `proposal.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (58/58 tasks complete)
- `apply-progress.md` ✅
- `verify-report.md` ✅ (uncommitted modifications — final verify at d87c9fe)
- `exploration.md` ✅
- `specs/` ✅ (14 domain delta specs)
- `archive-report.md` ✅ (this file — additive, excluded from source/destination diff)

---

## Source of Truth Updated

The following main specs now reflect the Cycle 2 behavior:
- `openspec/specs/brand-tokens/spec.md`
- `openspec/specs/close-confirmation/spec.md`
- `openspec/specs/close-countdown/spec.md`
- `openspec/specs/database-layer/spec.md`
- `openspec/specs/greeting-config/spec.md`
- `openspec/specs/guards-contracts/spec.md`
- `openspec/specs/ocio-commands/spec.md`
- `openspec/specs/permission-model/spec.md`
- `openspec/specs/sentinel-commands/spec.md`
- `openspec/specs/tach-boundaries/spec.md`
- `openspec/specs/ticket-model/spec.md`
- `openspec/specs/ticket-service/spec.md`
- `openspec/specs/time-parsing/spec.md`
- `openspec/specs/welcome-goodbye/spec.md`

---

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Cycle 2 (welcome-neon-timer-banana) is complete. Ready for Cycle 3 (welcome-ocio-assets).

**Note**: Archive left dirty for orchestrator commit — `sdd-archive` does not commit.
