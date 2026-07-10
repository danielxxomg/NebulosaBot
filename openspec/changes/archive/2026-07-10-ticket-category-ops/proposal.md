# Proposal: Ticket Category Operations

## Intent

Add two missing ticket lifecycle capabilities: (1) allow staff to change a ticket's category after creation, and (2) enforce a one-open-ticket-per-user-per-category limit to prevent abuse. Today, once a ticket is created, its category is immutable — staff must close and reopen to recategorize. There is also no guard against a user opening unlimited tickets in the same category.

## Scope

### In Scope
- "Edit Category" button in `TicketActionsView` (staff-only, button + ephemeral category select)
- Per-user-per-category open ticket limit (application-level check in `TicketService.create_ticket()`)
- DB query for counting user's open tickets in a category
- Pure invariant function for the limit check
- Channel rename on category edit

### Out of Scope
- Multi-panel support (single panel, single channel only)
- Dashboard changes (bot-only)
- DB migration for unique index (app-level check only for now)
- Category edit from dashboard or by ticket author

## Capabilities

### New Capabilities

None — all changes modify existing capabilities.

### Modified Capabilities

- `ticket-service`: Add `edit_ticket_category()` method (DB update + channel rename) and per-user-per-category guard in `create_ticket()` with subticket carve-out
- `ticket-invariants`: Add `check_one_ticket_per_user_per_category()` pure invariant (skip when `parent_id is not None`, skip when `categoryId IS NULL`)
- `ticket-views`: Add "Edit Category" button to `TicketActionsView` gated by `@is_mod()`, triggering ephemeral category select dropdown

## Approach

**Edit Category**: Add a third button ("Edit Category") to `TicketActionsView` alongside Claim/Close. On click: check `@is_mod()`, fetch active categories, show ephemeral `_CategorySelect` dropdown (reusing existing pattern). On selection: update `categoryId` in DB via new `edit_ticket_category()` in `TicketService`, rename channel via `sanitize_channel_name()`. Catches `discord.HTTPException` on rate-limited renames.

**Per-User-Per-Category Limit**: Add `check_one_ticket_per_user_per_category()` to `ticket_invariants.py` as a pure function. Add `count_user_open_tickets_in_category()` to `ticket_db.py`. Guard in `TicketService.create_ticket()` before insert. Skip check when `parent_id is not None` (subticket carve-out) or `categoryId IS NULL` (unlimited uncategorized tickets). Follows existing app-level FK validation pattern (Supabase Transaction Mode).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modified | Add `edit_ticket_category()`, add per-user-per-category guard in `create_ticket()` |
| `bot/services/ticket_invariants.py` | Modified | Add `check_one_ticket_per_user_per_category()` pure invariant |
| `bot/core/db/ticket_db.py` | Modified | Add `count_user_open_tickets_in_category()` query |
| `bot/views/tickets.py` | Modified | Add "Edit Category" button to `TicketActionsView` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Discord rate limit on channel rename (2/10min) | Low | Catch `discord.HTTPException`, log warning, proceed with DB update |
| Race condition on per-user-per-category check | Low | Negligible for Discord bot UX; DB unique index can be added later if observed |

## Rollback Plan

Remove the "Edit Category" button from `TicketActionsView`, revert `edit_ticket_category()` from `TicketService`, and remove the per-user-per-category guard from `create_ticket()`. No DB migration to revert — all changes are application-level. Channel names can be manually corrected if needed.

## Dependencies

- None (no new libraries or migrations)

## Success Criteria

- [ ] Staff can change a ticket's category via button in ticket channel
- [ ] Channel name updates to reflect new category
- [ ] User cannot open a second ticket in the same category while one is open
- [ ] Subtickets bypass the per-user-per-category limit
- [ ] Tickets with `categoryId IS NULL` are exempt from the limit
