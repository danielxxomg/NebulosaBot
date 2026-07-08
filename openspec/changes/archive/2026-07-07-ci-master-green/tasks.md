# Tasks: CI Master Green

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 200–350 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain (locked: single-pr) |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Python formatting + TS fixes + gates | PR 1 | Single PR, two commits |

## Phase 1: Python Formatting — Commit 1: `style: apply ruff formatting project-wide`

- [x] 1.1 **RED** — `uv run ruff format --check .` → observe ~35 files fail. *(Spec: Python Formatting Gate)*
- [x] 1.2 **GREEN** — `uv run ruff format .` → all 35 files reformatted.
- [x] 1.3 **VERIFY** — `uv run ruff format --check .` → exit 0, zero files. *(Spec: Full project passes format check)*
- [x] 1.4 **VERIFY** — `uv run pytest` → all pass. Formatting must not break tests. *(Spec: Non-Regression)*
- [x] 1.5 **Commit** — stage reformatted `.py` files only. `style: apply ruff formatting project-wide`.

## Phase 2: Dashboard TS Fixes — Commit 2: `test: fix dashboard type-check failures`

- [x] 2.1 **RED** — `cd dashboard && npx tsc --noEmit` → 4 errors: TS2322 `:254`, TS7016 `:2`, TS2345 `:81`/`:103`. *(Spec: TypeScript Compilation Gate)*
- [x] 2.2 **GREEN** — `ticket-actions.test.ts:254`: type `guildTicketCategoryId` as `string | null`.
- [x] 2.3 **GREEN** — `middleware.test.ts:2`: import `path-to-regexp` from npm package.
- [x] 2.4 **GREEN** — `middleware.test.ts:81,103`: add `supabase: {} as SupabaseClient` to mock returns.
- [x] 2.5 **VERIFY** — `npx tsc --noEmit` → exit 0. *(Spec: Full dashboard type-check passes)*
- [x] 2.6 **VERIFY** — `npx vitest run` → all pass. TS fixes must not break runtime. *(Spec: Non-Regression)*
- [x] 2.7 **Commit** — stage dashboard test files only. `test: fix dashboard type-check failures`.

## Phase 3: Pre-Push Verification + Delivery

- [x] 3.1 **Gate sweep** — run all 4 gates: `ruff format --check .`, `tsc --noEmit`, `pytest`, `vitest run`. All exit 0. *(Spec: all Requirements)*
- [x] 3.2 **Push** — branch `fix/ci-master-green` from master, push.
- [x] 3.3 **Open PR** — target `master`. Body: scope, 2 commits, rollback = `git revert`, downstream rebase plan. *(Spec: Rollback is safe)*

## Phase 4: Post-Merge Rebase (FOLLOW-UP — not this PR)

- [ ] 4.1 **Rebase #18** — onto green master. Resolve format conflicts in 5 shared files: accept master format, preserve #18 logic, `ruff format` touched files, fixup commit if needed. *(Spec: PR #18 rebases without conflicts)*
- [ ] 4.2 **Rebase #19/#20** — onto green master. Verify clean. *(Spec: PRs #19/#20 rebase without conflicts)*
