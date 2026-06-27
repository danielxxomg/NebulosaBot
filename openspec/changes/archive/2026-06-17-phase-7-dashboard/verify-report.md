# Verification Report

**Change**: phase-7-dashboard  
**Version**: MVP  
**Mode**: Strict TDD (`openspec/config.yaml` sets `strict_tdd: true`; Vitest runner detected for the dashboard sub-project)

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 36 |
| Tasks complete | 36 |
| Tasks incomplete | 0 |

All 36 task checkboxes in `tasks.md` are marked `[x]`. Every file referenced in the task list exists on disk.

## Build & Tests Execution

**Type check**: ❌ Failed
```text
$ npx tsc --noEmit
__tests__/lib/actions/_test-helpers.ts(145,3): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/_test-helpers.ts(147,5): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/_test-helpers.ts(152,3): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/_test-helpers.ts(154,5): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/_test-helpers.ts(159,3): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/_test-helpers.ts(161,5): error TS2304: Cannot find name 'expect'.
__tests__/lib/actions/economy-actions.test.ts(69,52): error TS2345: Argument of type 'Promise<SupabaseClient<...>>' is not assignable to parameter of type 'SupabaseClient<...>'.
__tests__/lib/actions/greeting-actions.test.ts(69,52): error TS2345: Argument of type 'Promise<SupabaseClient<...>>' is not assignable to parameter of type 'SupabaseClient<...>'.
__tests__/lib/actions/guild-actions.test.ts(66,52): error TS2345: Argument of type 'Promise<SupabaseClient<...>>' is not assignable to parameter of type 'SupabaseClient<...>'.
__tests__/lib/discord.test.ts(12,3): error TS2304: Cannot find name 'beforeAll'.
__tests__/lib/discord.test.ts(58,3): error TS2304: Cannot find name 'beforeAll'.
```
The errors are isolated to the test suite: `tsconfig.json` does not include Vitest/globals/Jest-DOM types and `createServiceClient` is mocked without `await`.

**Build**: ✅ Passed
```text
$ npm run build
Next.js 15.5.19 — Compiled successfully
Route (app): /, /login, /api/auth/callback, /api/auth/logout, /guilds/[guildId], /guilds/[guildId]/config, /guilds/[guildId]/economy, /guilds/[guildId]/greeting
Middleware: 90 kB
```

**Tests**: ✅ 77 passed / 0 failed / 0 skipped
```text
$ npm run test
Test Files  5 passed (5)
     Tests  77 passed (77)
  Duration  600ms
```

**Coverage**: ➖ Not available — no coverage provider is installed for Vitest.

## Spec Compliance Matrix

