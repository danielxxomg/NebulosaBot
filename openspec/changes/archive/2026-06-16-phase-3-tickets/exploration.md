## Exploration: Phase 3 — Tickets Module

### Current State

The bot has a working foundation (Phase 1-2): database layer, cache, guild config, infraction service, sentinel cog, and the `ticket` table already exists in `migrations/001_initial_schema.sql` with columns for sequential numbering, status (open/claimed/closed), claim tracking, transcript URL, and last activity. The `Ticket` dataclass in `bot/models/ticket.py` mirrors this table.

However, there is **no ticket_category table**, no `TicketService`, no ticket cog, no persistent views, and no transcript logic. The `guild.ticket_category_id` field exists but refers to the Discord category where ticket channels are created — not the ticket type categories (Soporte, Reporte, Sugerencia).

**Existing patterns to follow:**
- Services take `db` (and optionally `cache`) in `__init__`, use `__slots__`
- Models are dataclasses with `from_db_row()` / `to_db_dict()` (camelCase keys)
- Cogs use `async def setup(bot)` (v2.x), hybrid commands, `@is_mod()` / `@is_admin()` checks
- Database methods use `_unwrap()` on sync supabase-py responses
- Background tasks: `@tasks.loop()` with `cog_unload()` cancel
- Persistent views: `timeout=None` + static `custom_id` + `bot.add_view()` on startup

### Affected Areas

- `bot/models/ticket_category.py` — **NEW** dataclass for ticket categories
- `bot/services/ticket_service.py` — **NEW** business logic (create/close/claim/autoclose)
- `bot/services/transcript_service.py` — **NEW** HTML transcript generation + upload
- `bot/cogs/tickets.py` — **NEW** cog with `/ticket_panel`, `/create_category`, persistent views
- `bot/core/database.py` — **EXTEND** with ticket CRUD + ticket_category CRUD + stale ticket query
- `bot/bot.py` — **EXTEND** setup_hook() to init TicketService, TranscriptService, register persistent views, load tickets cog
- `migrations/002_ticket_categories.sql` — **NEW** migration for `ticket_category` table
- `bot/models/__init__.py` — **EXTEND** exports (currently empty)

### Approaches

#### 1. TicketCategory Model + Migration

**Approach**: New `ticket_category` table with guild-scoped categories.

```sql
CREATE TABLE ticket_category (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "guildId"   TEXT NOT NULL REFERENCES guild(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    emoji       TEXT,
    description TEXT,
    position    INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE ("guildId", name)
);
CREATE INDEX idx_ticket_category_guild ON ticket_category ("guildId");
```

- **Pros**: Clean separation, guild-scoped, supports ordering via `position`, unique constraint prevents duplicates
- **Cons**: Additional table join when resolving category name for a ticket
- **Effort**: Low

#### 2. TicketService — Sequential Numbering

**Approach A — Application-level MAX query**: Before insert, query `SELECT MAX("ticketNumber") FROM ticket WHERE "guildId" = $1` and increment. Wrap in a retry loop for race conditions.

**Approach B — Database sequence per guild**: Create a Postgres function that atomically increments a per-guild counter stored in a `ticket_sequence` table.

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| A: MAX + retry | Simple, no new DB objects | Race condition window (2 concurrent creates could get same number) | Low |
| B: Atomic DB function | No race conditions, guaranteed unique | More complex migration, custom SQL function | Medium |

**Recommendation**: **Approach A with optimistic retry**. Supabase Transaction Mode doesn't enforce FKs, and the bot is unlikely to have concurrent ticket creation for the same guild. A simple retry (up to 3 attempts) on unique constraint violation is sufficient. If this becomes a problem, upgrade to Approach B later.

#### 3. TicketService — Create / Close / Claim

**Create flow**:
1. Resolve guild config → get `ticketCategoryId` (Discord category for channels)
2. Get next ticket number (MAX + 1)
3. Create Discord text channel under the configured category with permission overwrites:
   - `@everyone`: deny `view_channel`
   - Ticket author: allow `view_channel`, `send_messages`, `read_message_history`
   - Mod role (from guild config): allow `view_channel`, `send_messages`, `read_message_history`, `manage_messages`
   - Bot: allow all
4. Insert ticket row in DB (status='open')
5. Send welcome embed in the new channel

**Close flow**:
1. Generate transcript (fetch message history → HTML)
2. Upload transcript to log channel (if configured)
3. Update ticket row: status='closed', closedAt=now(), transcriptUrl=attachment_url
4. Delete the Discord channel (optional — configurable, default: delete after 5s delay)

**Claim flow**:
1. Validate caller has mod role
2. Update ticket row: status='claimed', claimedBy=staff_id
3. Send embed in channel: "Ticket claimed by @staff"

- **Effort**: Medium-High (channel creation with overwrites is the complex part)

#### 4. Persistent Views — Ticket Panel

**Approach**: Single `TicketPanelView` class with `timeout=None` and static `custom_id` prefixes.

```python
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", custom_id="ticket:open", style=primary)
    async def open_ticket(self, interaction, button):
        # Show category select modal or direct create

    @discord.ui.button(label="Close", custom_id="ticket:close", style=danger)
    async def close_ticket(self, interaction, button):
        # Only works inside a ticket channel
```

**Panel persistence**: Store `panelMessageId` + `panelChannelId` in the `guild` table (add 2 nullable columns) or in a separate `ticket_panel` table. On startup, fetch the message and call `bot.add_view(TicketPanelView())`.

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| Add columns to guild table | Simple, no new table | Guild table gets wider, panel is 1:1 with guild | Low |
| Separate ticket_panel table | Cleaner, supports multiple panels per guild | Extra table + queries | Medium |

