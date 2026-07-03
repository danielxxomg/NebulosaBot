# Exploration: NebulosaBot Foundation

## Current State

The project is in **design/planning phase** with zero source code. Four design diagrams exist in `/Diagramas/`:

- **ER Diagram** (`DiagramaEntidad-Relacion.mmd`): Defines 5 entities — Guild, User, Member, Ticket, Infraction. Covers core relationships and moderation basics.
- **Sequence Diagram** (`DiagramaSecuencia.mmd`): Documents 3 key flows — cache-first command reads, webhook-based cache invalidation from dashboard, and ticket transcript storage via Discord CDN.
- **Use Cases** (`DiagramaCasosUso.mmd`): Two actors (User, Admin) across 7 use cases. Notes that config is dashboard-exclusive and XP/coins are listener-driven.
- **Command Ecosystem** (`Ecosistema-Comandos.mmd`): Mindmap of 5 modules — Core, Tickets, Moderation (Sentinel), Economy (Stellar), Utility.

**openspec/config.yaml** is initialized with project context, stack decisions, and rule conventions.

### What Works Well in the Current Design
- Cache-first + webhook invalidation is a solid pattern for a multi-server bot
- Ticket transcripts stored as Discord CDN URLs (not DB blobs) is smart storage optimization
- Modular command structure maps cleanly to discord.py cogs
- Hybrid commands (prefix + slash) give flexibility during Discord's transition period

---

## Affected Areas

No source code exists yet. This exploration affects **all future files**. Key design decisions here will shape:

- `bot/` — Core bot entry, event loop, cache layer
- `bot/cogs/` — Each module as a discord.py cog
- `bot/services/` — Shared services (DB, cache, image gen)
- `bot/models/` — Dataclass/Pydantic models mirroring DB schema
- `dashboard/` — Next.js admin panel (separate repo or monorepo TBD)
- `openspec/` — SDD artifacts (specs, design, tasks)

---

## 1. Data Model Gaps & Proposed Additions

The current ER diagram covers the **core entities** but is missing configuration and economy tables needed by confirmed features.

### Missing Entities

#### 1.1 EconomyConfig (per-guild)
```
EconomyConfig {
    string guildId FK PK
    bigint dailyReward "Coins granted on /daily (default: 100)"
    int dailyCooldownHours "Hours between /daily claims (default: 24)"
    int xpPerMessage "XP gained per message (default: 10)"
    int xpCooldownSeconds "Seconds between XP gains per user (default: 60)"
    float levelBaseXP "Base XP for level formula (default: 100)"
    float levelMultiplier "Multiplier for level curve (default: 1.5)"
}
```
**Why**: Economy is per-server XP but global coins. The Guild table has no economy tuning fields. Each guild needs independent XP/level configuration.

#### 1.2 MemberEconomy (per-guild member)
```
MemberEconomy {
    string guildId FK
    string userId FK
    bigint coins "Per-guild coin balance"
    datetime lastDaily "Last /daily claim timestamp"
    datetime lastXpGain "Last XP gain for cooldown"
    -- Composite PK: (guildId, userId)
}
```
**Why**: The current Member table has `xp` and `level` but no coins, no cooldown tracking. The user confirmed "coins global" but the ER shows XP on Member — we need to clarify: is coins a column on Member, or a separate table? **Recommendation**: Keep coins on Member (simpler), add `lastDaily` and `lastXpGain` timestamps there.

**Revised Member**:
```
Member {
    string guildId FK
    string userId FK
    bigint xp "Per-guild XP"
    int level "Computed or cached"
    int warnings "Active warning count"
    bigint coins "Per-guild coin balance"
    datetime lastDaily "Last /daily claim"
    datetime lastXpGain "Last XP gain (cooldown)"
}
```

> **OPEN QUESTION**: User said "coins global (shared across servers)" but ER has XP per-guild on Member. Need to clarify: are coins truly global (one balance across all guilds) or per-guild? If global, coins need a separate `UserEconomy` table keyed on `userId` only. **Recommendation**: Start per-guild (simpler, matches XP pattern), add global wallet later if needed.

