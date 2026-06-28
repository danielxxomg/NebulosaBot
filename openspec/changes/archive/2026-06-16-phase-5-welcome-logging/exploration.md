## Exploration: Phase 5 — Welcome/Goodbye + Audit Logging

### Current State

**Guild model** (`bot/models/guild.py`):
- Already has `log_channel_id`, `log_enabled`, `welcome_enabled` as simple columns on the `guild` table
- No dedicated greeting config (channel, message template, card toggle, background URL)
- No goodbye config at all

**ImageService** (`bot/services/image_service.py`):
- Generates rank cards with Pillow: gradient background, circular avatar, fonts, XP bar
- All synchronous — callers wrap in `asyncio.to_thread()`
- Has `_fetch_avatar()` and `_load_font()` helpers that are directly reusable
- Font dir: `assets/fonts/Inter-Regular.ttf`

**Logging today** (`bot/cogs/sentinel.py`):
- `SentinelCog._log_action()` is a **private helper** — duplicates per cog that needs logging
- Reads `guild_service.get_config()`, checks `log_enabled` + `log_channel_id`, sends embed
- Only covers moderation actions (warn/mute/kick/ban/lock/unlock)

**Listener pattern** (`bot/listeners/xp_listener.py`):
- Uses `@commands.Cog.listener()` decorator
- Guards: `message.author.bot`, `not message.guild`
- Loaded as `bot.listeners.xp_listener` extension

**Migrations**: 001 (initial), 002 (ticket_categories), 003 (economy_config) — next is 004

**Existing mod-logging spec** (`openspec/specs/mod-logging/spec.md`):
- Covers moderation action embeds only
- Does NOT cover audit events (message edit/delete, role changes, channel changes)

### Affected Areas

- `bot/models/guild.py` — needs new fields or a new GreetingConfig model
- `bot/services/image_service.py` — add `generate_welcome_card()` method
- `bot/services/guild_service.py` — add greeting config CRUD (or new GreetingService)
- `bot/core/database.py` — add greeting_config queries
- `bot/cogs/sentinel.py` — refactor `_log_action()` to use centralized LoggingService
- `bot/listeners/xp_listener.py` — pattern reference for new listeners
- `bot/bot.py` — wire new services and load new cog extensions
- `migrations/004_greeting_config.sql` — new table
- `bot/utils/embeds.py` — may add log-specific embed helpers

### Approaches

#### 1. Greeting Config Storage

**Approach A: New `greeting_config` table (recommended)**

Separate table following the `economy_config` pattern:
```sql
CREATE TABLE greeting_config (
    "guildId"           TEXT PRIMARY KEY REFERENCES guild(id),
    "welcomeEnabled"    BOOLEAN NOT NULL DEFAULT FALSE,
    "goodbyeEnabled"    BOOLEAN NOT NULL DEFAULT FALSE,
    "welcomeChannelId"  TEXT,
    "goodbyeChannelId"  TEXT,
    "welcomeMessage"    TEXT,          -- template with {mention}, {server}, {count}
    "goodbyeMessage"    TEXT,
    "welcomeCardEnabled" BOOLEAN NOT NULL DEFAULT TRUE,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- Pros: Clean separation, follows existing `economy_config` pattern, independently cacheable, easy to extend (custom backgrounds, embed colors)
- Cons: Extra table, extra DB query (mitigated by cache-first)
- Effort: Low

**Approach B: Add columns to `guild` table**

Add `welcomeChannelId`, `goodbyeChannelId`, `welcomeMessage`, `goodbyeMessage`, `welcomeCardEnabled` to the existing `guild` table.

- Pros: No new table, single query for all guild config
- Cons: Guild table keeps growing, `welcome_enabled` already exists and becomes redundant, harder to cache independently
- Effort: Low

**Recommendation: Approach A** — `greeting_config` table. The guild table is already at 11 columns; adding 5 more for a distinct feature domain violates single-responsibility. The `economy_config` precedent proves this pattern works.

---

#### 2. Welcome Card Image Generation

**Approach A: Extend ImageService with `generate_welcome_card()`**

Add a new public method alongside `generate_rank_card()`. Reuses `_fetch_avatar()`, `_load_font()`, gradient background logic.

Layout: 934x282 (same as rank card), dark gradient, circular avatar left, "Welcome" text + username + guild name + member count right side.

- Pros: Zero new infrastructure, reuses avatar fetch + font loading + gradient pattern, same `asyncio.to_thread()` contract
- Cons: ImageService grows (but it's the right home for it)
- Effort: Low

**Approach B: New WelcomeCardService**

Separate service just for welcome/goodbye cards.

- Pros: Single responsibility
- Cons: Duplicates avatar fetch, font loading, gradient logic — unnecessary code duplication
- Effort: Medium

**Recommendation: Approach A** — extend ImageService. The service is already the Pillow image generation hub; welcome cards share 80% of the infrastructure.

---

#### 3. Audit Logging Architecture

**Approach A: Centralized LoggingService (recommended)**

Extract `SentinelCog._log_action()` into a new `LoggingService` with typed event methods:
```python
class LoggingService:
    async def log_moderation_action(guild_id, action, target, moderator, reason)
    async def log_member_join(guild_id, member)
    async def log_member_leave(guild_id, member)
    async def log_message_edit(guild_id, before, after)
    async def log_message_delete(guild_id, message)
    async def log_role_change(guild_id, member, before_roles, after_roles)
    async def log_channel_change(guild_id, action, channel)
