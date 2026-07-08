## Exploration: ci-master-green

### Current State

Master CI (`ci.yml`) has been RED for the last 5 runs. Two independent failures block all 3 open PRs (#18, #19, #20):

1. **Python `ruff format --check`** fails in the `qa-matrix` job — 5 files in CI's scoped file list are unformatted.
2. **Dashboard `tsc --noEmit`** fails in the `dashboard-tests` job — 4 TypeScript errors across 2 test files.

Neither failure is in production code logic. Both are tooling/type-safety gate failures that prevent merge.

### Exact CI Commands That Must Pass

From `.github/workflows/ci.yml`:

**qa-matrix job (Python, runs on matrix 3.11/3.12/3.14):**
```
uv run --extra dev ruff format --check bot/services/economy_service.py bot/config.py tests/conftest.py tests/property/ tests/test_economy_service.py tests/test_guild_service.py tests/test_config.py tests/test_database.py tests/test_sentinel_cog.py tests/test_tickets_cog.py tests/test_greeting_service.py bot/models/ticket.py bot/models/ticket_note.py tests/test_migrations.py tests/test_ticket_model.py tests/integration/ bot/services/ticket_service.py tests/test_ticket_service.py
```

**dashboard-tests job (Node 20):**
```
cd dashboard && npx tsc --noEmit
cd dashboard && npx vitest run
```

### Failure 1: Ruff Format Check — Authoritative Unformatted File List

Run against master (clean tree). Exactly 5 files fail `ruff format --check` in CI scope:

| # | File | Nature |
|---|------|--------|
| 1 | `bot/services/ticket_service.py` | Production service — long function calls reformatted to multi-line |
| 2 | `tests/test_database.py` | Test — assert messages and dict literals reformatted |
| 3 | `tests/test_migrations.py` | Test — minor whitespace |
| 4 | `tests/test_ticket_service.py` | Test — formatting |
| 5 | `tests/test_tickets_cog.py` | Test — formatting |

**Root cause:** These files were committed before a ruff format pass was applied. `ruff check` (linting) PASSES on all of them — only formatting is off.

**Fix approach:** Run `uv run ruff format bot/services/ticket_service.py tests/test_database.py tests/test_migrations.py tests/test_ticket_service.py tests/test_tickets_cog.py`. Purely mechanical. Verified via `ruff format --diff`: all changes are whitespace/line-wrapping/trailing-comma — zero semantic changes.

**Risk:** **Negligible.** Ruff format never changes AST or behavior. The diff is cosmetic only (line wrapping, trailing commas, assert-message dedenting).

### Failure 2: Dashboard TypeScript Errors — Root Cause Analysis

4 errors across 2 test files. All are **test-file-only** type issues — no production code type contract is broken.

#### Error 2a: `ticket-actions.test.ts:254` — TS2322 `null` not assignable to `string | undefined`

**Location:** `dashboard/__tests__/lib/actions/ticket-actions.test.ts`, line 254

```typescript
setupAuth({
  guildTicketCategoryId: null,  // ← TS2322 here
  ...
});
```

**Root cause:** The `setupAuth()` helper function parameter `guildTicketCategoryId` has a default value of `CATEGORY_ID` (string `"111111111111111111"`). TypeScript infers the parameter type as `string | undefined` from the default. Passing `null` violates that — even though the DB column (`GuildConfig.ticketCategoryId`) is `string | null`.

**Production impact:** None. The test is correctly testing a `null` category ID scenario (guild without a ticket category configured). The type mismatch is purely in the test helper signature.

**Fix:** Add explicit type annotation to the `setupAuth` parameter:
```typescript
guildTicketCategoryId: string | null = CATEGORY_ID,
```

**Risk:** **None.** Test-only signature fix. Does not change any production contract.

#### Error 2b: `middleware.test.ts:2` — TS7016 No declaration file for `next/dist/compiled/path-to-regexp`

**Location:** `dashboard/__tests__/middleware.test.ts`, line 2

```typescript
import { pathToRegexp } from "next/dist/compiled/path-to-regexp";
```

**Root cause:** `next/dist/compiled/path-to-regexp` is Next.js's internal bundled copy of the `path-to-regexp` library. It ships no `.d.ts` files. This is a known pattern — Next.js bundles dependencies under `dist/compiled/` without type declarations.

The test uses `pathToRegexp` solely to validate that the middleware matcher config compiles without throwing (a guard against invalid `path-to-regexp` patterns that would break `next build`).

The `path-to-regexp` package IS installed as a transitive dependency (`node_modules/path-to-regexp/dist/index.d.ts` exists with full types).

**Fix:** Change the import to use the typed npm package:
```typescript
import { pathToRegexp } from "path-to-regexp";
```

**Alternative:** Add a `// @ts-expect-error next/dist/compiled has no types` directive. Less clean but minimal diff.

**Risk:** **Low.** The `path-to-regexp` npm package version installed may differ from Next.js's bundled copy, but the `pathToRegexp(path)` function signature is stable across versions. The test only validates that a regex pattern compiles — it doesn't exercise version-specific behavior.

#### Errors 2c & 2d: `middleware.test.ts:81,103` — TS2345 Missing `supabase` property

**Location:** `dashboard/__tests__/middleware.test.ts`, lines 81 and 103

```
Argument of type '{ supabaseResponse: NextResponse; session: null; }'
is not assignable to parameter of type
'{ supabaseResponse: NextResponse; supabase: SupabaseClient; session: Session | null; }'.
Property 'supabase' is missing.
```

**Root cause:** The `updateSession()` function in `dashboard/lib/supabase/middleware.ts` returns THREE properties:

```typescript
return { supabaseResponse, supabase, session };
```

The test mocks only provide TWO (`supabaseResponse` + `session`), missing `supabase`.

Additionally at line 103, `session: { user: { id: "u1" } } as never` uses an `as never` cast — this was likely a previous workaround attempt that doesn't satisfy the missing-property check.

**Production impact:** None. The production middleware (`dashboard/middleware.ts`) only destructures `supabaseResponse` and `session` from the return value — it correctly ignores the `supabase` property. The test just needs to match the return type signature.

**Fix:** Add `supabase` to both mock return values:
```typescript
vi.mocked(updateSession).mockResolvedValue({
  supabaseResponse: NextResponse.next(),
  supabase: {} as SupabaseClient,   // ← add this
  session: null,
});
```

And at line 103, also add `supabase` and fix the `as never` cast to use a proper `Session` type or cast.

**Risk:** **None.** Test-only mock completeness fix. The `supabase` property is unused in the test assertions — it just needs to exist to satisfy the type.

### Affected Areas

- `bot/services/ticket_service.py` — ruff format (line wrapping cosmetic)
- `tests/test_database.py` — ruff format (assert messages, dict literals)
- `tests/test_migrations.py` — ruff format (minor whitespace)
- `tests/test_ticket_service.py` — ruff format
- `tests/test_tickets_cog.py` — ruff format
- `dashboard/__tests__/lib/actions/ticket-actions.test.ts` — TS helper parameter type
- `dashboard/__tests__/middleware.test.ts` — TS import + mock completeness

### Approaches

1. **Minimal targeted fix** — Fix only what CI checks, scoped to failing files
   - Run `ruff format` on the 5 unformatted files (scoped, not project-wide)
   - Fix 4 TS errors in 2 test files with minimal changes
   - Pros: Fastest, lowest risk, smallest diff
   - Cons: Leaves broader unformatted debt (35 files total unformatted on master)
   - Effort: **Low**

2. **Full project format + fix** — Run `ruff format .` project-wide + fix TS errors
   - Pros: Clean slate, no partial formatting debt
   - Cons: Large diff, touches files unrelated to CI failure, bigger review surface
   - Effort: **Low** (same commands, bigger scope)

### Recommendation

**Approach 1 — Minimal targeted fix.** The CI only checks a scoped file list. Fix exactly what's broken:
1. `ruff format` the 5 files (mechanical, zero risk)
2. Fix `setupAuth` parameter type in `ticket-actions.test.ts` (1 line)
3. Fix `path-to-regexp` import in `middleware.test.ts` (1 line)
4. Add `supabase` to mock returns in `middleware.test.ts` (2 lines)

Total estimated diff: ~15-20 lines across 7 files. All changes are either cosmetic formatting or test-only type fixes.

The broader formatting debt (30 additional unformatted files outside CI scope) should be tracked separately — it doesn't block CI.

### Risks

- **Low risk:** The `path-to-regexp` npm package version may differ from Next.js's bundled copy. Mitigated by the fact that `pathToRegexp(path)` signature is stable and the test only checks compilation, not matching behavior.
- **Negligible risk:** Ruff format is purely cosmetic (verified via `--diff`).
- **No production risk:** All TS errors are test-file-only. No production type contracts are broken or masked.

### Ready for Proposal

**Yes.** The scope is clear, the fixes are mechanical, and the risk is minimal. The orchestrator should proceed to `sdd-propose`.