| Capability | Requirement | Scenario | Test | Result |
|------------|-------------|----------|------|--------|
| dashboard-auth | Discord OAuth2 login | User initiates login | (none) | ❌ UNTESTED |
| dashboard-auth | Discord OAuth2 login | User denies consent | (none) | ⚠️ PARTIAL — callback redirects to `/login?error=auth_failed`, but `login/page.tsx` does not render the error message |
| dashboard-auth | Session middleware | Authenticated user accesses dashboard | (none) | ❌ UNTESTED |
| dashboard-auth | Session middleware | Expired session | (none) | ❌ UNTESTED |
| dashboard-auth | Session middleware | Deep link without session | (none) | ❌ FAILING — middleware stores `?redirect=pathname`, but the OAuth callback does not return the user to the original URL |
| dashboard-auth | Guild administrator authorization | Authorized guild | `guild-actions.test.ts` (auth paths) | ⚠️ PARTIAL — action-level guard covered; page-level selector filtering has no covering test |
| dashboard-auth | Guild administrator authorization | Non-admin guild hidden | (none) | ❌ UNTESTED |
| dashboard-auth | Guild administrator authorization | Bot-not-present guild hidden | (none) | ❌ UNTESTED |
| dashboard-auth | Logout | User logs out | (none) | ❌ UNTESTED — `/api/auth/logout` exists but is not exercised by tests |
| dashboard-layout | Authenticated route group | Authenticated navigation | (none) | ⚠️ PARTIAL — `(authenticated)` route group + middleware exist; route prefix is `/` not `/dashboard` as spec states |
| dashboard-layout | Authenticated route group | Public routes remain accessible | (none) | ❌ UNTESTED |
| dashboard-layout | Sidebar navigation | Guild-scoped links | (none) | ⚠️ PARTIAL — links target `/guilds/:id/*` instead of `/dashboard/guilds/:id/*` |
| dashboard-layout | Sidebar navigation | Collapsed mobile sidebar | (none) | ❌ UNTESTED |
| dashboard-layout | Guild selector | Selector populated | (none) | ❌ UNTESTED |
| dashboard-layout | Guild selector | Selection persists | (none) | ⚠️ PARTIAL — selection is implicit via URL path, no explicit selector state |
| dashboard-layout | Guild selector | No authorized guilds | (none) | ❌ UNTESTED — empty state UI exists in `page.tsx` |
| dashboard-layout | Per-guild permission guard | Direct URL to authorized guild | (none) | ❌ UNTESTED |
| dashboard-layout | Per-guild permission guard | Direct URL to unauthorized guild | (none) | ⚠️ PARTIAL — redirects to `/?error=unauthorized` instead of `/dashboard` with an error message |
| dashboard-layout | Shell loading state | Initial load | (none) | ❌ UNTESTED — no skeleton/loading state is rendered while session/guild data is pending |
| guild-config-pages | Read guild configuration | Config page load | (none) | ❌ UNTESTED |
| guild-config-pages | Read guild configuration | Missing config defaults | (none) | ⚠️ PARTIAL — economy/greeting pages use defaults; the core guild config page returns "Guild not found" when the `guild` row is absent |
| guild-config-pages | Update guild configuration | Valid update | `guild-actions.test.ts` | ⚠️ PARTIAL — DB update + revalidation are tested; the required bot webhook notification is not implemented |
| guild-config-pages | Update guild configuration | Unauthorized update attempt | `guild-actions.test.ts` | ✅ COMPLIANT |
| guild-config-pages | Form validation | Prefix too long | `guild-actions.test.ts` | ✅ COMPLIANT |
| guild-config-pages | Form validation | Invalid language code | `guild-actions.test.ts` | ✅ COMPLIANT |
| guild-config-pages | Form validation | Malformed channel ID | `guild-actions.test.ts` | ✅ COMPLIANT |
| guild-config-pages | Webhook fallback | Bot offline during update | (none) | ❌ FAILING — no webhook call is made; TTL fallback exists but the success warning about delayed propagation is not shown |
| guild-config-pages | Page revalidation | Refresh after save | `guild-actions.test.ts` | ✅ COMPLIANT |

**Compliance summary**: 5/29 scenarios compliant, 9 partial, 15 untested/failing.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Discord OAuth2 via Supabase Auth | ✅ Implemented | `login/page.tsx` uses `supabase.auth.signInWithOAuth({ provider: "discord" })` |
| Session middleware | ✅ Implemented | `middleware.ts` refreshes session and redirects unauthenticated users to `/login` |
| Guild admin authorization | ✅ Implemented | `verifyGuildAdmin` in every Server Action + `guilds/[guildId]/layout.tsx` guard |
| Direct Supabase reads/writes | ✅ Implemented | `createServiceClient` used in pages and actions |
| Server Actions for config CRUD | ✅ Implemented | `guild-actions.ts`, `economy-actions.ts`, `greeting-actions.ts` |
| Form validation | ✅ Implemented | Prefix length, language set, snowflake regex, numeric bounds, message length |
| Revalidation after save | ✅ Implemented | `revalidatePath(`/guilds/${guildId}`, "layout")` in all actions |
| Bot webhook notification | ❌ Not implemented | Per spec, updates MUST notify the bot; design/proposal deferred webhook, but spec still requires it |
| Deep-link post-login return | ❌ Not implemented | `?redirect=` is set on `/login` but never forwarded through OAuth callback |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Next.js App Router | ✅ Yes | `dashboard/` is a Next.js 15 App Router project |
| Supabase Auth + Discord OAuth2 | ✅ Yes | No custom OAuth implementation |
| Direct Supabase queries | ✅ Yes | No bot API proxy layer |
| TTL-only cache sync | ✅ Yes | Webhook deferred per design decision |
| Tailwind + shadcn/ui | ✅ Yes | Components in `components/ui/*` |
| Server Actions for mutations | ✅ Yes | All mutations use Server Actions |
| Supabase client file structure | ⚠️ Deviation | Design specified `lib/supabase/server.ts` and `lib/supabase/client.ts`; actual code uses a single `lib/supabase.ts` |
| Route namespace | ⚠️ Deviation | Design/spec reference `/dashboard/*` routes; actual app uses root `/guilds/*` with no `basePath` |
| `ActionResult` contract | ✅ Yes | Matches design exactly |
| TypeScript interfaces | ✅ Yes | Mirrors Python camelCase schema from `lib/types.ts` |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ❌ Missing | No `apply-progress.md` artifact found for this change |
| All tasks have tests | ⚠️ Partial | Only Phase 5 tasks have test files; scaffolding/layout/auth tasks lack tests |
| RED confirmed (tests exist) | ⚠️ Partial | 5 test files exist; they map only to action/type validation tasks |
| GREEN confirmed (tests pass) | ✅ Yes | 77/77 Vitest tests pass on execution |
| Triangulation adequate | ✅ Yes | Validation cases cover boundary values, invalid inputs, and auth failures |
| Safety Net for modified files | ➖ Unknown | No apply-progress "Files Changed" table to cross-reference |

