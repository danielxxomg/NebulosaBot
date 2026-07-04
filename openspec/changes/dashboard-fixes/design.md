# Design: Dashboard Fixes

## Technical Approach

Implement three small dashboard fixes in the Next.js app only: run auth middleware in the supported Node.js middleware runtime, exempt both favicon assets from auth matching, and add authenticated route-group loading/error boundaries. The real protected route group is `dashboard/app/(authenticated)/`, covering `/` and `/guilds/[guildId]` routes; there is no `/dashboard/*` route prefix in this app.

Context7 verdict for Next.js 15: Node.js middleware runtime is supported in Next.js 15.5.x. The middleware-specific API shown by current docs/tests is `export const config = { runtime: 'nodejs', matcher: [...] }`, not top-level `export const runtime = 'nodejs'` (that form is route-segment config). This repo locks `next` to `15.5.19`, so the design should use `config.runtime = 'nodejs'` in `dashboard/middleware.ts`.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Middleware runtime | Add `runtime: 'nodejs'` to the existing `export const config` object | Top-level `export const runtime = 'nodejs'`; keep Edge and accept warning | Context7 validates middleware Node runtime through `config.runtime`; Node removes the `process.version` Edge warning from `@supabase/supabase-js`. Tradeoff: Node middleware may have less Edge locality/cold-start benefit, but auth already performs Supabase I/O and compatibility is more important. |
| Favicon bypass | Change the matcher only in `dashboard/middleware.ts` to `"/((?!api|_next/static|_next/image|favicon\\.(?:ico|png)).*)"` | Add only an in-function `pathname === "/favicon.png"` guard | Matcher exclusion prevents middleware from running for favicon assets at all; this is the smallest fix and keeps asset requests out of auth/session refresh. |
| Route-group boundaries | Add `loading.tsx` and `error.tsx` under `dashboard/app/(authenticated)/` | Per-page boundaries under every guild page | Layout-level boundary matches the authenticated shell and covers `/`, `/guilds/[guildId]`, and nested guild config routes without duplicating UI. |

## Data Flow

### Middleware request flow

```text
Request ── matcher excludes favicon/api/_next ──→ middleware.ts (Node.js)
        └─ favicon.ico/png served directly

middleware.ts ──→ updateSession(request) ──→ Supabase auth session
      │                    │
      │                    └─ refreshed cookies on NextResponse
      ├─ no session ──→ 307 /login?redirect=<real pathname>
      └─ session ────→ continue request
```

### UI boundary flow

```text
(authenticated)/layout.tsx
  ├─ loading.tsx while server components/data are pending
  ├─ page.tsx / guild pages render normally
  └─ error.tsx catches render errors and exposes reset()
```

## File Changes

| File | Action | Description |
|---|---|---|
| `dashboard/middleware.ts` | Modify | Add `runtime: "nodejs"` inside `export const config`; replace matcher with `"/((?!api|_next/static|_next/image|favicon\\.(?:ico|png)).*)"`. This is the only file touched for the favicon fix. |
| `dashboard/app/(authenticated)/loading.tsx` | Create | Server component rendering a skeleton shell that mirrors `layout.tsx`: left sidebar placeholder and main content placeholders/cards using `Skeleton`. |
| `dashboard/app/(authenticated)/error.tsx` | Create | Client error boundary with `'use client'`, `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, and a reset `Button`. |
| `dashboard/__tests__/middleware.test.ts` | Create | Vitest unit tests for matcher behavior and auth redirect regression. |
| `dashboard/__tests__/app/authenticated-boundaries.test.tsx` | Create | Vitest/jsdom render tests for loading skeleton and error reset behavior. |

## Interfaces / Contracts

```ts
// dashboard/middleware.ts
export const config = {
  runtime: "nodejs",
  matcher: ["/((?!api|_next/static|_next/image|favicon\\.(?:ico|png)).*)"],
};
```

```tsx
// dashboard/app/(authenticated)/error.tsx
'use client';

export default function AuthenticatedError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) { /* Card + reset button */ }
```

## Testing Strategy

Follow strict TDD: add failing tests first, verify RED, then implement minimal code.

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Matcher excludes `/favicon.ico` and `/favicon.png`, but includes `/`, `/guilds/123`, `/guilds/123/config` | `dashboard/__tests__/middleware.test.ts`; import `config.matcher`, compile equivalent `RegExp`, assert match/no-match. |
| Unit | Runtime config is Node.js | Same file asserts `config.runtime === "nodejs"`. |
| Unit | Middleware auth redirect still works for real protected routes | Mock `@/lib/supabase/middleware` to return no session; call `middleware(new NextRequest("http://localhost/guilds/123"))`; expect 307 and `/login?redirect=/guilds/123`. |
| Component | Loading boundary renders skeleton shell | `dashboard/__tests__/app/authenticated-boundaries.test.tsx`; render `loading.tsx` and assert multiple `[data-slot="skeleton"]` nodes. |
| Component | Error boundary reset button calls `reset()` | Same file; render `error.tsx` with a test error and `vi.fn()`, click retry/reset button, expect called once. |

If `@testing-library/react` is absent, install it as a dev dependency in apply phase or use `react-dom/client` + DOM events directly; do not weaken assertions.

## Migration / Rollout

No migration required. Rollout is a normal dashboard deploy. Validate with `cd dashboard && npm test && npm run build`, then manually confirm `/favicon.png` returns 200 without redirect.

## Risks / Rollback

- WARNING `dashboard/middleware.ts:44`: adding `runtime` to config changes middleware deployment target from Edge to Node.js; rollback by removing `runtime: "nodejs"`.
- WARNING `dashboard/middleware.ts:45`: matcher regex mistakes can over/under-match routes; rollback to previous matcher or restore only `favicon.ico` exemption.
- WARNING `dashboard/app/(authenticated)/error.tsx:1`: error boundaries must be client components; rollback by deleting `error.tsx`.
- Rollback for loading/error is deleting `dashboard/app/(authenticated)/loading.tsx` and `dashboard/app/(authenticated)/error.tsx`.

## Non-goals

- No bot/Python changes.
- No Supabase schema or migration changes.
- No new dashboard features or redesign.
- No per-page guild loading/error boundaries.

## Open Questions

- [ ] None blocking.
