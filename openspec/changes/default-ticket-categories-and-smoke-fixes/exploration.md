# Exploration: Default Ticket Categories and Smoke Fixes

## Current State

### Ticket System Architecture

The ticket system has **two distinct concepts that share a dangerously similar name**:

| Concept | DB Location | What it is | Example |
|---------|-------------|------------|---------|
| **Ticket Category Channel** | `guild.ticketCategoryId` | Discord `CategoryChannel` snowflake — the parent channel where new ticket text channels are created | `1518737156984668260` (a Discord channel ID) |
| **Ticket Category Label** | `ticket_category` table rows | UI labels shown in the dropdown when a user clicks "Open Ticket" | UUID like `a1b2c3d4...`, with name "Soporte General", emoji, description, position |

The "Not Configured" error fires at `bot/cogs/tickets.py:408` when `config.ticket_category_id` (the Discord CategoryChannel) is `None`. The user's guild `1518709129403695154` has:
- `ticketCategoryId = NULL` → **this is the root cause** of "Not Configured"
- 5 active `ticket_category` label rows (Soporte General, Tienda, Reportes, Apelaciones, Administracion) → these exist and work fine

The user created the label rows but never set the Discord CategoryChannel. These are two completely separate configuration steps, and nothing in the UX makes this clear.

### Guild Join / Startup Flow

- `on_guild_join` → `GuildService.on_guild_join()` → inserts a `GuildConfig` with defaults (prefix=`nb!`, language=`es`). **No default ticket categories are seeded.**
- `on_ready` → `GuildService.ensure_guild_exists()` → `INSERT ... ON CONFLICT DO NOTHING`. Only ensures the guild row exists. **No category seeding.**
- Ticket categories are only created via `/create_category` (manual admin command).

### Realtime Publication

Currently published tables: `guild`, `greeting_config`, `ticket`, `ticket_note`.
**`ticket_category` is NOT published.** The bot queries `ticket_category` directly from DB on every "Open Ticket" button click (no caching).

### XP Listener FK Error

The `member_userId_fkey` error occurs when `economy_service.gain_xp()` calls `update_member_xp()` which upserts into the `member` table. If a `user` table exists with FK enforcement on `member.userId`, the first message from a new user fails because no `user` row exists yet. This is a **separate issue** from tickets — it's a data integrity / schema concern.

### Realtime Warnings

- "No CDC events received" — the watchdog timer (`realtime.py:679`) fires 30s after SUBSCRIBED when `_event_count == 0`. This is expected on a quiet bot with no dashboard writes happening.
- "CDC event for None could not resolve a guild_id — skipping" — fires when `_extract_guild_id()` returns `None`. This happens for tables not in the extraction map (like `ticket_category` if it were published without a mapping), or for `ticket_note` events where the ticket_id can't be resolved to a guild.

## Affected Areas

- `bot/cogs/tickets.py` — `_CategorySelect.callback` (line 408: the "Not Configured" check); `open_ticket_button` (category label query); `create_category` / `delete_category` commands
- `bot/models/guild.py` — `GuildConfig.ticket_category_id` field (naming collision with `ticket_category` table)
- `bot/services/guild_service.py` — `on_guild_join()` and `ensure_guild_exists()` — no category seeding
- `bot/bot.py` — `on_guild_join` and `on_ready` lifecycle hooks
- `bot/core/database.py` — `insert_ticket_category()`, `get_ticket_categories()`, `ensure_guild_exists()`
- `bot/core/realtime.py` — `SUBSCRIBED_TABLES` tuple (line 48), `_extract_guild_id()` (line 77)
- `bot/services/economy_service.py` — `gain_xp()` triggers the FK error via `update_member_xp()`
- `bot/listeners/xp_listener.py` — `on_message` calls `gain_xp()` without guarding user existence

## Approaches

### 1. Seeding Default Categories — Options

#### Option A: Seed on `on_guild_join` + backfill on `on_ready`

- **How**: Extend `GuildService.on_guild_join()` and `ensure_guild_exists()` to also insert 5 default `ticket_category` rows (INSERT ... ON CONFLICT DO NOTHING).
- **Pros**: Simple, covers both new and existing guilds, no DB migration needed, follows existing patterns.
- **Cons**: Backfill on `on_ready` runs every startup (cheap query though). If admin deletes a category, backfill won't re-add it (ON CONFLICT DO NOTHING on a unique constraint — but there's no unique constraint on `(guildId, name)` currently).
- **Effort**: Low

#### Option B: DB trigger/function

- **How**: A Postgres trigger on `guild` INSERT that auto-creates 5 `ticket_category` rows.
- **Pros**: Guaranteed at DB level, works regardless of bot state.
- **Cons**: Harder to test, harder to update defaults, requires migration, Supabase dashboard debugging is harder.
- **Effort**: Medium

