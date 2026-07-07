# Exploration: audit-product-ux-tickets

## Current State

NebulosaBot is a Python 3.11+ Discord bot (discord.py 2.7.1) with 7 cogs (Core, Sentinel, Tickets, Stellar, Greetings, Utility, Ocio), 8 services, 2 listeners (XP, Audit), and 24 hybrid commands. The architecture follows a clean cog → service → database layering with cache-first reads via Supabase/PostgreSQL.

### Ticket System Lifecycle (as-implemented)

The full ticket flow works as follows:

1. **Panel Deploy** (`/ticket_panel`): Admin/mod deploys a persistent panel embed with an "Open Ticket" button (`TicketPanelView`, `custom_id="ticket:open"`, `timeout=None`). Panel IDs are persisted to the `guild` table (`ticketPanelMessageId`, `ticketPanelChannelId`).

2. **User Clicks "Open Ticket"**: `TicketPanelView.open_ticket_button()` fetches active `TicketCategory` rows for the guild. If none exist, shows an ephemeral error. Otherwise, shows an ephemeral `_CategorySelectView` dropdown (5-min timeout).

3. **Category Selection → Channel Creation**: `_CategorySelect.callback()` fetches `GuildConfig`, checks `config.ticket_category_id` (the Discord category channel). **CRITICAL BLOCKER**: If `ticketCategoryId` is NULL, the user sees a "Not Configured" ephemeral error (`tickets.py:408-417`). The user CANNOT create tickets until an admin sets this.

4. **Channel + DB Creation**: Creates a Discord text channel in the configured category, creates the ticket DB row with MAX+1 numbering (3 retries on conflict), attaches a `TicketActionsView` (persistent, `custom_id="ticket:claim"` / `"ticket:close"`), and sends a welcome embed.

5. **Claim/Close/Reopen/Transfer/Notes**: Full lifecycle via persistent buttons and hybrid commands.

6. **Auto-close**: `@tasks.loop(hours=1)` closes tickets idle for 48h, generating transcripts.

### Ticket Transcript Behavior

**TranscriptService** (`bot/services/transcript_service.py`):
- Generates self-contained inline-CSS HTML transcripts from channel history (up to 5000 messages).
- Uploads the HTML file to the configured log channel.
- Returns the attachment URL which is stored in the ticket's `transcriptUrl` field.

**Critical Finding — NO summary pinned on creation**: When a ticket is created (`tickets.py:529-538`), the bot sends a welcome embed with `TicketActionsView` but does NOT pin it. There is NO summary generated at creation time. The transcript is only generated at CLOSE time, not at creation. The user's question "does creating a ticket produce a summary pinned in the channel?" → **NO**.

### Subsidiados (Sub-tickets) Logic

The sub-ticket system (`tickets.py:1165-1449`, `ticket_service.py:290-415`) is well-implemented:
- One level deep (no sub-of-sub), same-guild enforcement, 4 FK validations via `ticket_invariants.py`.
- Creates a new channel, links via `parentId`, inherits parent author for permissions.
- Audit trail on success and denial paths.

**Quality Assessment**: The subsidiados logic is CLEAN. The invariant layer in `ticket_invariants.py` is pure-function, well-tested, and shared between bot and dashboard. No poor-quality patterns found.

---

## Audit Findings (by severity)

### CRITICAL

#### C1. `ticketCategoryId` is NULL — Tickets Are Blocked
- **File**: `bot/cogs/tickets.py:408-417`
- **Impact**: Users cannot create tickets. The "Open Ticket" button shows "Not Configured" error.
- **Root Cause**: There is NO `/setup` command or wizard to configure `ticketCategoryId`. The guild's Discord category channel must be set manually in the database.
- **Evidence**: `config.ticket_category_id` is `None` by default (`bot/models/guild.py:21`). `GuildService.on_guild_join()` only sets `prefix` and `language` — NOT `ticketCategoryId`.

#### C2. NO i18n System — All User-Facing Text is Hardcoded English
- **Files**: ALL cogs, ALL services, ALL embed builders
- **Impact**: The guild `language` field (`es`/`en`) exists in `GuildConfig` (`bot/models/guild.py:18`) but is NEVER READ for message localization. The `status` command shows the language value (`core.py:155`) but no command/service uses it to select message language.
- **Evidence**: Grep for `i18n`, `locale`, `gettext`, `translation` in `bot/` returns ZERO hits for actual translation logic. Only references to the `language` field itself.
- **Scope**: Every `error_embed()`, `success_embed()`, `info_embed()`, every embed title/description, every button label, every error message is English-only.

