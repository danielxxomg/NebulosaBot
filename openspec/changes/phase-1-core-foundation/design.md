# Design: Phase 1 — Core Foundation

## Technical Approach

Runnable skeleton: bot connects to Discord + Supabase, cache serves guild config, minimal commands prove the stack. All infrastructure — no feature modules. Follows `DiagramaSecuencia.mmd` cache-first pattern and `DiagramaEntidad-Relación.mmd` base schema.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Bot class | `NebulosaBot(commands.Bot)` with `setup_hook()` | Multiple bot instances, raw `on_ready` loading | Single class, discord.py 2.x idiom, cog loading before gateway connects |
| Prefix resolution | Async callable reading cache-first guild config | Static prefix, middleware chain | Dynamic per-guild prefix, cache avoids DB hit on every message |
| Cache | Dict-based TTL (5 min), guild-scoped keys `{guild_id}:{entity}` | Redis, aiocache | Phase 1 simplicity — no external deps, TTL covers webhook desync window |
| Database | Supabase Python client (`supabase-py`), async via `AsyncPostgrestClient` | SQLAlchemy, raw asyncpg | Matches stack decision in config.yaml, Supabase manages infra |
| Error handling | Global `on_app_command_error` + per-command overrides | Per-cog handlers only | Centralized fallback, ephemeral embeds for slash, channel embeds for prefix |
| Permission model | `@app_commands.check()` decorators reading guild config (`modRoleId`) + Discord perms | Custom middleware, role hierarchy table | discord.py native pattern, composable with `@commands.has_permissions()` |
| Models | Python `dataclasses` mirroring DB rows | Pydantic, SQLAlchemy ORM | Supabase returns dicts — dataclasses give type safety without ORM overhead |
| Context | `NebulosaContext` with `db`, `cache`, `guild_config` shortcuts | Raw `commands.Context`, pass services manually | Ergonomic access to services in every command handler |

## Data Flow

### Cache-First Command Read (from DiagramaSecuencia.mmd)

```
  Command (!help / /help)
       │
       ▼
  NebulosaBot.get_prefix()
       │
       ▼
  GuildService.get_config(guild_id)
       │
       ├── Cache HIT → return cached GuildConfig
       │
       └── Cache MISS
            │
            ▼
         Database.get_guild(guild_id)
            │
            ▼
         Cache.set(key, config, ttl=300)
            │
            ▼
         return GuildConfig
```

### Bot Startup Sequence