**TDD Compliance**: 2/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 77 | 5 | Vitest + jsdom |
| Integration | 0 | 0 | not installed |
| E2E | 0 | 0 | not installed |
| **Total** | **77** | **5** | |

### Changed File Coverage

Coverage analysis skipped — no coverage tool is installed for Vitest (`@vitest/coverage-v8` is not present in `devDependencies`).

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|------|------|-----------|-------|----------|
| `__tests__/lib/types.test.ts` | multiple | `expect(Object.keys(config).sort()).toEqual([...expectedKeys].sort())` | Tautological — the object is built from the same key list it is compared against; it does not exercise the exported TypeScript interface | WARNING |

**Assertion quality**: 0 CRITICAL, 1 WARNING.

## Quality Metrics

**Linter**: ➖ Not configured — `npm run lint` prompts for initial ESLint setup.
**Type Checker**: ❌ 11 errors in test files (see Type check output above).

## Issues Found

**CRITICAL**:
1. `npx tsc --noEmit` fails with 11 errors. The explicit verification requirement to type-check the dashboard is not met.
2. Strict TDD protocol was not followed — no `apply-progress.md` / TDD Cycle Evidence table exists for this change.
3. Spec requirement "Valid update … bot receives a sync notification" is not implemented; the webhook sidecar is absent.
4. Spec requirement "Deep link without session … returned to the original URL after login" is not implemented.

**WARNING**:
1. Many spec scenarios (20+) have no automated covering tests and are only verified by source inspection.
2. Design/spec assume routes under `/dashboard/*`; the deployed app uses root `/guilds/*` with no `basePath`.
3. OAuth denial path redirects to `/login?error=auth_failed` but the login page does not surface the error to the user.
4. Per-guild unauthorized access redirects to `/?error=unauthorized` rather than `/dashboard` with an error message.
5. No loading/skeleton state is shown while session and guild data are pending.
6. Core guild config page shows "Guild not found" for a missing `guild` row instead of default values.
7. `types.test.ts` assertions are tautological and do not actually guard the exported interface shape.
8. `.env.example` is missing `NEXT_PUBLIC_SITE_URL`, which `app/api/auth/logout/route.ts` requires.

**SUGGESTION**:
1. Add `@vitest/coverage-v8` and a coverage threshold for changed dashboard files.
2. Configure ESLint explicitly so `npm run lint` can run non-interactively.
3. Add page/component-level tests (e.g., with React Testing Library) for the guild selector and sidebar to raise confidence in layout/auth scenarios.
4. Reconcile the spec, design, and implementation on the `/dashboard/*` route prefix and the deferred webhook.

## Verdict

**FAIL**

The implementation is functionally complete against the task list and the Vitest suite passes, but the explicit `tsc --noEmit` requirement fails, several MUST scenarios in the specs are not implemented (webhook notification, deep-link return), and the Strict TDD apply-progress artifact is missing. These block archive readiness until addressed.
