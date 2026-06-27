# Design: Phase 5 — Welcome/Goodbye + Audit Logging

## Technical Approach

Extend the bot with two feature domains: (1) configurable welcome/goodbye cards on member join/leave, and (2) centralized audit logging for 7 Discord event types. Greeting config lives in a dedicated `greeting_config` table (mirroring the `economy_config` pattern). Card generation extends `ImageService` reusing existing Pillow infrastructure. A new `LoggingService` extracts `SentinelCog._log_action()` into a shared service consumed by both `SentinelCog` and a new `AuditListener`.

## Architecture Decisions

| # | Decision | Options | Tradeoff | Choice | Rationale |
|---|----------|---------|----------|--------|-----------|
| 1 | Greeting config storage | A) Columns on `guild` B) Separate `greeting_config` table | A) single query but guild table bloat B) extra table but clean separation | **B** | Follows `economy_config` precedent (PK→guild FK). Guild table already at 11 cols; adding 6+ for a distinct domain violates SRP. Independently cacheable. |
| 2 | Welcome card generation | A) Extend `ImageService` B) New `WelcomeCardService` | A) reuses 80% of Pillow infra B) single-responsibility but duplicates avatar/font/gradient | **A** | `ImageService` already owns `_fetch_avatar()`, `_load_font()`, gradient logic. Same sync + `asyncio.to_thread()` contract. |
| 3 | Audit logging architecture | A) Centralized `LoggingService` B) Per-cog helpers | A) single source of truth B) no cross-cog dep but duplicates 57-line `_log_action()` | **A** | `SentinelCog._log_action()` is 57 lines called 9×. Duplicating into AuditListener is unacceptable. Central service = consistent embed format + single config resolution path. |
| 4 | Extension structure | A) `GreetingsCog` + `AuditListener` B) Single combined cog | A) clear separation B) fewer files but mixes concerns | **A** | GreetingsCog is user-facing (commands + visual cards). AuditListener is passive event sink. Different test strategies. Follows `XPListener` precedent. |
| 5 | Channel visibility filter | Check `@everyone` read_messages overwrite per channel | Skips logging for private channels | **Yes** | Per proposal spec. Implemented as helper in `LoggingService._can_log_in_channel()`. |

## Data Flow

### Welcome Card (join)

```
on_member_join(member)
    │
    ▼
GreetingsCog
    │── greeting_service.get_config(guild_id)  [cache-first]
    │── if not enabled or no channel → return
    │── image_service.generate_greeting_card(...)  [sync → to_thread]
    │── channel.send(file=discord.File(buffer))
    ▼
  Discord Channel
```

### Audit Log (message edit)

```
on_message_edit(before, after)
    │
    ▼
AuditListener
    │── early exits: bot? DM? own message? log channel itself?
    │── logging_service.log_message_edit(guild_id, before, after)
    │       │── guild_service.get_config()  [cache-first]
    │       │── if not log_enabled → return
    │       │── _can_log_in_channel(source_channel) → skip if private
    │       │── build embed (before/after fields)
    │       │── log_channel.send(embed=embed)
    │       ▼
    │     Discord Log Channel
```

### SentinelCog Refactor

```
Before:  SentinelCog._log_action(guild_id, action, target, mod, reason)
         → inline config resolve + embed build + send

After:   SentinelCog → self.bot.logging_service.log_moderation_action(...)
         AuditListener → self.bot.logging_service.log_message_edit(...)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/004_greeting_config.sql` | Create | `greeting_config` table + columns |
| `bot/models/greeting_config.py` | Create | `GreetingConfig` dataclass (follows `EconomyConfig` pattern) |
| `bot/services/logging_service.py` | Create | Centralized log routing: config resolve + embed builders + send |
| `bot/services/greeting_service.py` | Create | Greeting config CRUD + card dispatch logic |
| `bot/cogs/greetings.py` | Create | `GreetingsCog`: `on_member_join/remove` + `/welcome` `/goodbye` cmds |
| `bot/listeners/audit_listener.py` | Create | `AuditListener`: 5 passive listeners (edit/delete/member_update/channel_create/delete) |
| `bot/services/image_service.py` | Modify | Add `generate_greeting_card(username, avatar_url, guild_name, member_count, card_type)` |
| `bot/core/database.py` | Modify | Add `get_greeting_config()` + `upsert_greeting_config()` |
| `bot/cogs/sentinel.py` | Modify | Replace all 9 `_log_action()` calls with `self.bot.logging_service.log_moderation_action()`; remove `_log_action()` |
| `bot/bot.py` | Modify | Init `LoggingService`, `GreetingService`; load `greetings` + `audit_listener` extensions |
| `tests/test_logging_service.py` | Create | Unit tests for LoggingService embed building + routing |