#### 1.3 TicketCategory
```
TicketCategory {
    uuid id PK
    string guildId FK
    string name "e.g. Soporte, Reporte, Sugerencia"
    string emoji "Button emoji"
    string description "Shown in dropdown/embed"
    int position "Display order"
    boolean active
}
```
**Why**: User confirmed ticket categories (Soporte/Reporte/Sugerencia) with a `/create_category` command. These need persistent storage beyond the single `ticketCategoryId` on Guild.

#### 1.4 TicketClaim
```
TicketClaim {
    uuid ticketId FK
    string claimedByUserId FK "Staff member who claimed"
    datetime claimedAt
}
```
**Why**: User confirmed claim system (staff takes ticket). Need to track who claimed it. Could be a column on Ticket (`claimedBy`) — simpler approach.

**Revised Ticket**:
```
Ticket {
    uuid id PK
    int ticketNumber "Sequential per guild"
    string guildId FK
    string authorId FK
    string channelId "Discord channel ID for this ticket"
    string categoryId FK "TicketCategory reference"
    string status "open/claimed/closed"
    string claimedBy "Staff who claimed (nullable)"
    string transcriptUrl "Discord CDN link"
    datetime createdAt
    datetime closedAt
    datetime lastActivity "For auto-close by inactivity"
}
```

#### 1.5 WelcomeConfig (per-guild)
```
WelcomeConfig {
    string guildId FK PK
    string channelId "Welcome message channel"
    string messageTemplate "Text template with {user}, {server}, {memberCount}"
    string backgroundImageUrl "Custom background for Pillow card"
    boolean enabled
}
```

#### 1.6 GoodbyeConfig (per-guild)
```
GoodbyeConfig {
    string guildId FK PK
    string channelId "Goodbye message channel"
    string messageTemplate
    string backgroundImageUrl
    boolean enabled
}
```
**Note**: Could merge Welcome/Goodbye into a single `GreetingConfig` table with a `type` column (welcome/goodbye). Cleaner if the schema is similar.

**Recommended merged approach**:
```
GreetingConfig {
    string guildId FK
    string type "welcome/goodbye"
    string channelId
    string messageTemplate
    string backgroundImageUrl
    boolean enabled
    -- Composite PK: (guildId, type)
}
```

#### 1.7 LogConfig (per-guild)
```
LogConfig {
    string guildId FK
    string eventType "message_edit/message_delete/member_join/member_leave/role_change/mod_action"
    string channelId "Target log channel"
    boolean enabled
    -- Composite PK: (guildId, eventType)
}
```
**Why**: User confirmed "all events in dedicated log channel" but some guilds may want different events in different channels. Start simple (one log channel per guild from `Guild.logChannelId`), add granular config later.

**Simpler Phase 1 approach**: Just use `Guild.logChannelId` + a `logEnabled` boolean. Add `LogConfig` table in Phase 3 if needed.

#### 1.8 AutoEscalation Rules
```
AutoEscalationRule {
    string guildId FK
    int warningThreshold "e.g. 3, 5"
    string action "MUTE/KICK/BAN"
    int durationMinutes "For MUTE (e.g. 60). 0 = permanent."
    boolean enabled
}
```
**Why**: User confirmed auto-escalation (3 warns = mute 1h, 5 warns = kick). Hardcoding is fragile — make it configurable per guild.

**Simpler Phase 1 approach**: Hardcode defaults (3=mute 1h, 5=kick) in code. Add `AutoEscalationRule` table when dashboard config is built.

### Recommended Entity Summary

| Entity | Phase | Notes |
|--------|-------|-------|
| Guild | 1 | Already exists, add `logEnabled`, `welcomeEnabled`, `goodbyeEnabled` |
| User | 1 | Already exists |
| Member | 1 | Add `coins`, `lastDaily`, `lastXpGain` |
| Ticket | 1 | Add `channelId`, `categoryId`, `claimedBy`, `lastActivity` |
| Infraction | 1 | Already exists, add `active` (for unwarn), `expiresAt` (for temp mute) |
| TicketCategory | 2 | Needed for `/create_category` |
| GreetingConfig | 2 | Merged welcome/goodbye |
| EconomyConfig | 2 | Per-guild economy tuning |
| AutoEscalationRule | 3 | Start hardcoded, make configurable later |
| LogConfig | 3 | Start with single channel, granular later |

---

## 2. Recommended Project Structure

