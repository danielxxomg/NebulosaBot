# Proposal: Phase 3 — Tickets Module

## Intent

Guilds lack a structured support system. Users open ad-hoc channels or DMs for help, losing context and accountability. This phase adds a full ticketing system: categorized panels, sequential tickets, staff claim/close workflow, HTML transcripts, and auto-close on inactivity.

## Scope

### In Scope
- TicketService: create, close, claim, sequential numbering (MAX+retry), auto-close (48h)
- TicketCategory model + migration 002 (`ticket_category` table)
- TicketPanelView: persistent view with category dropdown + open button
- TicketActionsView: close/claim buttons per ticket channel
- TranscriptService: self-contained HTML generation, upload to log channel
- AutoCloseTask: `@tasks.loop(hours=1)` checking stale tickets
- TicketsCog: `/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category`
- Panel persistence: `ticketPanelMessageId` + `ticketPanelChannelId` columns on guild table
- `on_message` listener for `lastActivity` updates (cached ticket channel set)

### Out of Scope
- Ticket transfer between users
- Multi-panel per guild
- External transcript hosting (CDN beyond Discord attachments)
- Ticket analytics/dashboard integration
- Edit category command (deferred — create/delete sufficient for MVP)

## Capabilities

### New Capabilities
- `ticket-service`: Create/close/claim lifecycle, sequential numbering, auto-close task
- `ticket-views`: Persistent panel view (category select + open) and per-ticket action view (close/claim)
- `transcript-service`: HTML transcript generation from channel history, upload to log channel
- `ticket-commands`: Admin/mod slash commands for panel deployment and category management
- `ticket-category-model`: TicketCategory dataclass with CRUD and guild-scoped ordering

### Modified Capabilities
- `initial-schema`: Migration 002 adds `ticket_category` table + guild panel columns
- `guild-config`: Guild table gains `ticketPanelMessageId` and `ticketPanelChannelId` nullable columns

## Approach

Follow existing patterns: services take `(db, cache)` with `__slots__`, models are dataclasses with `from_db_row()`/`to_db_dict()`, cog uses `async def setup(bot)`. Sequential numbering via MAX+1 with optimistic retry (3 attempts). Panel stored in guild table (1:1). Transcript as inline-CSS HTML uploaded to Discord CDN. Auto-close via hourly loop with 48h threshold.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/models/ticket_category.py` | New | TicketCategory dataclass |
| `bot/services/ticket_service.py` | New | Create/close/claim/numbering |
| `bot/services/transcript_service.py` | New | HTML generation + upload |
| `bot/cogs/tickets.py` | New | Commands, views, auto-close task |
| `bot/core/database.py` | Modified | Ticket + category CRUD, stale query |
| `bot/bot.py` | Modified | Init services, register views, load cog |
| `migrations/002_ticket_categories.sql` | New | ticket_category table + guild panel columns |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Race condition on ticket numbering | Low | Optimistic retry (3 attempts); upgrade to DB sequence if needed |
| `on_message` overhead | Medium | Cached ticket channel set for O(1) lookup; early return |
| Transcript exceeds 25MB Discord limit | Low | Cap at 5000 messages; split if needed |
| Panel message deleted externally | Medium | Detect on startup, log warning, allow re-creation via command |

## Rollback Plan

1. Remove tickets cog from `bot.py` extension list
2. Drop `ticket_category` table and guild panel columns via reverse migration
3. Existing `ticket` table unchanged — no data loss
4. Persistent views stop registering on restart (no code = no views)

## Dependencies

- Migration 001 must be applied (ticket table already exists)
- Guild config must have `ticketCategoryId` set (Discord category for channels)

## Success Criteria

- [ ] User opens ticket via panel → channel created with correct permissions
- [ ] Staff claims ticket → status updates, embed sent
- [ ] Ticket closed → HTML transcript uploaded to log channel, channel deleted
- [ ] Stale tickets auto-closed after 48h inactivity
- [ ] Panel persists across bot restarts

## Decisions (from Proposal Question Round)

| Question | Answer |
|----------|--------|
| Transcript scope | All messages, cap 5000 |
| Auto-close warning | No — silent close at 48h |
| Ticket limits | No limit for MVP |
| Category mgmt | Create + delete only |
| Transcript destination | Same logChannelId |
