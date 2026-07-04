# Proposal: Dashboard Ticket Management

## Intent

Admins deploy ticket panels from the bot but have no dashboard view of open tickets, stats, or ticket history. This change adds a read-only ticket overview page so admins can monitor ticket status without switching to Discord.

## Scope

### In Scope
- New page `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx` — server component showing stats (open/claimed/closed counts) + ticket list table (id, status, opener, created_at, claimed_by)
- New Server Action `dashboard/lib/actions/ticket-actions.ts` — `getTicketsForGuild(guildId)` with `verifyGuildAdmin` re-check pattern
- Sidebar link to `/tickets` in `dashboard/components/sidebar.tsx`
- Tests: vitest for the Server Action (mock Supabase, assert guildId filter + auth re-check + response shape)
- TS types `Ticket` and `TicketStatus` already exist in `dashboard/lib/types.ts` (lines 108–135) — no changes needed

### Out of Scope
- Close/claim/reopen from dashboard (future change)
- Bot/Python changes
- Schema or migration changes
- Sub-tickets (separate change)
- Transcript viewing (future change)
- Pagination controls (hard limit 50 for v1)

## Capabilities

### New Capabilities
- `dashboard-ticket-view`: Read-only ticket overview page with per-guild stats and ticket list. Filtered by guildId, auth-gated by verifyGuildAdmin.

### Modified Capabilities
None — no existing spec requirements change.

## Approach

- **Server Component** (no client state): page.tsx calls `getTicketsForGuild(guildId)` which uses `createServiceClient()` (service_role, bypasses RLS) to query tickets filtered by guildId.
- **Auth pattern**: reuse `verifyGuildAdmin` from guild-actions (copy pattern, not import — each action file is self-contained per existing convention).
- **Status badges**: map `open` → green Badge, `claimed` → yellow Badge, `closed` → gray Badge using shadcn Badge component.
- **Stats**: aggregate counts via Supabase query or JS-side reduce (small dataset, ≤50 rows).
- **No caching**: read-on-demand server component, fresh on each navigation.
- **DB column names**: Supabase returns camelCase (`ticketNumber`, `guildId`, `authorId`, `createdAt`, `claimedBy`, `lastActivity`, `closedAt`, `transcriptUrl`). These match the existing `Ticket` interface in types.ts and the bot model's `from_db_row`.
- **Test pattern**: follow `economy-actions.test.ts` — mock `createServiceClient`, `createServerSupabaseClient`, `fetchUserGuilds`, assert auth rejection + successful data fetch + shape.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx` | New | Server component: stats cards + ticket list table |
| `dashboard/lib/actions/ticket-actions.ts` | New | `getTicketsForGuild(guildId)` Server Action |
| `dashboard/components/sidebar.tsx` | Modified | Add Tickets nav link (Ticket icon from lucide-react) |
| `dashboard/__tests__/lib/actions/ticket-actions.test.ts` | New | Vitest for auth + data fetch |
| `dashboard/__tests__/lib/actions/_test-helpers.ts` | Modified | Add `ticket` table case to `buildMockServiceClient` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DB column name mismatch (camelCase vs snake_case) | Low | Confirmed: migration 001 uses camelCase (`"ticketNumber"`, `"guildId"`, etc.) — matches types.ts and bot model exactly |
| Large ticket counts per guild | Low | Hard limit 50 in query, state as non-goal for v1 |
| Missing shadcn Badge/Table components | Low | Badge exists in shadcn; Table can use plain HTML table or install shadcn Table |

## Rollback Plan

Delete the three new files (`tickets/page.tsx`, `ticket-actions.ts`, `ticket-actions.test.ts`), revert sidebar.tsx link addition, and revert `_test-helpers.ts` ticket case. No schema or data changes.

## Dependencies

- shadcn Badge component (already available in `dashboard/components/ui/`)
- lucide-react `Ticket` icon (lucide-react already in package.json)

## Success Criteria

- [ ] `/guilds/{id}/tickets` page renders ticket stats (open/claimed/closed counts)
- [ ] Ticket list shows id, status badge, author, created_at, claimed_by (max 50)
- [ ] Non-admin users get auth error (verifyGuildAdmin blocks)
- [ ] Sidebar shows Tickets link with active state
- [ ] `vitest run` passes for ticket-actions tests
- [ ] No existing tests broken