```
NebulosaBot/
├── bot/
│   ├── __init__.py
│   ├── __main__.py              # Entry point: python -m bot
│   ├── bot.py                   # NebulosaBot class (extends commands.Bot)
│   ├── config.py                # Env vars, constants, defaults
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── cache.py             # RAM cache with TTL + invalidation
│   │   ├── database.py          # Supabase client wrapper
│   │   ├── webhook_server.py    # Flask/FastAPI webhook receiver for dashboard sync
│   │   └── context.py           # Custom bot context (NebulosaContext)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── guild.py             # GuildConfig dataclass
│   │   ├── member.py            # Member dataclass
│   │   ├── ticket.py            # Ticket dataclass
│   │   ├── infraction.py        # Infraction dataclass
│   │   └── economy.py           # EconomyConfig, MemberEconomy dataclasses
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── guild_service.py     # Guild CRUD + cache integration
│   │   ├── member_service.py    # Member CRUD + XP/coins logic
│   │   ├── ticket_service.py    # Ticket lifecycle management
│   │   ├── moderation_service.py # Infractions + auto-escalation
│   │   ├── economy_service.py   # Daily, coins, XP gains
│   │   ├── image_service.py     # Pillow image generation (rank, welcome)
│   │   └── transcript_service.py # HTML transcript generation + CDN upload
│   │
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── core.py              # Ping, Status, Help, Sync
│   │   ├── tickets.py           # Ticket panel, open/close/claim buttons
│   │   ├── sentinel.py          # Moderation commands (warn/mute/kick/ban)
│   │   ├── stellar.py           # Economy commands (rank/leaderboard/daily/coins)
│   │   ├── utility.py           # Avatar, serverinfo, userinfo
│   │   ├── greetings.py         # Welcome/Goodbye event listeners
│   │   ├── logging_cog.py       # Event logging to log channel
│   │   ├── ocio.py              # Fun commands (dados, banana)
│   │   └── admin_config.py      # Admin-only config commands (prefix, channels)
│   │
│   ├── views/
│   │   ├── __init__.py
│   │   ├── ticket_views.py      # Persistent views for ticket buttons/modals
│   │   └── confirmation.py      # Reusable confirmation view
│   │
│   ├── listeners/
│   │   ├── __init__.py
│   │   ├── xp_listener.py       # on_message XP gain logic
│   │   └── audit_listener.py    # on_message_edit/delete, on_member_join/leave, etc.
│   │
│   └── utils/
│       ├── __init__.py
│       ├── checks.py            # Permission checks (is_mod, is_admin)
│       ├── converters.py        # Custom argument converters
│       ├── embeds.py            # Embed builder helpers
│       ├── pagination.py        # Embed pagination for leaderboards
│       └── time.py              # Time formatting helpers
│
├── dashboard/                   # Next.js app (separate or monorepo)
│   └── ...
│
├── migrations/                  # Supabase SQL migrations
│   ├── 001_initial_schema.sql
│   └── ...
│
├── assets/
│   ├── fonts/                   # Fonts for Pillow image generation
│   └── backgrounds/             # Default welcome/rank backgrounds
│
├── tests/
│   ├── conftest.py
│   ├── test_cache.py
│   ├── test_services/
│   └── test_cogs/
│
├── openspec/                    # SDD artifacts
├── Diagramas/                   # Design diagrams
├── logo/                        # Brand assets
├── .env.example
├── pyproject.toml               # Project metadata + dependencies
├── requirements.txt             # Pinned dependencies
└── README.md
```

### Key Structural Decisions

1. **`services/` layer between cogs and DB**: Cogs handle Discord interaction, services handle business logic. This makes services testable without Discord mocks.

2. **`listeners/` separate from `cogs/`**: Event listeners (XP on message, audit logging) are not commands — they don't have a prefix/slash trigger. Keeping them separate avoids bloating cogs.

3. **`views/` for persistent UI**: discord.py 2.x persistent views (buttons, modals) need to be registered on bot startup. Isolating them in `views/` makes this clean.

4. **`models/` as dataclasses**: Not SQLAlchemy models (Supabase client returns dicts). Dataclasses give type safety without ORM overhead.

5. **No `routes/` or `api/` in bot**: The webhook receiver is minimal (one endpoint). If it grows, extract to its own service.

---

