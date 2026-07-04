# Design: Tickets Subsidiados

## Technical Approach

Extend the existing ticket stack without rewriting the open/close/panel flow: Migration 003 adds nullable ticket hierarchy plus staff notes; Python dataclasses mirror camelCase Supabase rows; `TicketService` owns all business validation; `TicketsCog` remains Discord I/O only; the Next.js RSC page renders the tree while small client leaves handle actions and notes.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| DB self-FK for `ticket.parentId` | Stronger integrity, but conflicts with project rule: Supabase Transaction Mode has no FK enforcement | Nullable UUID + service validation is mandatory. |
| Multi-level trees | More flexible, harder permissions/lifecycle | Reject sub-of-sub; v1 supports exactly one child level. |
| Persistent Discord buttons for reopen/transfer | Convenient, but require target ticket context outside deleted channels | Use slash commands for v1; keep persistent views limited to channel-local Claim/Close. |
| Dashboard interactivity in page | Simpler file count, larger client boundary | Keep `page.tsx` server-rendered; create client row actions/notes panel leaves. |
| Transfer audit as DB row | Spec says row, but no audit table exists in current schema | Use existing `LoggingService` audit embed unless tasks add an audit table. This is a blocker to clarify. |

## Data Flow

```text
/subticket create → TicketsCog → TicketService.create_subticket
  → validate parent exists/not self/not child/same guild
  → create Discord channel → Database.insert_ticket(parentId) → cache.add

Dashboard RSC → getTicketsForGuild(guildId) → build parent/child tree
  → Client action button → server action verifies admin → Supabase mutation → revalidatePath
```

## Migration 003 Contract

`migrations/003_subtickets_notes.sql` must be additive and idempotent:

```sql
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS "parentId" UUID;

CREATE TABLE IF NOT EXISTS ticket_note (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "ticketId" UUID NOT NULL,
    "authorId" TEXT NOT NULL,
    content     TEXT NOT NULL,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ticket_parent ON ticket ("parentId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket ON ticket_note ("ticketId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_created ON ticket_note ("ticketId", "createdAt" DESC);
```

No data backfill is required; existing tickets keep `parentId = null`.

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/003_subtickets_notes.sql` | Create | Add `ticket.parentId`, `ticket_note`, lookup indexes. |
| `bot/models/ticket.py` | Modify | Add `parent_id: str | None = None`, map `parentId` in `from_db_row`/`to_db_dict`. |
| `bot/models/ticket_note.py` | Create | `TicketNote(id, ticket_id, author_id, content, created_at)` dataclass with camelCase DB mapping. |
| `bot/core/database.py` | Modify | `insert_ticket(..., parent_id=None)`, `get_tickets_by_parent`, `insert/get/delete_ticket_note`; note list ordered newest-first and capped by caller. |
| `bot/services/ticket_service.py` | Modify | Add `create_subticket`, `reopen_ticket`, `transfer_ticket`, notes CRUD; duplicate check is skipped only when `parent_id` is set. |
| `bot/cogs/tickets.py` | Modify | Add `subticket` group and `reopen`, `transfer`, `note add/list/delete` hybrid commands, all `@is_mod()`. |
| `dashboard/lib/types.ts` | Modify | Add `Ticket.parentId` and `TicketNote`. |
| `dashboard/lib/actions/ticket-actions.ts` | Modify | Add `reopenTicket`, `transferTicket`, `getTicketNotes`, `addTicketNote`, `deleteTicketNote`; every action calls `verifyGuildAdmin`. |
| `dashboard/app/(authenticated)/guilds/[guildId]/tickets/page.tsx` | Modify | Build parent→children tree; orphan children degrade to top-level rows. |
| `dashboard/app/(authenticated)/guilds/[guildId]/tickets/_components/*.tsx` | Create | Client `TicketRowActions`, `TransferTicketButton`, `NotesPanel`; accessible labels, disabled/loading states, clear empty notes state. |

## Interfaces / Contracts

```python
async def create_subticket(parent_id: str, author_id: str, category_id: str | None, channel_id: str) -> Ticket
# Reject: parent missing, self-reference, parent.parent_id is not None, parent.guild_id mismatch.
async def reopen_ticket(ticket_id: str, guild: discord.Guild) -> Ticket
async def transfer_ticket(ticket_id: str, new_claimed_by: str, actor_id: str) -> Ticket
async def create_note(ticket_id: str, author_id: str, content: str) -> TicketNote
```

Dashboard action contracts return existing `ActionResult`; note fetch returns `{ data: TicketNote[]; error: string | null }`.

## Testing Strategy

| Layer | RED tests | Files |
|---|---|---|
| Migration | Existing data gets nullable `parentId`; `ticket_note` + indexes exist | `tests/test_migrations.py` |
| Models | Ticket parent serialization; TicketNote serialization | `tests/test_ticket_model.py` |
| Service | 4 FK rejections, valid subticket, duplicate carve-out, reopen channel/cache, transfer claimedBy+audit, notes CRUD/cap/ownership | `tests/test_ticket_service.py` |
| Cog | `/subticket create`, `/reopen`, `/transfer`, `/note add/list/delete` gated by `@is_mod()` | `tests/test_tickets_cog.py` |
| Dashboard actions | Admin verification for reopen/transfer/notes; mutation query shape | `dashboard/__tests__/lib/actions/ticket-actions.test.ts` |
| Dashboard page | Tree render, orphan fallback, action visibility, notes empty/list/add/delete panel calls | `dashboard/__tests__/app/tickets-page.test.tsx` |

## UI Guidance

Keep the dashboard a functional admin tool: preserve existing Card/Button tokens, use indentation and connector spacing for hierarchy, text status labels not color alone, button copy with explicit verbs (`Reopen`, `Transfer`, `Add note`), loading/disabled states, keyboard-focusable collapsible notes panels, and a real empty state: “No staff notes yet.” Avoid nested cards inside rows.

## Migration / Rollout

Ship schema/model first, then bot service/commands, then dashboard. Rollback: `DROP TABLE IF EXISTS ticket_note; ALTER TABLE ticket DROP COLUMN IF EXISTS "parentId";` and revert code. Critical guard is service-layer parent validation because DB does not protect `parentId`.

## Non-goals

No multi-level sub-tickets, Discord threads, ticket system rewrite, notifications, or notes pagination beyond the v1 cap of 50.

## Open Questions

- [ ] Spec says transfer inserts an audit log row, but the current schema has no audit table. Confirm whether existing `LoggingService` audit embeds satisfy this, or add a future `ticket_audit_log` table.