**Recommendation**: **Add to guild table** — the requirement is one panel per guild. Add `ticketPanelMessageId` and `ticketPanelChannelId` as nullable TEXT columns. This is the simplest approach and matches the 1:1 relationship.

**Category selection**: When user clicks "Open Ticket", show a `discord.ui.Select` dropdown with the guild's categories (Soporte, Reporte, Sugerencia). This requires a two-step interaction: button click → select menu → channel creation. Implement as a `discord.ui.View` with a select that appears in the interaction response (ephemeral message with the select).

#### 5. Transcript Service

**Approach**: Fetch channel history → render HTML template → upload as file to log channel.

```python
class TranscriptService:
    async def generate(self, channel: discord.TextChannel) -> discord.File:
        messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
        html = self._render_html(messages)
        buffer = io.BytesIO(html.encode("utf-8"))
        return discord.File(buffer, filename=f"transcript-{channel.name}.html")

    async def upload(self, file: discord.File, log_channel: discord.TextChannel) -> str:
        msg = await log_channel.send(file=file)
        return msg.attachments[0].url
```

**HTML template**: Minimal, self-contained HTML with inline CSS. Each message shows: author avatar, username, timestamp, content, attachments. No external dependencies.

- **Pros**: Discord CDN hosts the file permanently, URL is stable
- **Cons**: Large transcripts (10k+ messages) could hit Discord file size limit (25MB for free tier). Mitigate by truncating or splitting.
- **Effort**: Medium (HTML rendering is boilerplate but verbose)

#### 6. Auto-Close Background Task

**Approach**: `@tasks.loop(hours=1)` in `TicketsCog` that queries stale tickets.

```python
@tasks.loop(hours=1)
async def auto_close_stale_tickets(self):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    stale = await self.bot.db.get_stale_tickets(cutoff)
    for row in stale:
        ticket = Ticket.from_db_row(row)
        await self.bot.ticket_service.close_ticket(
            ticket, reason="Auto-closed due to inactivity (48h)"
        )
```

**DB query**: `SELECT * FROM ticket WHERE status != 'closed' AND "lastActivity" < $1`

**lastActivity update**: Must be updated on every message in a ticket channel. Add an `on_message` listener in the TicketsCog that checks if the message's channel is a ticket channel and updates `lastActivity`.

- **Pros**: Simple, runs hourly, 48h threshold is generous
- **Cons**: `on_message` fires for EVERY message — must be fast. Use a set of ticket channel IDs (cached) for O(1) lookup.
- **Effort**: Low-Medium

#### 7. Tickets Cog Commands

- `/ticket_panel` (admin) — Creates the persistent panel embed + view in the current channel. Stores message ID in guild config.
- `/create_category` (admin) — Creates a ticket category (name, emoji, description).
- `/list_categories` (mod) — Lists configured categories.
- `/delete_category` (admin) — Removes a category.

### Recommendation

**Architecture summary:**

```
bot/
├── models/
│   ├── ticket.py              (exists — no changes needed)
│   └── ticket_category.py     (NEW)
├── services/
│   ├── ticket_service.py      (NEW — create/close/claim/numbering)
│   └── transcript_service.py  (NEW — HTML generation + upload)
├── cogs/
│   └── tickets.py             (NEW — commands + persistent views + auto-close task)
├── core/
│   └── database.py            (EXTEND — ticket CRUD + category CRUD + stale query)
└── bot.py                     (EXTEND — init services, register views, load cog)
migrations/
└── 002_ticket_categories.sql  (NEW — ticket_category table + guild panel columns)
```

**Key decisions:**
1. Sequential numbering via MAX + retry (simple, sufficient for bot scale)
2. Panel persistence via guild table columns (1:1 relationship, simplest)
3. Transcript as self-contained HTML uploaded to Discord CDN
4. Auto-close via hourly `@tasks.loop`, 48h inactivity threshold
5. `on_message` listener with cached ticket channel set for `lastActivity` updates
6. Category select shown as ephemeral response after "Open Ticket" button click

### Risks

- **Race condition on ticket numbering**: Two concurrent `/ticket_panel` button clicks could theoretically get the same number. Mitigated by retry logic, but a DB-level atomic counter would be safer for high-traffic guilds.
- **`on_message` performance**: Fires for every message in every guild. Must check channel ID against a cached set and return immediately for non-ticket channels. Consider using `bot.listen()` (discord.py 2.x) instead of `on_message` to avoid blocking message processing.
- **Transcript file size**: Very active tickets (10k+ messages) could exceed Discord's 25MB upload limit. Mitigate by limiting transcript to last 5000 messages or splitting into chunks.
- **Persistent view re-registration**: If the panel message is deleted, `bot.add_view()` on startup will silently fail. Need error handling and a way to detect/recreate deleted panels.
- **Channel deletion timing**: Deleting a channel immediately after transcript generation could fail if the transcript upload is still in progress. Add a small delay (5s) or ensure transcript is fully uploaded before channel deletion.
- **Supabase Transaction Mode**: No FK enforcement at DB level. Application must validate that `categoryId` references a valid category and `guildId` exists.

### Ready for Proposal

**Yes.** The codebase has clear patterns (services, cogs, models, database layer) that map directly to the tickets module. The existing `ticket` table and `Ticket` dataclass provide a solid foundation. The main unknowns (category selection UX, transcript format) have straightforward solutions.

The orchestrator should tell the user: exploration is complete, all components are well-defined with clear approaches. Ready to proceed to `sdd-propose` to formalize scope, rollback plan, and implementation order.