## 3. Phased Development Order

### Phase 1: Core Foundation (Must exist first)
**Goal**: Bot connects to Discord, connects to DB, cache works, basic commands respond.

1. **Project scaffolding** — pyproject.toml, folder structure, .env, config.py
2. **Bot class** (`bot/bot.py`) — NebulosaBot extending commands.Bot, hybrid command setup, cog loading
3. **Database layer** (`bot/core/database.py`) — Supabase client init, connection health check
4. **Cache layer** (`bot/core/cache.py`) — TTLCache per guild, get/set/invalidate
5. **Guild service** (`bot/services/guild_service.py`) — Load guild config (cache-first), save config
6. **Core cog** (`bot/cogs/core.py`) — ping, status, help (custom), sync (tree sync)
7. **SQL migration 001** — Guild, User, Member, Infraction tables
8. **Custom context** (`bot/core/context.py`) — NebulosaContext with db/cache access

**Exit criteria**: Bot starts, connects to Discord + Supabase, `!ping` responds, guild config loads from DB with cache.

### Phase 2: Moderation (Sentinel)
**Goal**: Moderators can warn/mute/kick/ban. Infractions stored in DB. Auto-escalation works.

1. **Infraction service** — CRUD infractions, count active warnings
2. **Auto-escalation logic** — On warn: check threshold, apply mute/kick automatically
3. **Sentinel cog** — /warn, /unwarn, /mute, /unmute, /kick, /ban, /modlogs
4. **Permission checks** (`bot/utils/checks.py`) — is_mod(), is_admin() decorators
5. **SQL migration 002** — Infraction table (if not in 001)

**Exit criteria**: Mod can warn a user, 3 warns auto-mutes for 1h, /modlogs shows history.

### Phase 3: Tickets (Enterprise)
**Goal**: Full ticket lifecycle — panel, open, claim, close, transcript.

1. **Ticket service** — Create/close/claim tickets, sequential numbering per guild
2. **Ticket category model** — TicketCategory CRUD
3. **Persistent views** (`bot/views/ticket_views.py`) — Open/Close/Claim buttons, category dropdown
4. **Tickets cog** — /ticket_panel, /create_category
5. **Transcript service** — HTML generation, upload to Discord channel, store URL
6. **Auto-close task** — Background task checking `lastActivity` for stale tickets
7. **SQL migration 003** — Ticket, TicketCategory tables

**Exit criteria**: User opens ticket from panel, staff claims it, close generates transcript uploaded to log channel.

### Phase 4: Economy (Stellar)
**Goal**: XP per message, /daily coins, /rank image, /leaderboard.

1. **Economy service** — XP gain (with cooldown), daily claim, coin balance
2. **XP listener** (`bot/listeners/xp_listener.py`) — on_message XP gain
3. **Image service** (`bot/services/image_service.py`) — Pillow rank card generation
4. **Stellar cog** — /rank, /leaderboard, /daily, /coins
5. **SQL migration 004** — Add coins/lastDaily/lastXpGain to Member (or EconomyConfig table)

**Exit criteria**: User gains XP per message, /daily gives coins, /rank generates image card, /leaderboard shows top 10.

### Phase 5: Welcome/Goodbye + Logging
**Goal**: Join/leave messages with Pillow image card. All events logged to dedicated channel.

1. **Greetings cog** — on_member_join, on_member_remove handlers
2. **Image service extension** — Welcome/goodbye card generation (avatar, username, background)
3. **Audit listener** (`bot/listeners/audit_listener.py`) — message_edit/delete, member_join/leave, role changes, mod actions
4. **Logging cog** — Event routing to log channel
5. **SQL migration 005** — GreetingConfig (or add columns to Guild)

**Exit criteria**: New member gets welcome image + message in configured channel. Member leave logs goodbye. Message edits/deletes logged.

### Phase 6: Utility + Ocio + Polish
**Goal**: Remaining commands, error handling, rate limiting, production readiness.