```
  python -m bot
       │
       ▼
  config.py → load .env, validate required vars
       │
       ▼
  NebulosaBot.__init__() → init intents, set command_prefix callable
       │
       ▼
  bot.run() → Discord gateway connects
       │
       ▼
  setup_hook()
       ├── Database.connect() → health check
       ├── Cache.__init__() → empty TTL store
       ├── GuildService.__init__(db, cache)
       ├── load_extension("bot.cogs.core")
       └── tree.sync() → register slash commands globally
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Create | Project metadata, Python 3.11+, deps: discord.py>=2.3, supabase-py, python-dotenv |
| `requirements.txt` | Create | Pinned deps for reproducible installs |
| `.env.example` | Create | Template: DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY |
| `bot/__init__.py` | Create | Package init, version constant |
| `bot/__main__.py` | Create | Entry point: `python -m bot` — loads config, instantiates bot, calls `bot.run()` |
| `bot/bot.py` | Create | `NebulosaBot(commands.Bot)` — `setup_hook()`, `get_prefix()`, `on_app_command_error` |
| `bot/config.py` | Create | Env loading via `python-dotenv`, `BotConfig` dataclass with validation |
| `bot/core/__init__.py` | Create | Core subpackage init |
| `bot/core/cache.py` | Create | `TTLCache` — dict-based, `get/set/invalidate/invalidate_guild`, 5min default TTL |
| `bot/core/database.py` | Create | `Database` — wraps Supabase client, `connect()`, `health_check()`, table accessors |
| `bot/core/context.py` | Create | `NebulosaContext` — extends `commands.Context` with `db`, `cache`, `guild_config` |
| `bot/models/__init__.py` | Create | Models subpackage init |
| `bot/models/guild.py` | Create | `GuildConfig` dataclass — mirrors Guild table |
| `bot/models/member.py` | Create | `Member` dataclass — mirrors Member table |
| `bot/models/ticket.py` | Create | `Ticket` dataclass — mirrors Ticket table |
| `bot/models/infraction.py` | Create | `Infraction` dataclass — mirrors Infraction table |
| `bot/services/__init__.py` | Create | Services subpackage init |
| `bot/services/guild_service.py` | Create | `GuildService` — `get_config()` (cache-first), `save_config()`, `on_guild_join()` |
| `bot/cogs/__init__.py` | Create | Cogs subpackage init |
| `bot/cogs/core.py` | Create | `CoreCog` — ping, status, help (embed by module), sync (tree sync) |
| `bot/utils/__init__.py` | Create | Utils subpackage init |
| `bot/utils/checks.py` | Create | `is_mod()`, `is_admin()` — app_commands.check decorators |
| `bot/utils/embeds.py` | Create | `error_embed()`, `success_embed()`, `info_embed()` helpers |
| `migrations/001_initial_schema.sql` | Create | Tables: Guild, User, Member, Infraction, Ticket (per ER diagram) |

**Total**: 24 new files, 0 modified, 0 deleted.

## Interfaces / Contracts

### TTLCache
```python
class TTLCache:
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int = 300) -> None: ...
    def invalidate(self, key: str) -> None: ...
    def invalidate_guild(self, guild_id: int) -> None: ...
```

### Database
```python
class Database:
    async def connect(self) -> None: ...
    async def health_check(self) -> bool: ...
    async def get_guild(self, guild_id: int) -> dict | None: ...
    async def upsert_guild(self, config: GuildConfig) -> None: ...
```

### GuildService
```python
class GuildService:
    async def get_config(self, guild_id: int) -> GuildConfig: ...
    async def save_config(self, config: GuildConfig) -> None: ...
    async def on_guild_join(self, guild_id: int) -> GuildConfig: ...
```

### NebulosaContext
```python
class NebulosaContext(commands.Context):
    db: Database
    cache: TTLCache
    guild_config: GuildConfig
```

### Migration 001 Schema (core tables from ER diagram)
- **Guild**: id (PK, bigint), prefix, language, modRoleId, logChannelId, ticketCategoryId, active
- **User**: id (PK, bigint), username, avatarUrl, lastSeen
- **Member**: guildId (FK), userId (FK), xp, level, warnings — composite PK (guildId, userId)
- **Infraction**: id (PK, uuid), guildId (FK), targetId (FK), moderatorId (FK), type, reason, createdAt
- **Ticket**: id (PK, uuid), ticketId (int), guildId (FK), authorId (FK), status, transcriptUrl, createdAt, closedAt

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | TTLCache get/set/invalidate/expiry | pytest with mocked time |
| Unit | GuildService cache-first logic | pytest with mocked Database + Cache |
| Unit | Permission checks (is_mod, is_admin) | pytest with mocked discord.Member/Role |
| Integration | Database connect + health_check | pytest against Supabase local or test project |
| Manual | Bot starts, ping responds (prefix + slash) | Run `python -m bot`, test in Discord dev server |

## Migration / Rollout

No production data exists. Migration 001 runs once against Supabase SQL editor. Tables created in dependency order: Guild → User → Member → Infraction → Ticket. Rollback: drop tables in reverse order.

## Open Questions

- [ ] Coins scope (global vs per-guild) deferred to Phase 4 — Phase 1 Member table has no coins column
- [ ] Supabase Transaction Mode FK enforcement — app-level validation in GuildService for now