#### C3. `/create_category` Sends Permanent Message in Public Channel
- **File**: `bot/cogs/tickets.py:998-1004`
- **Impact**: The "Category Created" confirmation with the UUID is sent as a regular (non-ephemeral) `ctx.send()`. In a public channel, this is annoying and unprofessional.
- **Root Cause**: Uses `ctx.send()` without `ephemeral=True`. For hybrid commands, `ctx.send()` routes to `interaction.response.send_message()` for slash, but WITHOUT `ephemeral=True` the message is visible to everyone.

#### C4. `/ticket_panel` Confirmation Uses `delete_after=10` Instead of Ephemeral
- **File**: `bot/cogs/tickets.py:910-916`
- **Impact**: The "Panel Deployed" success message uses `delete_after=10` — a visible message that auto-deletes after 10 seconds. This briefly pollutes the channel and is not the correct pattern.
- **Correct Pattern**: Should use `ephemeral=True` for the confirmation, or use `ctx.defer(ephemeral=True)` then `ctx.send(embed=..., ephemeral=True)`.

### WARNING

#### W1. Inconsistent Ephemeral Pattern Across Cogs

| Command | Cog | Current Behavior | Should Be Ephemeral? |
|---------|-----|-----------------|---------------------|
| `/ticket_panel` | Tickets | `ctx.send()` + `delete_after=10` | YES (admin config) |
| `/create_category` | Tickets | `ctx.send()` permanent | YES (admin config) |
| `/list_categories` | Tickets | `ctx.send()` permanent | YES (admin config) |
| `/delete_category` | Tickets | `ctx.send()` permanent | YES (admin config) |
| `/subticket` (group) | Tickets | `ctx.send()` permanent | YES (mod command) |
| `/subticket create` | Tickets | `ctx.send()` permanent | MAYBE (creates visible channel) |
| `/reopen` | Tickets | `ctx.send()` permanent | MAYBE (mod action, visible result) |
| `/transfer` | Tickets | `ctx.send()` permanent | MAYBE (mod action) |
| `/note add/list/delete` | Tickets | `ctx.send()` / DM | Note list is private (good); add/delete are permanent |
| `/warn` | Sentinel | `ctx.send()` permanent | NO (moderation actions should be visible) |
| `/unwarn` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/mute` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/unmute` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/kick` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/ban` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/lock` | Sentinel | `ctx.send()` permanent | NO (channel-level action) |
| `/unlock` | Sentinel | `ctx.send()` permanent | NO (same) |
| `/modlogs` | Sentinel | `ctx.send()` permanent | YES (personal data) |
| `/daily` | Stellar | `ephemeral=True` | ✅ Correct |
| `/coins` | Stellar | `ephemeral=True` | ✅ Correct |
| `/leaderboard` | Stellar | `ephemeral=True` | ✅ Correct |
| `/rank` | Stellar | `ephemeral=True` | ✅ Correct |
| `/avatar` | Utility | `ctx.send()` permanent | Debatable (public display is fine) |
| `/serverinfo` | Utility | `ctx.send()` permanent | NO (public info) |
| `/userinfo` | Utility | `ctx.send()` permanent | Debatable |
| `/dados` | Ocio | `ctx.send()` permanent | NO (fun, public) |
| `/banana` | Ocio | `ctx.send()` permanent | NO (fun, public) |
| `/ping` | Core | `ctx.send()` permanent | Debatable |
| `/status` | Core | `ctx.send()` permanent | YES (admin info) |
| `/help` | Core | `ctx.send()` permanent | Debatable |
| `/sync` | Core | `ephemeral=True` | ✅ Correct |
| `/welcome_test` | Greetings | `ephemeral=True` | ✅ Correct |
| `/goodbye_test` | Greetings | `ephemeral=True` | ✅ Correct |

**Recommended Standard**:
- **Ephemeral**: Admin/config commands (`/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category`, `/sync`, `/status`), personal data (`/daily`, `/coins`, `/rank`, `/modlogs`, `/note list`), and test commands.
- **Permanent**: Moderation actions (`/warn`, `/kick`, `/ban`, `/lock`), fun commands (`/dados`, `/banana`), public info (`/serverinfo`, `/avatar`), and commands whose output is meant to be seen (ticket panels, leaderboards when displayed publicly).

#### W2. Prefix Commands Don't Support Ephemeral
- **Impact**: All commands are hybrid. When invoked via prefix (`nb!create_category`), `ctx.send()` sends a permanent message — there's no ephemeral option for prefix commands.
- **discord.py Behavior**: `ctx.interaction` is `None` for prefix invocations, so `ephemeral=True` is silently ignored.
- **Mitigation**: For prefix invocations of admin commands, consider DMing the response (like `/note list` already does via `_send_notes_private()`).

#### W3. No `/setup` or `/configure` Wizard
- **Evidence**: Grep for `setup`, `configure`, `wizard` in `bot/cogs/` returns only `async def setup(bot)` (cog loader) — NO user-facing setup command exists.
- **Impact**: Admins must manually configure the guild by knowing which fields to set. There's no guided flow for: setting `ticketCategoryId`, `modRoleId`, `logChannelId`, `language`, `prefix`.

#### W4. Missing `@app_commands.default_permissions()` on Admin Commands
- **Files**: `tickets.py` (`/create_category`, `/list_categories`, `/delete_category`, `/subticket`, `/reopen`, `/transfer`, `/note`)
- **Impact**: These commands use `@is_mod()` but don't set `@app_commands.default_permissions()` for the Discord UI permission hint. Slash command users see all commands regardless of their permissions — the check only happens at execution time.
- **Correct Pattern**: Per Context7, `@app_commands.default_permissions(administrator=True)` or `@app_commands.default_permissions(moderate_members=True)` should be used alongside the runtime check.
- **Exception**: `/welcome_test` and `/goodbye_test` in `greetings.py` correctly use both `@commands.has_permissions(administrator=True)` AND `@app_commands.default_permissions(administrator=True)`.

#### W5. Transcript Not Pinned, No Summary on Creation
- **File**: `bot/cogs/tickets.py:529-538`
- **Impact**: The welcome embed sent to the ticket channel on creation is NOT pinned. There is no summary at creation time. The transcript is only generated at close.
- **User Request**: "Verifica si al crear un ticket se crea un resumen de este, y se fija en el canal el resumen."
- **Answer**: NO. The welcome embed is sent but NOT pinned. No summary is generated at creation. The transcript is generated only at close time and uploaded to the log channel (not the ticket channel).

#### W6. `on_command_error` Sends Non-Ephemeral Error Embeds
- **File**: `bot/bot.py:361-387`
- **Impact**: When a prefix command fails, the error embed is sent as a regular channel message (visible to everyone). The slash command handler (`on_app_command_error`) correctly uses `ephemeral=True`, but the prefix handler does not.
- **Note**: Prefix commands can't be ephemeral, but the error could be DM'd instead.

### SUGGESTION

#### S1. Proactive UX Improvements

1. **Empty State Guidance**: When no ticket categories exist, the "Open Ticket" button error message says "Ask an admin to set them up with `/create_category`" — good. But when `ticketCategoryId` is NULL, it says "Ask an admin to set it up" without specifying HOW.

2. **Confirmation Dialogs**: `/delete_category` does NOT ask for confirmation before deleting. Destructive actions should have a confirmation step (button-based or modal).

3. **Ticket Panel Embed**: The default panel embed is functional but generic. Consider making it more visually appealing with custom branding, category previews, and ticket count statistics.

4. **Button State Management**: The `TicketActionsView` Claim/Close buttons don't update their state after a ticket is closed (the channel is deleted, so this is acceptable). However, after claim, only the embed is updated — the buttons remain the same. Consider disabling the Claim button after claim.

5. **Help Command**: The `/help` command shows all commands to all users regardless of permissions. Consider filtering by the user's actual permissions.

#### S2. Missing Commands (Inspired by Popular Bots)

| Suggested Command | Description | Fits Architecture? |
|------------------|-------------|-------------------|
| `/ticket close_reason` | Close ticket with a reason (visible in transcript) | YES — extend close_ticket |
| `/ticket rating` | Rate ticket satisfaction after close | YES — new DB table + service |
| `/slowmode` | Set channel slowmode | YES — utility cog |
| `/poll` | Create a reaction-based poll | YES — new cog or utility |
| `/giveaway` | Timed giveaway with random winner | YES — new cog |
| `/remind` | Set a reminder | YES — new cog + DB |
| `/clear` | Bulk delete messages | YES — sentinel cog |
| `/snipe` | Show last deleted message | YES — audit listener stores it |
| `/autorole` | Auto-assign role on join | YES — greetings cog |
| `/reactionrole` | Reaction-based role assignment | YES — new cog + persistent view |
| `/embed` | Create custom embeds | YES — utility cog |
| `/ticket_stats` | Show ticket statistics | YES — ticket service |

#### S3. Permission Requirements Table

| Permission | Required By | Reason |
|-----------|------------|--------|
| `manage_channels` | Tickets, Sentinel (lock/unlock) | Create/delete ticket channels, modify channel permissions |
| `manage_roles` | Stellar (level roles), Autorole | Auto-assign roles on level-up or join |
| `ban_members` | Sentinel (`/ban`) | Ban users |
| `kick_members` | Sentinel (`/kick`) | Kick users |
| `moderate_members` | Sentinel (`/mute`) | Timeout users |
| `manage_messages` | Audit (channel visibility check) | Read message history in private channels |
| `embed_links` | ALL cogs | Send embed messages |
| `attach_files` | Transcript, Rank Card, Greetings | Upload files |
| `read_message_history` | Transcript, Audit | Fetch channel history |
| `send_messages` | ALL cogs | Send messages |
| `view_channel` | ALL cogs | Access channels |
| `use_application_commands` | ALL slash commands | Execute slash commands |

**Commands Missing Permission Checks**:
- `/ticket_panel`: Has `@is_mod()` ✅
- `/create_category`: Has `@is_mod()` ✅
- `/list_categories`: Has `@is_mod()` ✅
- `/delete_category`: Has `@is_mod()` ✅
- `/subticket`: Has `@is_mod()` ✅
- `/reopen`: Has `@is_mod()` ✅
- `/transfer`: Has `@is_mod()` ✅
- `/note`: Has `@is_mod()` ✅
- `/warn`: Has `@is_mod()` ✅
- `/unwarn`: Has `@is_mod()` ✅
- `/mute`: Has `@is_mod()` ✅
- `/unmute`: Has `@is_mod()` ✅
- `/kick`: Has `@is_mod()` ✅
- `/ban`: Has `@is_admin()` ✅
- `/lock`: Has `@is_mod()` ✅
- `/unlock`: Has `@is_mod()` ✅
- `/modlogs`: Has `@is_mod()` ✅
- `/daily`: No check (open) ✅ (correct — public command)
- `/coins`: No check (open) ✅
- `/leaderboard`: No check (open) ✅
- `/rank`: No check (open) ✅
- `/avatar`: No check (open) ✅
- `/serverinfo`: No check (open) ✅
- `/userinfo`: No check (open) ✅
- `/dados`: No check (open) ✅
- `/banana`: No check (open) ✅
- `/ping`: No check (open) ✅
- `/status`: No check (should be mod/admin?)
- `/help`: No check (open) ✅
- `/sync`: Has `@is_admin()` ✅
- `/welcome_test`: Has `@commands.has_permissions(administrator=True)` ✅
- `/goodbye_test`: Has `@commands.has_permissions(administrator=True)` ✅

**Missing**: `/status` exposes database health and guild config details — should be `@is_mod()` at minimum.

#### S4. i18n Architecture Recommendation

Given the bot's size (~24 commands, ~8 services), the simplest robust approach is **JSON-based locale files** with a thin lookup layer:

```
bot/
├── core/
│   └── i18n.py          # t(guild_id, key, **kwargs) → str
├── locales/
│   ├── es.json           # Spanish translations (default)
│   └── en.json           # English translations
```

**`i18n.py`** would:
1. Load all locale files at startup into a dict-of-dicts.
2. Expose `t(guild_id: str, key: str, **kwargs) -> str` that:
   - Reads the guild's language from `GuildService.get_config()`.
   - Looks up the key in the appropriate locale dict.
   - Falls back to `es` if the key is missing.
   - Supports `{placeholder}` interpolation via `kwargs`.
3. Keys follow a dot-notation convention: `tickets.create.success`, `errors.permission.denied`.

**Scope**: Every user-facing string MUST go through `t()`. This includes:
- Embed titles and descriptions
- Button labels
- Error messages
- Ticket category templates
- Success confirmations

#### S5. Setup Wizard Design

**Recommended**: A `/setup` hybrid command with a persistent view (button-based wizard):

1. `/setup` → Shows an embed with current config + "Configure" button.
2. "Configure" button → Shows a modal with fields: prefix, language, mod role, log channel, ticket category, welcome channel.
3. On submit → Saves config, invalidates cache, confirms with updated embed.

**Alternative**: Multi-step slash command wizard using `discord.ui.Select` for each config option.

**Key Config Fields to Configure**:
- `prefix` (text input)
- `language` (select: es/en)
- `modRoleId` (role select)
- `logChannelId` (channel select)
- `ticketCategoryId` (category channel select)
- `ticketPanelChannelId` (text channel select)
- `welcomeEnabled` (toggle)
- `logEnabled` (toggle)

---

## Affected Areas

- `bot/cogs/tickets.py` — Ephemeral patterns, panel embed, category commands, button states
- `bot/cogs/core.py` — `/status` permission check, `/help` permission filtering
- `bot/cogs/sentinel.py` — `/modlogs` ephemeral, missing `@app_commands.default_permissions()`
- `bot/cogs/stellar.py` — Already correct (ephemeral)
- `bot/cogs/greetings.py` — Already correct (ephemeral + default_permissions)
- `bot/cogs/utility.py` — Minor ephemeral considerations
- `bot/cogs/ocio.py` — No changes needed (fun commands stay public)
- `bot/bot.py` — Error handler i18n, `on_command_error` prefix pattern
- `bot/utils/embeds.py` — i18n integration point
- `bot/utils/checks.py` — No changes needed (well-implemented)
- `bot/models/guild.py` — `language` field already exists
- `bot/services/guild_service.py` — i18n lookup integration
- `bot/services/ticket_service.py` — Transcript pinning, close reason
- `bot/services/transcript_service.py` — Summary generation on creation
- NEW: `bot/core/i18n.py` — i18n lookup layer
- NEW: `bot/locales/es.json` — Spanish translations
- NEW: `bot/locales/en.json` — English translations
- NEW: `bot/cogs/setup.py` — Setup wizard cog

---

## Approaches

### 1. **Incremental i18n + UX Fix (Recommended)**
   - Phase 1: Create `i18n.py` + locale files, wire into `embeds.py`.
   - Phase 2: Migrate all hardcoded strings to locale keys (one cog at a time).
   - Phase 3: Add `/setup` wizard.
   - Phase 4: Fix ephemeral patterns across all cogs.
   - Pros: Phased delivery, each phase is independently shippable, low risk.
   - Cons: Temporary inconsistency during migration.
   - Effort: HIGH (full migration is ~100+ strings across 7 cogs + 8 services).

### 2. **Big-Bang i18n + UX Overhaul**
   - Do everything in one change: i18n system, all strings migrated, setup wizard, ephemeral fixes, permission fixes.
   - Pros: No inconsistency period.
   - Cons: Huge PR, high review burden, high risk of regressions.
   - Effort: VERY HIGH.

### 3. **Minimal Fix (Ephemeral + Setup Only)**
   - Fix ephemeral patterns, add `/setup` wizard, add `@app_commands.default_permissions()` where missing. Skip i18n for now.
   - Pros: Quick wins, addresses the most visible UX issues.
   - Cons: Doesn't address the i18n problem (the user's primary complaint).
   - Effort: MEDIUM.

---

## Recommendation

**Approach 1 (Incremental)** is the correct path. Here's why:

1. The user's primary pain points are: (a) tickets blocked by missing config, (b) non-ephemeral admin messages polluting channels, (c) no i18n, (d) no setup wizard.
2. These can be addressed in 3-4 chained PRs, each independently shippable:
   - **PR1**: Fix ephemeral patterns + add `@app_commands.default_permissions()` + fix `/status` permission + pin ticket welcome embed.
   - **PR2**: Add i18n system (`i18n.py` + locale files) + migrate tickets cog strings.
   - **PR3**: Add `/setup` wizard + migrate remaining cogs to i18n.
   - **PR4**: Add proactive UX features (close reason, ticket rating, confirmation dialogs).

---

## Risks

- **R1**: i18n migration touches every file — merge conflicts with concurrent work.
- **R2**: `ephemeral=True` is silently ignored for prefix commands — the DM fallback pattern used by `/note list` should be applied to other admin commands.
- **R3**: The `/setup` wizard needs `discord.ui.Modal` + `discord.ui.Select` — these are well-supported in discord.py 2.7.1 but require careful UX design.
- **R4**: Changing ephemeral behavior for existing commands could surprise users who expect to see mod actions in the channel.
- **R5**: The `ticketCategoryId` NULL blocker requires either a `/setup` wizard or a manual DB update — the wizard is the right fix.

---

## Ready for Proposal

**YES** — the exploration is complete. The orchestrator should tell the user:

1. The ticket system is well-architected but BLOCKED by the missing `ticketCategoryId` configuration.
2. There is NO i18n system — the `language` field exists but is never used for localization.
3. Ephemeral patterns are inconsistent — Stellar and Greetings are correct, Tickets and Sentinel need fixes.
4. A `/setup` wizard is the missing piece for proactive admin UX.
5. The transcript is generated at CLOSE time only, NOT at creation. The welcome embed is NOT pinned.
6. Recommended approach: Incremental delivery in 3-4 chained PRs.
