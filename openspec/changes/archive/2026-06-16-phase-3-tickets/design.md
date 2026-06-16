# Design: Phase 3 — Tickets Module

## Technical Approach

Implement a full ticketing system following existing NebulosaBot patterns: services with `(db, cache)` + `__slots__`, dataclass models with `from_db_row()`/`to_db_dict()`, cogs with `async def setup(bot)`. The ticket table already exists (migration 001); we add `ticket_category`, extend the guild model with panel persistence columns, and wire everything through `setup_hook()`.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice | Rationale |
|----------|---------|----------|--------|-----------|
| Sequential numbering | A: MAX+1 retry · B: DB sequence function | A: simple, small race window · B: atomic, more complex | **A: MAX+1 with 3 retries** | Bot scale makes concurrent creates per guild unlikely; retry handles edge case |
| Panel persistence | A: guild table columns · B: separate `ticket_panel` table | A: simple, 1:1 · B: multi-panel support | **A: guild table** | Requirement is 1 panel per guild; matches existing pattern (ticket_category_id on guild) |
| Transcript format | A: inline-CSS HTML · B: Markdown · C: external CDN | A: self-contained, Discord-hosted · B: less visual · C: extra infra | **A: inline-CSS HTML** | Discord CDN hosts permanently; no external deps; URL stable |
| `on_message` perf | A: DB query per message · B: cached channel set | A: always accurate, slow · B: O(1), needs sync | **B: cached `set[int]`** | Fires for every message; must be fast. Sync on ticket create/close + startup |
| Auto-close | A: hourly loop · B: per-ticket scheduler | A: simple, batch · B: precise, complex | **A: `@tasks.loop(hours=1)`** | 48h threshold makes minute precision unnecessary |

## Data Flow

### Ticket Creation
```
User clicks "Open Ticket" → TicketPanelView callback
  → ephemeral Select with categories
  → TicketService.create_ticket()
      → MAX("ticketNumber")+1 with retry
      → guild.create_text_channel() with permission overwrites
      → DB insert (status='open')
      → sync ticket_channel_cache
      → welcome embed in new channel
```

### Ticket Close
```
Staff clicks "Close" → TicketActionsView callback
  → TranscriptService.generate(channel) → HTML → discord.File
  → upload to logChannelId → get attachment URL
  → DB update (status='closed', transcriptUrl, closedAt)
  → channel.delete() after 5s delay
  → remove from ticket_channel_cache
```

### Auto-Close
```
@tasks.loop(hours=1) → get_stale_tickets(cutoff=48h)
  → for each: TranscriptService.generate + close flow
  → reason: "Auto-closed due to inactivity (48h)"
```

### lastActivity Update
```
on_message → channel.id in _ticket_channel_cache?
  → YES: DB update ticket SET lastActivity=NOW() WHERE channelId=$1
  → NO: return immediately (O(1) early exit)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/002_ticket_categories.sql` | Create | `ticket_category` table + guild panel columns (`ticketPanelMessageId`, `ticketPanelChannelId`) |
| `bot/models/ticket_category.py` | Create | `TicketCategory` dataclass with `from_db_row()`/`to_db_dict()` |
| `bot/models/guild.py` | Modify | Add `ticket_panel_message_id: str \| None` and `ticket_panel_channel_id: str \| None` fields + update `from_db_row()`/`to_db_dict()` |
| `bot/services/ticket_service.py` | Create | `create_ticket()`, `close_ticket()`, `claim_ticket()`, sequential numbering with retry, `_ticket_channel_cache: set[int]` |
| `bot/services/transcript_service.py` | Create | `generate(channel) → discord.File`, `upload(file, log_channel) → str`, HTML template with inline CSS |
| `bot/cogs/tickets.py` | Create | `TicketsCog`: `/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category`, `TicketPanelView`, `TicketActionsView`, `auto_close_stale_tickets` task, `on_message` listener |
| `bot/core/database.py` | Modify | Add: `insert_ticket()`, `update_ticket()`, `get_ticket_by_channel()`, `get_max_ticket_number()`, `get_stale_tickets()`, `insert_ticket_category()`, `get_ticket_categories()`, `delete_ticket_category()`, `update_guild_panel()` |
| `bot/bot.py` | Modify | `setup_hook()`: init `TicketService(db, cache)`, `TranscriptService()`, register persistent views, load tickets cog. Add `ticket_service` + `transcript_service` to `__slots__` |
| `tests/test_ticket_service.py` | Create | Unit tests for numbering, create/close/claim flows, cache sync |

## Interfaces / Contracts

```python
@dataclass
class TicketCategory:
    id: str                  # UUID PK
    guild_id: str            # FK guild.id
    name: str                # e.g. "Soporte"
    emoji: str | None        # e.g. "🛠"
    description: str | None
    position: int            # ordering within guild
    created_at: datetime
    # from_db_row() / to_db_dict() following existing pattern

class TicketService:
    __slots__ = ("_db", "_cache", "_ticket_channel_cache")
    def __init__(self, db: Database, cache: TTLCache) -> None: ...
    async def create_ticket(self, guild_id: str, author_id: str, category_id: str | None, guild: discord.Guild) -> Ticket: ...
    async def close_ticket(self, ticket: Ticket, *, reason: str, transcript_service: TranscriptService, log_channel: discord.TextChannel | None) -> str | None: ...
    async def claim_ticket(self, ticket: Ticket, staff_id: str) -> Ticket: ...
    async def sync_channel_cache(self) -> None: ...  # load open ticket channel IDs into set

class TranscriptService:
    __slots__ = ()
    async def generate(self, channel: discord.TextChannel, *, limit: int = 5000) -> discord.File: ...
    async def upload(self, file: discord.File, log_channel: discord.TextChannel) -> str: ...

class TicketPanelView(discord.ui.View):
    # timeout=None, custom_id="ticket:panel"
    # Select dropdown for categories + "Open Ticket" button

class TicketActionsView(discord.ui.View):
    # timeout=None, custom_id prefix="ticket:actions:{channel_id}"
    # "Close" (danger) + "Claim" (success) buttons
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Sequential numbering (MAX+1, retry on conflict) | Mock DB `get_max_ticket_number()` returning values; simulate `IntegrityError` for retry path |
| Unit | `create_ticket` flow | Mock DB + mock `discord.Guild.create_text_channel`; verify channel overwrites, DB insert, cache sync |
| Unit | `close_ticket` flow | Mock transcript service + DB update; verify status, transcriptUrl, closedAt |
| Unit | `claim_ticket` | Verify status→'claimed', claimedBy set |
| Unit | `TicketCategory.from_db_row()`/`to_db_dict()` | Round-trip test with camelCase dict |
| Unit | `on_message` early return | Non-ticket channel ID not in cache → no DB call |
| Unit | Auto-close task | Mock `get_stale_tickets()` returns rows; verify `close_ticket` called per row |

## Migration / Rollout

1. Apply `migrations/002_ticket_categories.sql` — creates `ticket_category` table, adds 2 nullable columns to `guild`
2. No data migration needed — new columns are nullable, new table starts empty
3. Deploy bot code: `setup_hook()` registers views + loads cog
4. Admins deploy panel via `/ticket_panel` command per guild
5. Rollback: remove cog from `bot.py`, drop `ticket_category` table + guild columns via reverse migration

## Open Questions

- None — all decisions resolved in proposal question round.