1. **Utility cog** — /avatar, /serverinfo, /userinfo
2. **Ocio cog** — /dados, /banana
3. **Admin config cog** — In-Discord config commands (fallback when dashboard isn't ready)
4. **Webhook server** (`bot/core/webhook_server.py`) — Receive cache invalidation from dashboard
5. **Global error handler** — on_command_error, on_app_command_error
6. **Rate limiting** — Cooldown decorators on economy commands
7. **SQL migration 006** — EconomyConfig, AutoEscalationRule, LogConfig (if deferred)

**Exit criteria**: All commands work. Error messages are user-friendly. Bot survives restart with persistent views re-registered.

### Phase 7: Dashboard Integration (Future)
**Goal**: Next.js admin panel connects to bot via webhook.

1. **Dashboard scaffolding** — Next.js + Supabase auth
2. **Guild config pages** — Edit prefix, channels, roles
3. **Webhook client** — POST /webhook/sync on config changes
4. **Ticket viewer** — Browse closed tickets, read transcripts

---

## 4. Missing Architectural Patterns

The diagrams cover the **happy path** but miss several production-critical patterns:

### 4.1 Error Handling Strategy
**Missing**: No error handling flow in any diagram.
**Needed**:
- Global `on_app_command_error` handler in bot.py
- Per-command error handling (missing permissions, bot missing perms, cooldown)
- User-friendly error messages (embeds, not tracebacks)
- Logging errors to a dedicated error channel or file

### 4.2 Permission Model
**Missing**: Diagrams show "Admin" actor but no permission check flow.
**Needed**:
- `is_mod()` check: has modRoleId or Manage Server permission
- `is_admin()` check: has Administrator permission or guild owner
- Per-command permission decorators using discord.py's `@app_commands.check()`
- Graceful "you don't have permission" responses

### 4.3 Rate Limiting / Cooldowns
**Missing**: No cooldown patterns in diagrams.
**Needed**:
- discord.py built-in `@commands.cooldown()` for economy commands (/daily)
- XP cooldown (per-user, per-guild, configurable interval)
- Ticket creation cooldown (prevent spam)
- Rate limit on transcript generation (expensive operation)

### 4.4 Bot Startup & Recovery
**Missing**: No startup sequence diagram.
**Needed**:
- Cog loading order (core first, then modules)
- Persistent view re-registration on restart (ticket buttons must survive restarts)
- Cache warm-up strategy (load active guild configs on startup?)
- Graceful shutdown (close DB connections, finish pending tasks)

### 4.5 Multi-Guild Isolation
**Missing**: Diagrams show single-guild flows.
**Needed**:
- All cache keys must be guild-scoped: `cache[f"{guild_id}:config"]`
- All DB queries must filter by guild_id
- Background tasks (auto-close tickets, auto-escalation) must iterate all guilds
- Rate limits must be per-guild or per-guild-per-user

### 4.6 Configuration Hierarchy
**Missing**: No default value strategy.
**Needed**:
- Default guild config on bot join (INSERT with sensible defaults)
- Fallback chain: command arg > guild config > hardcoded default
- Config validation (channel exists, role exists, prefix not empty)

### 4.7 Data Consistency
**Missing**: Supabase Transaction Mode has no FK enforcement.
**Needed**:
- Application-level referential integrity checks
- Idempotent operations (double-click /warn shouldn't create 2 infractions)
- Soft deletes vs hard deletes strategy (Infraction.active for unwarn)

### 4.8 Observability
**Missing**: No monitoring/logging strategy.
**Needed**:
- Structured logging (Python `logging` module with JSON formatter)
- Guild join/leave tracking
- Command usage metrics (which commands are used most)
- Health check endpoint (for uptime monitoring)

---

## 5. discord.py Specific Decisions

### 5.1 Cogs vs Extensions
**Recommendation: Cogs loaded as extensions.**

In discord.py, "cogs" and "extensions" are complementary:
- A **cog** is a class that groups related commands/listeners (`commands.Cog`)
- An **extension** is a Python file loaded via `bot.load_extension("bot.cogs.sentinel")`

Each file in `cogs/` defines one cog class and an `async def setup(bot)` function. This is the standard pattern and gives:
- Hot-reload during development (`!reload sentinel`)
- Clean separation of concerns
- Easy to enable/disable modules per guild later

```python
# bot/cogs/sentinel.py
class Sentinel(commands.Cog):
    def __init__(self, bot: NebulosaBot):
        self.bot = bot

async def setup(bot: NebulosaBot):
    await bot.add_cog(Sentinel(bot))
```

### 5.2 Hybrid Commands (Prefix + Slash)
**Recommendation: Use `@commands.hybrid_command()` for all user-facing commands.**

discord.py 2.x provides `hybrid_command` which registers both a prefix command and a slash command from one definition:

```python
@commands.hybrid_command(name="warn", description="Warn a member")
@app_commands.describe(member="The member to warn", reason="Reason for the warning")
@commands.has_permissions(moderate_members=True)
async def warn(self, ctx: NebulosaContext, member: discord.Member, reason: str):
    ...
```

**Key considerations**:
- Prefix commands need `bot.command_prefix` to be a callable that reads guild config (cache-first)
- Slash commands need `tree.sync()` after startup (and after adding new commands)
- Some features differ: prefix commands can have flexible argument parsing, slash commands have strict types
- Use `ctx.send()` — it works for both (discord.py handles the response type)

**Prefix setup**:
```python
async def get_prefix(bot, message):
    if not message.guild:
        return "!"
    config = await bot.guild_service.get_config(message.guild.id)
    return config.prefix or "!"
```

### 5.3 Persistent Views (Buttons/Modals)
**Recommendation: Define views as classes, register on startup with `bot.add_view()`.**

For ticket buttons that must survive bot restarts:

```python
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent (no timeout)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ...

# In cog setup or bot startup:
bot.add_view(TicketPanelView())
```

**Key rules**:
- `custom_id` is mandatory for persistent views (must be static/predictable)
- `timeout=None` makes the view persistent
- Must call `bot.add_view()` on every startup (even if the message already exists)
- Store the message ID of the ticket panel so you can re-register the view on restart
- For modals (text input forms), use `discord.ui.Modal` — these are NOT persistent (they're ephemeral)

### 5.4 Background Tasks
**Recommendation: Use `@tasks.loop()` for periodic jobs.**

```python
from discord.ext import tasks

class TicketAutoClose(commands.Cog):
    def __init__(self, bot):
        self.check_stale_tickets.start()

    @tasks.loop(hours=1)
    async def check_stale_tickets(self):
        stale = await self.ticket_service.get_stale_tickets(hours=48)
        for ticket in stale:
            await self.ticket_service.close(ticket.id, reason="Inactivity")
```

### 5.5 App Command Tree Error Handling
```python
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Handle MissingPermissions, CommandOnCooldown, etc.
    ...
```

---

## Recommendation

Proceed with **Phase 1 (Core Foundation)** as the first SDD change. The foundation must be solid before any module work begins. The exploration reveals:

1. **Data model needs expansion** — 3-4 new tables minimum (TicketCategory, GreetingConfig, EconomyConfig). Start with core tables in Phase 1, add feature tables per phase.
2. **Service layer is critical** — Without it, cogs become untestable blobs. Build it from day one.
3. **Cache design needs detail** — The sequence diagram shows the pattern but not the implementation (TTL? eviction? key format?). This should be part of Phase 1 design.
4. **Coins scope needs clarification** — "Global coins" vs "per-guild coins" changes the schema. Recommend per-guild first (simpler, consistent with XP).

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Supabase Transaction Mode has no FK enforcement | Data inconsistency | Application-level checks in services, validate before write |
| Pillow image generation blocks event loop | Bot lag on /rank and welcome | Run in `asyncio.to_thread()` or executor |
| Persistent views break on bot restart if not re-registered | Ticket buttons stop working | `bot.add_view()` on startup, store panel message IDs in DB |
| Cache desync if webhook fails | Stale config served | TTL on cache entries (e.g., 5 min), force refresh on miss |
| discord.py hybrid commands have edge cases | Prefix and slash behave differently | Test both modes for every command, document differences |
| Multi-guild background tasks scale poorly | Auto-close ticks take too long at 100+ guilds | Batch queries, use `asyncio.gather()` with limits |

---

## Ready for Proposal

**Yes.** The exploration is complete. The orchestrator should tell the user:

> "The exploration is done. We've identified 6 missing data entities, recommended a 7-phase development order starting with Core Foundation, and flagged 3 open questions (coins scope, welcome/goodbye table design, log granularity). The next step is to create a **proposal** for Phase 1 (Core Foundation) — this covers bot scaffolding, DB connection, cache layer, and basic commands. Want to proceed?"
