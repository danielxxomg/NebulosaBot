# Proposal: Dashboard Fixes

## Intent

Three production-confirmed dashboard issues: (1) Edge Runtime warning inflates middleware bundle to 90.2 kB because `@supabase/ssr` transitively imports `process.version`, (2) `favicon.png` requests bypass the middleware public-route exemption causing spurious 307 redirects to `/login` on every page load, (3) no loading or error boundaries in the authenticated layout — users see blank screens during data fetches and unhandled crashes.

## Scope

### In Scope
- Fix Edge Runtime warning: add `export const runtime = 'nodejs'` to `dashboard/middleware.ts`
- Fix favicon matcher: update matcher regex to include `favicon.png`
- Add `loading.tsx` at `(authenticated)` layout level using shadcn Skeleton
- Add `error.tsx` at `(authenticated)` layout level (client component error boundary)
- Tests: vitest tests for matcher regex, loading component render, error boundary behavior

### Out of Scope
- Bot/Python changes
- DB schema or migration changes
- New features or redesign
- Guild-level loading/error boundaries (layout-level is sufficient for now)

## Capabilities

### New Capabilities
None

### Modified Capabilities
None — these are implementation fixes, no spec-level behavior changes.

## Approach

### Fix 1: Edge Runtime → Node.js Runtime

Add `export const runtime = 'nodejs'` to `dashboard/middleware.ts`. Next.js 15 supports Node.js runtime for middleware. This eliminates the `process.version` warning because Node APIs become available. No code changes to `lib/supabase/middleware.ts` — the `createServerClient` call works identically in Node runtime. Tradeoff: slightly larger cold start vs Edge (~10ms), but middleware already does async Supabase auth calls so Edge latency advantage is negligible.

### Fix 2: Favicon Matcher

Update `dashboard/middleware.ts` matcher regex from:
```
"/((?!api|_next/static|_next/image|favicon.ico).*)"
```
to:
```
"/((?!api|_next/static|_next/image|favicon\\.(ico|png)).*)"
```

### Fix 3: Loading & Error Boundaries

- `dashboard/app/(authenticated)/loading.tsx`: full-page Skeleton layout matching the sidebar + content structure using `Skeleton` from `@/components/ui/skeleton`
- `dashboard/app/(authenticated)/error.tsx`: `'use client'` component with error message display and `reset()` button, styled with existing `Card` components

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `dashboard/middleware.ts` | Modified | Add `runtime = 'nodejs'` export, update matcher regex |
| `dashboard/app/(authenticated)/loading.tsx` | New | Skeleton loading boundary |
| `dashboard/app/(authenticated)/error.tsx` | New | Error boundary with reset |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Node runtime slightly increases middleware cold start | Low | Negligible — auth calls dominate latency anyway |
| Loading skeleton flash on fast connections | Low | Acceptable — better than blank screen |

## Rollback Plan

Revert `runtime = 'nodejs'` export (Edge is still default). Revert matcher regex. Delete `loading.tsx` and `error.tsx`. No data or schema changes to undo.

## Dependencies

None. `@supabase/ssr ^0.5.2`, shadcn `Skeleton`, and Next.js 15 already in `package.json`.

## Success Criteria

- [ ] `next build` produces NO `process.version` Edge Runtime warning
- [ ] `GET /favicon.png` returns 200 (not 307 redirect)
- [ ] `loading.tsx` renders Skeleton during page transitions
- [ ] `error.tsx` catches and displays errors with reset option
- [ ] All existing tests pass: `cd dashboard && npm test`
- [ ] New tests cover matcher regex, loading render, error boundary
