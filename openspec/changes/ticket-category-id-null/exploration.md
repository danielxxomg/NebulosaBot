## Exploration: ticket-category-id-null

### Current State

The ticket system requires a Discord `CategoryChannel` (stored as `ticket_category_id` in the `guild` table) to create ticket channels. This field:

- **Defaults to `None`** in `GuildConfig` (`bot/models/guild.py:21`)
- **Is never set by `on_guild_join()`** — only `prefix` and `language` are initialized (`bot/services/guild_service.py:138`)
- **Has NO bot command to set it** — no `/setup`, no `/config`, no `/set_ticket_category` exists
- **Can only be set via the web dashboard** (`dashboard/lib/actions/guild-actions.ts:86-119`)

When `ticket_category_id` is `None`, three flows are blocked:

1. **Ticket creation** — "Open Ticket" button → category select → callback checks `config.ticket_category_id` → "Not Configured" error (`bot/cogs/tickets.py:377-384`)
2. **Sub-ticket creation** — `/sub_ticket` command checks same field → "Not Configured" error (`bot/cogs/tickets.py:1172-1178`)
3. **Ticket reopen** — `ticket_service.reopen_ticket()` calls `_resolve_ticket_category()` → `ValueError` if `None` (`bot/services/ticket_service.py:460-464`)

**Key distinction**: `ticket_category_id` (Discord CategoryChannel snowflake) is DIFFERENT from `TicketCategory` (DB labels like "Support", "Bug Report"). The `/create_category` command creates `TicketCategory` records but does NOT set `ticket_category_id`. Both must be configured for tickets to work.

### Affected Areas

- `bot/cogs/tickets.py:377-384` — "Open Ticket" callback blocks on `None` ticket_category_id
- `bot/cogs/tickets.py:1172-1178` — `/sub_ticket` command blocks on `None` ticket_category_id
- `bot/services/ticket_service.py:460-464` — `reopen_ticket()` raises ValueError on `None`
- `bot/services/ticket_service.py:525-543` — `_resolve_ticket_category()` helper returns `None`
- `bot/models/guild.py:21` — `ticket_category_id: str | None = None` default
- `bot/services/guild_service.py:129-153` — `on_guild_join()` only sets prefix+language
- `dashboard/app/(authenticated)/guilds/[guildId]/config/page.tsx:78-83` — dashboard config form (hint says "UUID" but should say "Discord Category Channel ID")
- `dashboard/lib/actions/guild-actions.ts:86-119` — dashboard server action (validates as snowflake, correct)

### Approaches

#### 1. `/setup` Wizard Command (Option A)

Add a hybrid command `/setup` (gated with `@is_admin()`) that walks the admin through configuring ticket_category_id, mod_role_id, log_channel_id, and language in one guided flow.

- **Pros**: Single entry point for all config; discoverable; can validate Discord IDs exist before saving; uses `t()` for i18n
- **Cons**: More complex implementation (modal or multi-step interaction); must handle partial completion; admin might not know Discord IDs upfront
- **Effort**: Medium-High
- **AGENTS.md compliance**: hybrid_command ✓, ephemeral for slash ✓, permission check ✓, no hardcoded IDs ✓, guild-scoped ✓

#### 2. Auto-Create Default Category on Guild Join (Option B)

In `on_guild_join()`, after creating the default config, auto-create a Discord CategoryChannel named "Tickets" and save its ID to `ticket_category_id`.

- **Pros**: Zero-config for basic use; tickets work immediately after bot join
- **Cons**: Requires `Manage Channels` permission (may not be granted); creates channel without admin consent; naming may conflict with existing channels; doesn't educate admin about customization
- **Effort**: Low
- **AGENTS.md compliance**: Needs bot to have Manage Channels permission; no hardcoded IDs ✓ (channel name could be configurable)

#### 3. Fallback — Auto-Create on Demand (Option C)

When `ticket_category_id` is `None` and a user tries to open a ticket, auto-create a "Tickets" CategoryChannel on demand, save it to the guild config, and proceed.

- **Pros**: Self-healing; works even if admin forgot to configure; lazy initialization
- **Cons**: First ticket creation is slower; unexpected channel creation; permission issues if bot lacks Manage Channels; surprising UX for admin
- **Effort**: Low-Medium
- **AGENTS.md compliance**: Same permission concern as Option B

#### 4. Hybrid — `/setup` + Fallback Warning (Option D — Recommended)

Combine a lightweight `/setup` command with improved error messages that tell admins EXACTLY what to do (including the dashboard URL).

- **Pros**: Best UX — guided setup + clear error messages; respects admin consent; no surprise channel creation
- **Cons**: Two code paths to maintain
- **Effort**: Medium
- **AGENTS.md compliance**: Full compliance possible

### Recommendation

**Option D (Hybrid)** — Here's why:

1. **Add `/setup` command** in `TicketsCog` (or a new `SetupCog`): a hybrid command `@is_admin()` that accepts `ticket_category` (a `discord.CategoryChannel` parameter — discord.py resolves it automatically) and optionally `mod_role`, `log_channel`. Saves via `guild_service.save_config()`. Uses `t()` for all strings.

2. **Improve error messages** in the "Not Configured" blocks: instead of generic "Ask an admin to set it up", say "Run `/setup` or configure via the dashboard" with a link.

3. **Fix dashboard hint**: change "Default ticket category UUID for new tickets" to "Discord Category Channel ID (right-click → Copy Channel ID)".

This approach:
- Respects admin consent (no surprise channel creation)
- Uses `t()` for all new strings (i18n compliance)
- Follows existing patterns (`@is_admin()` from `bot/utils/checks.py`)
- Is discoverable (error messages point to `/setup`)
- Requires `Manage Channels` permission only if the admin wants to create a new category (they can use an existing one)

### Risks

- **Permission model**: `/setup` with `@is_admin()` means only server admins can configure. This is correct per the existing dashboard model, but mods cannot self-serve. Severity: Low (by design).
- **i18n scope**: New command needs keys in both `es.json` and `en.json`. If missing, `t()` falls back to raw key strings. Severity: Low (testable).
- **Dashboard desync**: Bot-side config changes via `/setup` won't immediately reflect in the dashboard (dashboard reads from Supabase directly). Severity: Low (Supabase is the source of truth).
- **Existing guilds**: Guilds that already have `ticket_category_id = None` need a migration path. The improved error message handles this — no DB migration needed. Severity: Low.

### Ready for Proposal

**Yes.** The exploration is complete. The orchestrator should tell the user:

1. The bug is **confirmed** — `ticket_category_id` defaults to `None` and there's no bot-side command to set it
2. The fix is a **hybrid approach**: add `/setup` command + improve error messages + fix dashboard hint
3. **Three flows are affected**: ticket creation, sub-ticket creation, ticket reopen
4. The dashboard CAN set the value but the hint text is misleading ("UUID" instead of "Discord Category Channel ID")
5. No DB schema changes needed — only code changes in bot + dashboard