```

Each method: resolve config → check enabled → build embed → send to channel. SentinelCog and AuditListener both call this service.

- Pros: Single source of truth for log routing, consistent embed format, no duplication, easy to add new event types
- Cons: New service to wire up
- Effort: Medium

**Approach B: Per-cog logging helpers**

Each cog/listener implements its own `_send_log()` helper (like SentinelCog does today).

- Pros: No cross-cog dependency
- Cons: Duplicates config resolution + embed building + error handling across 2+ cogs, inconsistent formatting
- Effort: Low

**Recommendation: Approach A** — centralized LoggingService. The duplication cost is real: SentinelCog already has 57 lines of `_log_action()` that would be copy-pasted into the audit listener.

---

#### 4. Cog/Listener Structure

**Approach A: Two new extensions**

- `bot/cogs/greetings.py` — GreetingsCog with `on_member_join` + `on_member_remove` + `/welcome` + `/goodbye` config commands
- `bot/listeners/audit_listener.py` — AuditListener with `on_message_edit`, `on_message_delete`, `on_member_update`, `on_guild_channel_create`, `on_guild_channel_delete`

- Pros: Clear separation — greetings is interactive (commands + welcome cards), audit is passive (event-driven). Follows existing pattern (XPListener is separate from cogs)
- Cons: Two new files
- Effort: Medium

**Approach B: Single combined cog**

One `LoggingCog` with all listeners + config commands.

- Pros: Fewer files
- Cons: Mixes concerns — greeting card generation is unrelated to audit message-edit tracking. Cog becomes large and hard to navigate
- Effort: Medium

**Recommendation: Approach A** — two extensions. GreetingsCog is user-facing (commands + visual cards); AuditListener is a passive event sink. Different responsibilities, different test strategies.

---

#### 5. Performance: High-Frequency Events

`on_message_edit` and `on_message_delete` fire on EVERY message edit/delete in every guild the bot is in.

**Strategy:**
1. **Early exit guards**: ignore bots, DMs, own messages, and the log channel itself
2. **Cache-first config**: `LoggingService` reads `guild_service.get_config()` which is already cached (5-min TTL)
3. **Skip when disabled**: if `log_enabled` is false, return immediately — no embed building
4. **Content truncation**: limit before/after content to 1024 chars (Discord embed field limit)
5. **No image generation for audit**: audit events use text embeds only (no Pillow)
6. **Debounce consideration**: NOT needed — Discord rate-limits gateway events per connection; the bot naturally throttles

### Recommendation (Summary)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Greeting config | New `greeting_config` table | Follows `economy_config` pattern, clean separation |
| Welcome card | Extend `ImageService` | Reuses 80% of existing Pillow infrastructure |
| Audit logging | Centralized `LoggingService` | Eliminates duplication from SentinelCog._log_action() |
| Cog structure | GreetingsCog + AuditListener | Clear separation of concerns |
| Performance | Early exits + cache-first | No special infrastructure needed |

### New Files to Create

| File | Purpose |
|------|---------|
| `migrations/004_greeting_config.sql` | greeting_config table |
| `bot/models/greeting_config.py` | GreetingConfig dataclass |
| `bot/services/logging_service.py` | Centralized audit log routing |
| `bot/services/greeting_service.py` | Greeting config CRUD + card dispatch |
| `bot/cogs/greetings.py` | GreetingsCog (join/leave + config commands) |
| `bot/listeners/audit_listener.py` | AuditListener (edit/delete/role/channel events) |

### Existing Files to Modify

| File | Change |
|------|--------|
| `bot/services/image_service.py` | Add `generate_welcome_card()` method |
| `bot/core/database.py` | Add greeting_config CRUD methods |
| `bot/cogs/sentinel.py` | Replace `_log_action()` with `LoggingService` calls |
| `bot/bot.py` | Wire LoggingService, GreetingService; load new extensions |
| `bot/models/guild.py` | Remove `welcome_enabled` (moved to greeting_config) |

### Risks

1. **`on_message_edit` volume** — In large servers (10k+ members), message edits can be very frequent. Mitigated by early-exit guards and cache-first config check. If still too noisy, add a per-guild opt-in for message edit logging specifically.

2. **Avatar fetch failures on join** — New members may have no avatar or a slow CDN. ImageService already handles this gracefully (returns placeholder).

3. **`welcome_enabled` column migration** — The existing `guild.welcome_enabled` column becomes dead. Migration 004 should either drop it or leave it as deprecated. Recommend leaving it and ignoring it in code (non-destructive).

4. **SentinelCog refactor scope** — Replacing `_log_action()` with LoggingService calls touches 9 command handlers. Low risk (mechanical refactor) but must be tested to avoid breaking moderation logging.

5. **Intents requirement** — `on_message_edit/delete` requires `Intents.message_content`. `on_member_update` (roles) requires `Intents.members`. These should already be enabled for Phase 2-4 but must be verified.

### Ready for Proposal

**Yes.** The exploration has enough detail to proceed to `sdd-propose`. The orchestrator should tell the user:

> Phase 5 exploration complete. We'll create a `greeting_config` table (like economy_config), extend ImageService with welcome card generation, build a centralized LoggingService to replace SentinelCog's private logging helper, and add two new extensions: GreetingsCog (welcome/goodbye + config commands) and AuditListener (message edit/delete, role changes, channel changes). Ready to move to proposal.
