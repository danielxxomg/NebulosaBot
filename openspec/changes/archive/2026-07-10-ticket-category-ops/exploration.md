## Exploration: ticket-category-ops

### Current State

**Ticket creation flow**: `TicketPanelView` → `_CategorySelect` (ephemeral dropdown) → `TicketIntakeModal` → `_create_ticket_after_modal()` → `TicketService.create_ticket_channel()`. The category is a **ticket_category** row (label/schema), NOT a Discord category channel. The Discord category channel is resolved from guild config (`config.ticket_category_id`).

**Category model**: `TicketCategory` dataclass with `id`, `guildId`, `name`, `emoji`, `description`, `position`, `active`, `field_definitions`. Stored in `ticket_category` table. Guild-scoped CRUD exists via `TicketCategoryDBMixin`.

**Ticket model**: `Ticket` dataclass with `categoryId` (FK to ticket_category, nullable). No unique constraint on `(authorId, categoryId, status)`.

**Staff interactions**: `TicketActionsView` has Claim and Close buttons. Commands: `/unclaim`, `/transfer`, `/reopen`, `/subticket create`, `/note add|list|delete`. All gated by `@is_mod()`.

**Per-user-per-category limit**: **NOT currently enforced anywhere**. The `create_ticket()` and `create_ticket_channel()` methods perform no duplicate check. `count_open_tickets_by_category(guild_id, category_id)` exists but is only used by `/delete_category` to prevent orphaning tickets — it counts ALL open tickets in a category, not per-user.

**"Edit category" does not exist**: No command, button, or service method to change a ticket's `categoryId` after creation.

### Affected Areas

- `bot/services/ticket_service.py` — needs `edit_ticket_category()` method and per-user-per-category guard in `create_ticket()`
- `bot/services/ticket_invariants.py` — needs `check_one_ticket_per_user_per_category()` pure invariant
- `bot/core/db/ticket_db.py` — needs `count_user_open_tickets_in_category(guild_id, author_id, category_id)` query
- `bot/views/tickets.py` — needs "Edit Category" button in `TicketActionsView` (or a new view)
- `bot/cogs/tickets.py` — may need `/edit_category` command as alternative entry point
- `bot/models/ticket.py` — no changes needed (already has `category_id`)
- `bot/core/db/ticket_category_db.py` — no changes needed (CRUD exists)
- `openspec/specs/ticket-invariants/spec.md` — delta spec for new invariants
- `openspec/specs/ticket-service/spec.md` — delta spec for edit_category + duplicate guard

### Approaches

#### 1. Edit Category: Button in TicketActionsView + Category Select

Add an "Edit Category" button to `TicketActionsView` (alongside Claim/Close). On click:
1. Check `@is_mod()` (staff only, per product decision)
2. Fetch active categories, show ephemeral `_CategorySelect` dropdown
3. On selection: update `categoryId` in DB, rename channel via `sanitize_channel_name()`, optionally move channel to a new Discord category if the category maps to one

- **Pros**: Consistent with existing panel UX pattern (dropdown → action), visible in every ticket channel, no new command needed
- **Cons**: Adds a third button to the actions view (Discord allows up to 5 per row, so fine), requires the view to remember the guild_id for category resolution
- **Effort**: Low

#### 2. Edit Category: Slash Command `/edit_category_on_ticket`

Add a hybrid command that accepts `category_id` (required). Resolves ticket by current channel, validates staff, updates DB + renames.

- **Pros**: Explicit, discoverable via slash command autocomplete
- **Cons**: Requires typing UUIDs or implementing autocomplete, less discoverable than a button for per-ticket actions, product decision says "button or command in the ticket channel" — a button is more natural
- **Effort**: Low

#### 3. Per-User-Per-Category Limit: DB Unique Index

Add a partial unique index: `CREATE UNIQUE INDEX ... ON ticket ("guildId", "authorId", "categoryId") WHERE status IN ('open', 'claimed')`. This is the strongest enforcement — DB-level guarantees no duplicates even under race conditions.

- **Pros**: Bullet-proof against race conditions, zero application code for the check itself
- **Cons**: Supabase Transaction Mode may not enforce partial unique indexes the same way; requires migration; error handling on unique violation needs to be user-friendly; does NOT apply when `parentId IS NOT NULL` (carve-out), so the partial index needs `AND "parentId" IS NULL`
- **Effort**: Medium

#### 4. Per-User-Per-Category Limit: Application-Level Check

Add a `check_one_ticket_per_user_per_category()` invariant in `ticket_invariants.py` and a `count_user_open_tickets_in_category()` DB query. Check before `create_ticket()` in the service layer.

- **Pros**: Follows existing architecture pattern (app-level FK validation per AGENTS.md), pure function testable, integrates naturally with the subticket carve-out (`if parent_id is not None: skip`)
- **Cons**: Race condition window between check and insert (two concurrent creates for same user+category could both pass the check)
- **Effort**: Low

#### 5. Hybrid: App Check + DB Constraint

Application-level check for user-friendly error messages + partial unique index as safety net. The app check provides the UX; the DB constraint catches races.

- **Pros**: Best of both worlds — friendly errors + no duplicates
- **Cons**: More code, two enforcement points to maintain
- **Effort**: Medium

### Recommendation

**Edit Category**: **Approach 1 (Button in TicketActionsView)**. It's the most natural UX — staff see the button in every ticket channel, consistent with Claim/Close pattern. Add it as a third button with `@is_mod()` gate. The category select dropdown pattern already exists in `_CategorySelectView`.

**Per-User-Per-Category Limit**: **Approach 4 (Application-Level Check)**. The existing codebase explicitly uses app-level FK validation (AGENTS.md: "Application-level FK validation — Supabase Transaction Mode has no FK enforcement"). Follow the same pattern. The race condition window is negligible for a Discord bot (users click buttons, not automated scripts). The subticket carve-out is clean: `if parent_id is not None: skip check`.

### Risks

1. **Channel rename on category edit**: Discord rate limits channel renames (2 per 10 min per channel). If a staff member rapidly edits categories, renames may fail. Mitigation: catch `discord.HTTPException` and log warning (same pattern as existing `create_ticket_channel` rename).

2. **Category deletion while tickets reference it**: Already handled — `/delete_category` checks `count_open_tickets_by_category > 0` and rejects. No new risk.

3. **Race condition on per-user-per-category check**: Two users clicking "Open Ticket" for the same category simultaneously could both pass the app-level check. The insert retry loop (`MAX_RETRIES = 3`) handles insert conflicts but NOT the per-user check. Mitigation: accept the negligible risk OR add the DB partial unique index as a safety net (Approach 5). I recommend starting with Approach 4 and adding the DB index later if races are observed in production.

4. **Edit category changes channel name semantics**: The channel name includes the category slug. Changing `categoryId` means the channel name no longer matches the category label stored on the ticket row. This is cosmetic, not functional. The rename handles it.

5. **No `categoryId` on some tickets**: `categoryId` is nullable. The per-user-per-category check should treat `NULL` as "no category" — a user can have unlimited tickets with `categoryId IS NULL`. The edit-category flow should always set a non-null `categoryId`.

### Ready for Proposal

**Yes**. The exploration is complete. Key decisions are clear:
- Edit category = button in `TicketActionsView` gated by `@is_mod()`
- Per-user-per-category limit = app-level check in `TicketService.create_ticket()` with carve-out for subtickets
- Channel rename on category edit uses existing `sanitize_channel_name()` pattern

The orchestrator can proceed to `sdd-propose`.
