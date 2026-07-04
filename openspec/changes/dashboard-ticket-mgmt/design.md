# Design: Dashboard Ticket Management

## Technical Approach

Add a read-only Tickets page to the Next.js dashboard under the existing
authenticated guild route. The page remains a Server Component, calls one
self-contained Server Action, and renders pre-fetched data with shadcn `Card`
surfaces plus a page-local badge span because `dashboard/components/ui/badge.tsx`
does not currently exist.

This implements `dashboard-ticket-view` only: stats, a capped ticket list,
guild isolation, auth re-check, empty state, and sidebar navigation. No bot,
schema, ticket mutation, transcript, or pagination UI work is included.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Data boundary | Query in page directly; Server Action | `getTicketsForGuild(guildId)` Server Action | Copies the economy/greeting defense-in-depth pattern and keeps service-role reads behind auth. |
| Auth | Trust layout; re-check action | Copy local `verifyGuildAdmin` | Existing action files are self-contained; service-role reads must not rely only on route layout. |
| UI badge | Install shadcn Badge; local span | Local `StatusBadge` span | Badge is missing; local span preserves the 3-new-file rollback scope and avoids installing components during this read-only change. |
| Stats | SQL aggregate; JS reduce | JS reduce over max 50 rows | Simpler, testable, and bounded by the hard query limit. |
| Table | shadcn Table; plain table | Plain semantic table in `Card` | `Table` component is also absent; plain table avoids unrelated UI component additions. |

## Data Flow

```text
/guilds/[guildId]/tickets page
  └─ await params
  └─ getTicketsForGuild(guildId)
       ├─ createServerSupabaseClient().auth.getSession()
       ├─ createServiceClient().from("guild").select("active").eq("id", guildId).single()
       ├─ fetchUserGuilds(provider_token) + hasAdministratorPerm()
       └─ createServiceClient().from("ticket")
            .select("*")
            .eq("guildId", guildId)
            .order("createdAt", { ascending: false })
            .limit(50)
  └─ stats cards + ticket table / empty state
```

## File Changes

| File | Action | Description |
|---|---|---|
| `dashboard/lib/actions/ticket-actions.ts` | Create | Server Action with copied `verifyGuildAdmin` and read-only ticket query. |
| `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx` | Create | Server Component page with stats cards, table, status badges, and empty state. |
| `dashboard/__tests__/lib/actions/ticket-actions.test.ts` | Create | Vitest RED tests for auth, guild filter, order/limit chain, return shape, and empty data. |
| `dashboard/__tests__/lib/actions/_test-helpers.ts` | Modify | Add `ticketSelectResult` and a `ticket` table chain for `.select().eq().order().limit()`. |
| `dashboard/components/sidebar.tsx` | Modify | Import lucide `Ticket`; add `/guilds/${guildId}/tickets` nav item. |

## Interfaces / Contracts

`Ticket` and `TicketStatus` already exist in `dashboard/lib/types.ts:108-135`.
No type changes are needed.

```ts
type TicketListResult =
  | { data: Ticket[]; error: null }
  | { data: null; error: string };

export async function getTicketsForGuild(
  guildId: string
): Promise<TicketListResult>;
```

Action behavior:

- Unauthenticated, missing Discord token, inactive guild, or non-admin:
  `{ data: null, error: string }`.
- Supabase ticket query error: `{ data: null, error: `Database error: ...` }`.
- Success: `{ data: tickets ?? [], error: null }`.
- Query MUST be exactly:
  `.from("ticket").select("*").eq("guildId", guildId).order("createdAt", { ascending: false }).limit(50)`.

Page behavior:

- `params` is `Promise<{ guildId: string }>` per existing Next.js 15 pages.
- Compute counts from `tickets.filter((t) => t.status === status).length`.
- Render three cards: Open, Claimed, Closed.
- Render columns: Number, Status, Author, Created, Claimed By.
- `claimedBy === null` renders `—`.
- `createdAt` may use `new Date(createdAt).toLocaleString()`; no client state.
- Empty data renders a designed message: `No tickets yet`.
- Error renders a `Card` with the action error; no redirect.

Page structure sketch:

```tsx
<div className="space-y-6">
  <header>
    <h1>Tickets</h1>
    <p>Monitor support tickets for this guild.</p>
  </header>
  <section className="grid gap-4 md:grid-cols-3">{/* stats cards */}</section>
  <Card>
    <CardHeader>{/* title + description */}</CardHeader>
    <CardContent>{/* empty state or table */}</CardContent>
  </Card>
</div>
```

Action import set:

```ts
import { createServerSupabaseClient, createServiceClient } from "@/lib/supabase";
import { fetchUserGuilds, hasAdministratorPerm } from "@/lib/discord";
import type { Ticket } from "@/lib/types";
```

Status badge mapping:

| Status | Classes / visual intent |
|---|---|
| `open` | green/default: `bg-green-500/10 text-green-600 ring-green-500/20` |
| `claimed` | yellow/warning: `bg-yellow-500/10 text-yellow-600 ring-yellow-500/20` |
| `closed` | gray/secondary: `bg-muted text-muted-foreground ring-border` |
| unknown | default neutral classes; no crash |

Sidebar contract:

```ts
import { Ticket } from "lucide-react";

{ href: `/guilds/${guildId}/tickets`, label: "Tickets", icon: Ticket }
```

Lucide confirmation: `Ticket` exists and is importable from `lucide-react`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit RED | `getTicketsForGuild` rejects unauthenticated and non-admin users | Follow `economy-actions.test.ts`; mock session, Discord guilds, and service client. |
| Unit RED | Success query shape | Assert `from("ticket")`, `select("*")`, `eq("guildId", GUILD_ID)`, `order("createdAt", { ascending: false })`, `limit(50)`. |
| Unit RED | Return shape | Success returns `{ data: Ticket[], error: null }`; auth/db errors return `{ data: null, error }`. |
| Unit RED | Empty data | Mock `[]`; expect `{ data: [], error: null }`. Page empty state can be covered later with component/page test if harness exists. |
| Regression | Existing action tests | Run `cd dashboard && npm test`. |

`buildMockServiceClient` should expose table-specific chain mocks so tests can
inspect the ticket query rather than only testing mocked outcomes.

## Migration / Rollout

No migration required. The existing `ticket` table uses camelCase columns that
match `Ticket`. Rollout is a normal dashboard deploy.

Rollback: delete `tickets/page.tsx`, `ticket-actions.ts`, and
`ticket-actions.test.ts`; revert the sidebar link and `_test-helpers.ts` ticket
mock extension. No data cleanup is required.

## Risks

- **WARNING** `dashboard/components/ui/`: Badge is missing; use page-local span
  for this change or accept a 4th new file if apply chooses `shadcn add badge`.
- **WARNING** `dashboard/components/ui/`: Table is missing; design intentionally
  uses plain semantic table markup inside `Card`.
- **WARNING** `openspec/config.yaml:14-24`: project config still lists Python
  pytest defaults, but this dashboard change must use `cd dashboard && npm test`.

## Open Questions

- None blocking.