#### Option C: Hybrid — bot-level seeding + unique constraint

- **How**: Add a unique constraint on `(guildId, name)` to `ticket_category`. Seed in `on_guild_join` + `on_ready` backfill. ON CONFLICT DO NOTHING ensures idempotency and respects admin deletions (if admin deletes and re-creates with same name, the new one wins).
- **Pros**: Robust idempotency, admin can delete defaults without them coming back, DB enforces uniqueness.
- **Cons**: Requires a migration for the unique constraint.
- **Effort**: Low-Medium

**Recommendation: Option C** — it's the cleanest. The unique constraint is missing anyway (the `create_category` command checks for duplicates in application code, but there's no DB-level enforcement).

### 2. "Not Configured" Error Fix

The error is **correct behavior** — the Discord CategoryChannel must be configured by an admin. The fix is:
1. Improve the error message to explain the TWO separate configuration steps.
2. Consider adding a `/setup_tickets` wizard or at minimum clearer docs.

### 3. Naming Clarity

Rename `guild.ticketCategoryId` to `guild.ticketDiscordCategoryId` (or similar) to make it unambiguous. This is a DB column rename + code update — a bigger change that could be a separate follow-up.

### 4. `ticket_category` in Realtime Publication

**Current state**: Not published, not needed — the bot always queries DB fresh.
**When to add**: Only if we cache the category list. Currently the query is lightweight (one select per guild, on button click). Adding to Realtime without caching provides zero benefit.
**Recommendation**: Skip for now. If caching is added later, publish then.

### 5. XP FK Error — Separate Fix

This is unrelated to tickets. The `member` table's `userId` column has an FK to a `user` table. The `update_member_xp()` upsert fails when the user doesn't exist in `user` table yet. Two options:
- **Option A**: Remove the FK constraint (if the `user` table is not used/needed).
- **Option B**: Ensure a `user` row exists before upserting into `member` (application-level FK validation, matching the project's pattern from AGENTS.md).
- **Effort**: Low for either.

### 6. Realtime Warnings — Separate Fix

- "No CDC events received" → Expected on quiet bots. Could lower the log level from WARNING to INFO, or increase the watchdog delay. Not a bug.
- "CDC event for None guild_id" → This fires for `ticket_note` events where the ticket can't be resolved. If it's firing for guild PATCH events, check that `_extract_guild_id` handles the `guild` table correctly (it does — line 87 returns `record.get("id")`). The log after guild PATCH suggests the CDC payload for a guild update might have `id=None` in certain edge cases. Worth investigating but low priority.
- **Effort**: Low (log level change) or investigate-and-fix.

## Recommendation

### Change Scope: `default-ticket-categories-and-smoke-fixes`

**Core work** (this change):
1. Add unique constraint on `ticket_category(guildId, name)` via migration.
2. Create a `DEFAULT_TICKET_CATEGORIES` constant (5 entries: Soporte General, Tienda, Reportes, Apelaciones, Administracion) with emojis and descriptions.
3. Add `seed_default_categories(guild_id)` method to `GuildService` or `Database` — inserts 5 rows with ON CONFLICT DO NOTHING.
4. Call `seed_default_categories()` from `on_guild_join()` and `on_ready` backfill.
5. Improve the "Not Configured" error message to guide the admin.
6. Fix the XP FK error (investigate whether `user` table FK should be removed or user row should be ensured).

**Deferred** (separate changes):
- Rename `guild.ticketCategoryId` to clearer name (breaking change, needs careful migration).
- Add `ticket_category` to Realtime (only if caching is added).
- Realtime watchdog tuning (cosmetic).

## Risks

- **Unique constraint migration**: Adding `(guildId, name)` unique constraint could fail if duplicate names already exist in production. Need to check for duplicates first.
- **Default category names in Spanish**: The 5 defaults are Spanish. If the bot ever supports other languages, these would need localization. For now, matches the `language=es` default.
- **Admin intent on re-seed**: With ON CONFLICT DO NOTHING, if admin deletes a default category, it won't come back on restart. This is the desired behavior per the user's request.
- **XP FK error scope**: Need to verify whether the `user` table actually exists and has FK enforcement, or if this is a Supabase Transaction Mode issue (no FK enforcement per AGENTS.md). If there's no real FK, the error might be something else.

## Ready for Proposal

**Yes** — the exploration is complete. The orchestrator should tell the user:

1. The "Not Configured" error is because `guild.ticketCategoryId` (Discord CategoryChannel) is NULL — the admin needs to set it via the dashboard or a command. The 5 category labels they created are separate and working fine.
2. The recommended approach is bot-level seeding with a DB unique constraint (Option C).
3. The XP FK error and Realtime warnings are separate smoke fixes that can be bundled or split.
4. A proposal can proceed with scope: default category seeding + improved error message + XP FK fix + optional Realtime warning tuning.
