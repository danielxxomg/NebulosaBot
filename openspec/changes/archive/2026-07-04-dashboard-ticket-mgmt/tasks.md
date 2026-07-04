# Tasks: Dashboard Ticket Management

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 250–300 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-always |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full ticket view feature (action + page + sidebar + tests) | PR 1 | Single PR; all phases below |

## Phase 1: Test Helper Extension

- [x] 1.1 Add `ticketSelectResult` override and `ticket` table chain to `buildMockServiceClient` in `dashboard/__tests__/lib/actions/_test-helpers.ts` — supports `.select().eq().order().limit()` returning `{ data: Ticket[]; error: null | Error }`. Verify: existing tests still pass (`cd dashboard && npm test`).

## Phase 2: Action — RED

- [x] 2.1 Create `dashboard/__tests__/lib/actions/ticket-actions.test.ts` with vitest mocks for `@/lib/supabase`, `@/lib/discord`. Follow `economy-actions.test.ts` mock pattern. RED tests:
  - Auth rejection: unauthenticated → `{ data: null, error: /authenticated/i }`
  - Non-admin rejection → `{ data: null, error: /administrator/i }`
  - GuildId filter: assert `eq("guildId", GUILD_ID)` called on ticket chain
  - Query shape: assert `.from("ticket").select("*").eq("guildId", ...).order("createdAt", { ascending: false }).limit(50)`
  - Return shape: success → `{ data: Ticket[], error: null }`
  - Empty data: mock `[]` → `{ data: [], error: null }`
- Verify: `cd dashboard && npm test -- ticket-actions` — all tests FAIL (module not found).

## Phase 3: Action — GREEN

- [x] 3.1 Create `dashboard/lib/actions/ticket-actions.ts` with:
  - `"use server"` directive
  - Copy local `verifyGuildAdmin` (from `guild-actions.ts:30-66`)
  - `getTicketsForGuild(guildId: string): Promise<TicketListResult>` — calls verifyGuildAdmin, then `createServiceClient().from("ticket").select("*").eq("guildId", guildId).order("createdAt", { ascending: false }).limit(50)`
  - Returns `{ data: tickets ?? [], error: null }` on success, `{ data: null, error: "..." }` on failure
  - Imports: `createServerSupabaseClient`, `createServiceClient` from `@/lib/supabase`; `fetchUserGuilds`, `hasAdministratorPerm` from `@/lib/discord`; `Ticket` from `@/lib/types`
- Verify: `cd dashboard && npm test -- ticket-actions` — all tests PASS.

## Phase 4: Action — REFACTOR

- [x] 4.1 Review `ticket-actions.ts` for naming, imports, docstring. Confirm verifyGuildAdmin matches guild-actions pattern exactly. Verify: `cd dashboard && npm test -- ticket-actions` still PASS.

## Phase 5: Page Component

- [x] 5.1 Create `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx` server component:
  - `const { guildId } = await params` (Next.js 15 Promise pattern)
  - Call `getTicketsForGuild(guildId)`, handle error with Card
  - Compute stats via `tickets.filter(t => t.status === ...).length` for open/claimed/closed
  - Render 3 stats Cards (Open, Claimed, Closed) in `grid gap-4 md:grid-cols-3`
  - Render ticket table: columns Number, Status, Author, Created, Claimed By
  - StatusBadge: page-local styled `<span>` — green (open), yellow (claimed), gray (closed), neutral (unknown)
  - `claimedBy === null` → `—`
  - `createdAt` → `new Date(...).toLocaleString()`
  - Empty state: "No tickets yet" message in Card
  - Use `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent` from `@/components/ui/card`
- Verify: `cd dashboard && npm run build` — page compiles without errors.

## Phase 6: Sidebar Link

- [x] 6.1 In `dashboard/components/sidebar.tsx`: import `Ticket` from `lucide-react`, add `{ href: \`/guilds/${guildId}/tickets\`, label: "Tickets", icon: Ticket }` to `navItems` array after the Greeting entry. Verify: `cd dashboard && npm run build` clean.

## Phase 7: Full Verification

- [x] 7.1 Run `cd dashboard && npm test` — all tests green, no regressions.
- [x] 7.2 Run `cd dashboard && npm run build` — clean build, no TypeScript or lint errors.

## Phase 8: Commit Preparation

- [x] 8.1 Single work unit — committed as df43d09 + a51ca7f (archive-time stale-checkbox reconciliation: verify-report PASS WITH WARNINGS confirms all 15/15 scenarios compliant, full suite 118/118 green).
