# Proposal: Tickets Subsidiados

## Intent

The current ticket model is flat — no parent-child relationship, no reopen, no transfer, no staff notes. Staff cannot derive sub-tickets from a parent, cannot reopen a closed ticket (channel is deleted), cannot transfer claim ownership, and have no private annotation mechanism. This blocks operational workflows that require ticket derivation, recovery, reassignment, and internal documentation.

## Scope

### In Scope
- **Sub-tickets**: staff creates a child ticket derived from a parent (1 level deep). Self-referential `parentId UUID` on `ticket` table (nullable). Child has own channel, claimedBy, transcript, lifecycle.
- **Reopen**: closed → open, creates a NEW Discord channel (old deleted on close), restores category/permissions.
- **Transfer**: mutate `claimedBy` + audit log entry. No new channel.
- **Notes**: new `ticket_note` table (staff-only, NOT visible to ticket opener). CRUD via bot commands and dashboard.
- **Bot commands**: `/subticket create`, `/reopen`, `/transfer`, `/note add`.
- **Dashboard**: extend tickets page — sub-ticket tree view + client components for reopen/transfer/notes buttons + notes panel.
- **Migration**: `003_subtickets_notes.sql` — add `parentId` to ticket, create `ticket_note` table.

### Out of Scope
- Multi-level sub-tickets (sub-of-sub). Enforced app-level: reject if parent already has a parentId.
- Thread-based sub-tickets (discord.py threads break permission isolation model).
- Rewrite of existing open/close/transcript/panel flows.
- Notification system for note creation or transfer events.
- Pagination for notes panel (v1 cap at 50 per ticket).

## Capabilities

### New Capabilities
- `ticket-subsidiados`: Sub-ticket derivation (parentId self-ref), reopen (new channel), transfer (claimedBy mutation), and staff notes (ticket_note table). Covers bot commands, service layer, and dashboard client components.

### Modified Capabilities
- `initial-schema`: Migration adds `parentId UUID` nullable FK to `ticket` table + new `ticket_note` table.
- `ticket-service`: Extend `create_ticket` to accept optional `parentId`; add `reopen_ticket`, `transfer_ticket` methods.
- `ticket-model`: Add `parent_id: str | None` field to `Ticket` dataclass.
- `dashboard-ticket-view`: Extend page with sub-ticket tree rendering, action buttons (reopen/transfer/notes), notes panel.

## Approach

- **Schema**: `parentId UUID` nullable self-ref on `ticket`. App-level FK validation (Supabase Transaction Mode has no FK enforcement): reject self-referential, reject sub-of-sub, reject cross-guild. New `ticket_note` table: `id UUID PK`, `ticketId UUID FK`, `authorId TEXT`, `content TEXT`, `createdAt TIMESTAMPTZ`.
- **Reopen**: `TicketService.reopen_ticket()` — create new Discord channel with same category/permissions, update ticket `channelId` + status → `open`, clear `closedAt`. Old channel already deleted on close.
- **Transfer**: `TicketService.transfer_ticket()` — update `claimedBy`, insert audit log row.
- **Notes**: `Database.insert_ticket_note()`, `get_ticket_notes()`, `delete_ticket_note()`. Staff-only (`@is_mod()`).
- **"One open ticket per user per category"** rule: carve-out for sub-tickets (child tickets exempt from this constraint).
- **Cache invalidation**: `_ticket_channel_cache` updated on reopen (add new channel ID, old was removed on close).
- **Dashboard**: RSC page renders parent→child tree. Client components (`'use client'`) for reopen/transfer/notes action buttons. Notes panel as a collapsible section per ticket row.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/003_subtickets_notes.sql` | New | parentId column + ticket_note table |
| `bot/models/ticket.py` | Modified | Add `parent_id` field |
| `bot/models/ticket_note.py` | New | TicketNote dataclass |
| `bot/core/database.py` | Modified | Add ticket_note CRUD + parentId-aware insert_ticket |
| `bot/services/ticket_service.py` | Modified | Add reopen_ticket, transfer_ticket, create_subticket |
| `bot/cogs/tickets.py` | Modified | Add /subticket, /reopen, /transfer, /note slash commands |
| `dashboard/lib/types.ts` | Modified | Add parentId to Ticket, add TicketNote interface |
| `dashboard/lib/actions/ticket-actions.ts` | Modified | Add reopenTicket, transferTicket, notes CRUD actions |
| `dashboard/app/.../tickets/page.tsx` | Modified | Sub-ticket tree + action buttons + notes panel |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| App-level FK validation bypass (no DB FK enforcement) | **Critical** | Validate parentId exists, is not self, has no parent itself, same guild — all in service layer before insert |
| Reopen: category channel deleted since close | Medium | Fallback to guild's default ticket category; error if none configured |
| Cache invalidation miss on reopen | Medium | Explicit `_ticket_channel_cache.add()` in reopen_ticket |
| "One open ticket per user" blocks sub-tickets | High | App-level carve-out: skip constraint when parentId is set |
| Dashboard RSC→client boundary complexity | Medium | Keep tree rendering in RSC; extract action buttons to isolated `'use client'` components |
| Permissions: notes visible to non-staff | Medium | Bot commands gated by `@is_mod()`; dashboard actions gated by `verifyGuildAdmin` |

## Rollback Plan

1. Run `DROP TABLE IF EXISTS ticket_note; ALTER TABLE ticket DROP COLUMN IF EXISTS parentId;` to revert schema.
2. Revert changes to `ticket.py`, `ticket_service.py`, `database.py`, `tickets.py`.
3. Revert dashboard changes to `page.tsx`, `ticket-actions.ts`, `types.ts`.
4. Delete `ticket_note.py` model.
5. No data loss — parentId and ticket_note are additive; existing tickets unaffected.

## Dependencies

- None beyond existing stack (discord.py 2.x, Supabase, Next.js 15, shadcn/ui).

## Success Criteria

- [ ] Staff can create a sub-ticket from an existing ticket via `/subticket create`
- [ ] Sub-ticket has own Discord channel, independent lifecycle, linked parentId
- [ ] App-level validation rejects self-ref, sub-of-sub, cross-guild parentId
- [ ] `/reopen` creates a new channel for a closed ticket, restores open status
- [ ] `/transfer` changes claimedBy and logs the transfer
- [ ] `/note add` creates a staff-only note (not visible to ticket opener)
- [ ] Dashboard shows parent→child tree + action buttons + notes panel
- [ ] `uv run pytest` passes (bot tests)
- [ ] `vitest run` passes (dashboard tests)
- [ ] Migration 003 applies cleanly on existing data

## Size Estimate

~940 lines total: bot ~480, dashboard ~260, tests ~200. **EXCEEDS 400-line PR budget** — flag for `size:exception` approval or split into chained PRs at apply phase (e.g., schema+model → bot service+commands → dashboard).
