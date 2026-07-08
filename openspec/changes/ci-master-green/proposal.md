# Proposal: ci-master-green

## Intent

Master CI red for 5 runs, blocking PRs #18/#19/#20. Two gate failures: `ruff format --check` (5 files) + `tsc --noEmit` (4 TS errors, 2 test files). Zero production impact.

## Scope

### In Scope
- `ruff format .` project-wide (35 files, cosmetic only)
- Fix TS2322 `ticket-actions.test.ts:254` — `setupAuth` param type `string | null`
- Fix TS7016 `middleware.test.ts:2` — import `path-to-regexp` from npm instead of `next/dist/compiled`
- Fix TS2345 `middleware.test.ts:81,103` — add missing `supabase` to mock returns

### Out of Scope
- ruff rules, mypy, CI matrix, coverage upgrades (→ `tooling-rigor`)
- Widening CI `ruff format --check` to project-wide (see Open Decisions)
- Production code/behavior changes

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None (cosmetic formatting + test-only type fixes — no spec requirements change)

## Approach

**Approach 2 — Clean Slate** (user-chosen): `ruff format .` project-wide + fix 4 TS errors. Estimated diff: ~200-400 lines across 37 files.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| 35 `*.py` files | Modified | `ruff format` cosmetic (whitespace, line-wrapping) |
| `dashboard/__tests__/lib/actions/ticket-actions.test.ts` | Modified | `setupAuth` param type annotation |
| `dashboard/__tests__/middleware.test.ts` | Modified | Import path + mock completeness |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `path-to-regexp` npm version ≠ Next.js bundled | Low | Signature stable; test checks compilation only |
| Format diff approaches 800-line review budget | Medium | Cosmetic diffs shouldn't be split — atomic by nature |
| Rebase conflicts with PR #18 (same 5 CI-scope files) | High | Format master first, rebase PR #18, fixup commit |

## Rollback Plan

`git revert <merge-sha>` — single commit. All changes cosmetic/test-only, no data or behavior change.

## Dependencies

- None

## Success Criteria

- [ ] `ruff format --check .` passes (0 files reformatted)
- [ ] `npx tsc --noEmit` passes in `dashboard/`
- [ ] CI green on Python 3.11, 3.12, 3.14
- [ ] PRs #18, #19, #20 rebase onto green master cleanly

## Open Decisions

### 1. Widen CI `ruff format --check` to project-wide?

CI checks a hardcoded file list, not `.`. The 30 outside-CI-scope files can silently re-decay.

**Recommendation:** Leave CI scoped here. Defer to `tooling-rigor`.

### 2. Format-on-master vs rebase conflicts with PR #18

PR #18 (`fix/runtime-bugfixes`) touches the same 5 CI-scope Python files. Formatting on master causes rebase conflicts.

**Recommendation:** Format master first, rebase PR #18, re-run `ruff format` on its touched files in a fixup commit.

### 3. Review-budget interaction

35 files → ~200-400 lines. Under 800-line budget likely. Auto-forecast may suggest splitting — but format passes are atomic; partial application leaves inconsistent formatting.

**Recommendation:** Single PR. Argue against splitting.
