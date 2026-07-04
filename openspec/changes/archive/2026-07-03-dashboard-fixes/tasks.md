# Tasks: Dashboard Fixes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150–200 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | single-pr |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | All 3 fixes + tests + build verification | PR 1 | Single work unit; under 200 lines |

## Prerequisite: Install @testing-library/react

- [x] 0.1 `cd dashboard && npm i -D @testing-library/react` — required for component render tests in Phases 2–3. Verify `package.json` lists it after install.

## Phase 1: Middleware — Favicon Matcher + Node.js Runtime

- [x] 1.1 **RED** — Create `dashboard/__tests__/middleware.test.ts`. Import `config` from `@/middleware`. Assert `config.runtime === "nodejs"`. Compile `config.matcher[0]` into `RegExp`. Assert NO match: `/favicon.ico`, `/favicon.png`. Assert match: `/`, `/guilds/123`, `/guilds/123/config`, `/login`. Run `npm test -- __tests__/middleware.test.ts` — expect FAIL (runtime missing, favicon.png matches).
- [x] 1.2 **GREEN** — Edit `dashboard/middleware.ts`: add `runtime: "nodejs"` to `export const config`; change matcher to `"/((?!api|_next/static|_next/image|favicon\\.(ico|png)).*)"`. Run test — expect PASS. **Deviation (justified):** matcher uses non-capturing `favicon\\.(?:ico|png)` — Next's path-to-regexp rejects capturing groups `(ico|png)` with "Capturing groups are not allowed" (would break `next build`). Verified empirically. Guard test added (1.1).
- [x] 1.3 **Verify** — `cd dashboard && npm test -- __tests__/middleware.test.ts` all green.

## Phase 2: Loading Boundary

- [x] 2.1 **RED** — Create `dashboard/__tests__/app/authenticated-boundaries.test.tsx`. Import `Loading` from `@/app/(authenticated)/loading`. Render with `@testing-library/react`. Assert multiple `data-slot="skeleton"` nodes exist in the DOM. Run test — expect FAIL (file missing).
- [x] 2.2 **GREEN** — Create `dashboard/app/(authenticated)/loading.tsx` as server component rendering a `<div className="flex min-h-screen">` with a sidebar skeleton column (`w-64` Skeleton) and main content area with Skeleton cards. Run test — expect PASS.
- [x] 2.3 **Verify** — `cd dashboard && npm test -- __tests__/app/authenticated-boundaries.test.tsx` green.

## Phase 3: Error Boundary

- [x] 3.1 **RED** — Add to `dashboard/__tests__/app/authenticated-boundaries.test.tsx`. Import `Error` from `@/app/(authenticated)/error`. Render with `error: new Error("test")` and `reset: vi.fn()`. Assert error message displayed. Click the reset button. Assert `reset` called once. Run test — expect FAIL (file missing).
- [x] 3.2 **GREEN** — Create `dashboard/app/(authenticated)/error.tsx` with `'use client'` directive. Accept `{ error, reset }` props. Render `Card` > `CardHeader` > `CardTitle` ("Something went wrong") + `CardDescription` (`error.message`) + `CardContent` > `Button` onClick={reset}. Run test — expect PASS.
- [x] 3.3 **Verify** — `cd dashboard && npm test -- __tests__/app/authenticated-boundaries.test.tsx` all green (loading + error tests).

## Phase 4: Auth Guard Regression

- [x] 4.1 **RED** — Add to `dashboard/__tests__/middleware.test.ts`. Mock `@/lib/supabase/middleware` `updateSession` to return `{ supabaseResponse: NextResponse.next(), session: null }`. Call `middleware(new NextRequest("http://localhost/guilds/123"))`. Assert response status is 307 and `Location` header contains `/login?redirect=/guilds/123`. Run test — expect FAIL or PASS depending on existing mock setup.
- [x] 4.2 **GREEN** — If FAIL, fix mock wiring (no production code change expected — middleware auth logic is unchanged). Run test — expect PASS.
- [x] 4.3 **Verify** — `cd dashboard && npm test` — ALL tests green (existing + new).

## Phase 5: Full Verification

- [x] 5.1 `cd dashboard && npm test` — all tests pass, zero failures. **Result: 8 files, 97 tests passed.**
- [x] 5.2 `cd dashboard && npm run build` — clean build, NO `process.version` or `Node.js API is used` warning in output. **Result: build succeeded, no Edge/Node warning.**
- [x] 5.3 Manual: start dev server, hit `http://localhost:3000/favicon.png` — returns 200 (not 307). **Waived by orchestrator (build clean). Behavior covered by matcher unit test: `/favicon.png` and `/favicon.ico` assert `matcher.test() === false`, so middleware never runs → no 307.**

## Phase 6: Commit (orchestrator-managed)

- [x] 6.1 Orchestrator runs review-reliability then handles commit. Do NOT commit from apply agent. *(Reconciled at archive time: commit f61e986 exists at HEAD; verify-report confirms completion.)*