## Interfaces / Contracts

```python
@dataclass
class GreetingConfig:
    guild_id: str                          # PK, FK → guild(id)
    welcome_enabled: bool = False
    goodbye_enabled: bool = False
    welcome_channel_id: str | None = None
    goodbye_channel_id: str | None = None
    welcome_message: str | None = None     # template: {mention}, {server}, {count}
    goodbye_message: str | None = None
    welcome_card_enabled: bool = True      # image card vs text-only
    goodbye_card_enabled: bool = True

class LoggingService:
    def __init__(self, bot: NebulosaBot) -> None: ...
    async def log_moderation_action(self, guild_id: str, action: str,
        target: discord.Member | discord.User, moderator: discord.Member,
        reason: str) -> None: ...
    async def log_message_edit(self, guild_id: str,
        before: discord.Message, after: discord.Message) -> None: ...
    async def log_message_delete(self, guild_id: str,
        message: discord.Message) -> None: ...
    async def log_member_join(self, guild_id: str,
        member: discord.Member) -> None: ...
    async def log_member_leave(self, guild_id: str,
        member: discord.Member) -> None: ...
    async def log_member_update(self, guild_id: str,
        before: discord.Member, after: discord.Member) -> None: ...
    async def log_channel_create(self, guild_id: str,
        channel: discord.abc.GuildChannel) -> None: ...
    async def log_channel_delete(self, guild_id: str,
        channel: discord.abc.GuildChannel) -> None: ...

class GreetingService:
    def __init__(self, db: Database, cache: TTLCache,
        image_service: ImageService) -> None: ...
    async def get_config(self, guild_id: str) -> GreetingConfig: ...
    async def save_config(self, config: GreetingConfig) -> None: ...
    async def dispatch_welcome(self, member: discord.Member) -> None: ...
    async def dispatch_goodbye(self, member: discord.Member,
        guild: discord.Guild) -> None: ...

# ImageService addition:
def generate_greeting_card(self, username: str, avatar_url: str | None,
    guild_name: str, member_count: int,
    card_type: str = "welcome") -> io.BytesIO: ...
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `LoggingService` embed building | Mock `guild_service.get_config()` + channel.send; verify embed fields per event type |
| Unit | `LoggingService` routing guards | Test disabled logging, missing channel, private channel skip |
| Unit | `GreetingService` dispatch | Mock ImageService + channel; verify card sent when enabled, skipped when disabled |
| Unit | `ImageService.generate_greeting_card()` | Verify returns BytesIO PNG; test avatar fetch failure graceful fallback |
| Unit | `SentinelCog` refactor | Verify all 9 handlers call `logging_service.log_moderation_action()` with correct args |
| Unit | `AuditListener` early exits | Bot messages, DMs, own messages, log channel itself — all return early |

## Migration / Rollout

```sql
-- migrations/004_greeting_config.sql
CREATE TABLE IF NOT EXISTS greeting_config (
    "guildId"            TEXT PRIMARY KEY REFERENCES guild(id) ON DELETE CASCADE,
    "welcomeEnabled"     BOOLEAN NOT NULL DEFAULT FALSE,
    "goodbyeEnabled"     BOOLEAN NOT NULL DEFAULT FALSE,
    "welcomeChannelId"   TEXT,
    "goodbyeChannelId"   TEXT,
    "welcomeMessage"     TEXT,
    "goodbyeMessage"     TEXT,
    "welcomeCardEnabled" BOOLEAN NOT NULL DEFAULT TRUE,
    "goodbyeCardEnabled" BOOLEAN NOT NULL DEFAULT TRUE
);
```

Existing `guild.welcome_enabled` column is left as-is (non-destructive). Code ignores it in favor of `greeting_config.welcome_enabled`. Rollback: `DROP TABLE greeting_config`, remove new extensions from `bot.py`, restore `_log_action()` from git.

## Open Questions

- [ ] Should `goodbye_card_enabled` default to `True` or `False`? Goodbye cards are less common than welcome cards — defaulting to `False` may reduce surprise.
- [ ] Should `AuditListener` skip messages in ticket channels (already logged by ticket system)?
