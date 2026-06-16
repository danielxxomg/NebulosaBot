# Tasks: Phase 1 — Core Foundation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1100 (24 new files) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Scaffolding, config, models, migration, utils | PR 1 | ~14 files, all leaf deps; base: main |
| 2 | Core infra, services, bot, cogs | PR 2 | ~7 files, wires everything; depends on PR 1 |
| 3 | Tests & verification | PR 3 | pytest setup + unit tests; depends on PR 2 |

## Phase 1: Foundation (Scaffolding, Config, Models, Migration, Utils)

- [x] 1.1 Create `pyproject.toml` with Python 3.11+, deps (discord.py>=2.3, supabase-py, python-dotenv), and project metadata
- [x] 1.2 Create `requirements.txt` with pinned versions for reproducible installs
- [x] 1.3 Create `.env.example` with DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY placeholders
- [x] 1.4 Create `bot/__init__.py` with `__version__` constant
- [x] 1.5 Create `bot/config.py` — `BotConfig` dataclass, `python-dotenv` loading, validation of required vars
- [x] 1.6 Create `bot/models/__init__.py` (empty subpackage init)
- [x] 1.7 Create `bot/models/guild.py` — `GuildConfig` dataclass mirroring Guild table columns
- [x] 1.8 Create `bot/models/member.py` — `Member` dataclass mirroring Member table columns
- [x] 1.9 Create `bot/models/ticket.py` — `Ticket` dataclass mirroring Ticket table columns
- [x] 1.10 Create `bot/models/infraction.py` — `Infraction` dataclass mirroring Infraction table columns
- [x] 1.11 Create `bot/utils/__init__.py` (empty subpackage init)
- [x] 1.12 Create `bot/utils/checks.py` — `is_mod()` and `is_admin()` as `@app_commands.check()` decorators reading guild config + Discord perms
- [x] 1.13 Create `bot/utils/embeds.py` — `error_embed()`, `success_embed()`, `info_embed()` helpers with consistent styling
- [x] 1.14 Create `migrations/001_initial_schema.sql` — Guild, User, Member, Infraction, Ticket tables in FK dependency order with all columns per spec

## Phase 2: Core Infrastructure (Database, Cache, Context)

- [ ] 2.1 Create `bot/core/__init__.py` (empty subpackage init)
- [ ] 2.2 Create `bot/core/database.py` — `Database` class wrapping Supabase client with `connect()`, `health_check()`, `get_guild()`, `upsert_guild()`
- [ ] 2.3 Create `bot/core/cache.py` — `TTLCache` class with `get()`, `set()`, `invalidate()`, `invalidate_guild()`, 5min default TTL, dict-based with timestamp tracking
- [ ] 2.4 Create `bot/core/context.py` — `NebulosaContext` extending `commands.Context` with `db`, `cache`, `guild_config` accessors

## Phase 3: Services (GuildService)

- [ ] 3.1 Create `bot/services/__init__.py` (empty subpackage init)
- [ ] 3.2 Create `bot/services/guild_service.py` — `GuildService` with `get_config()` (cache-first → DB fallback → cache populate), `save_config()` (DB upsert + cache invalidate), `on_guild_join()` (insert defaults: prefix=`nb!`, language=`es`)

## Phase 4: Bot & Cogs (NebulosaBot, CoreCog, Entry Point)

- [ ] 4.1 Create `bot/bot.py` — `NebulosaBot(commands.Bot)` with `setup_hook()` (DB connect → cache init → GuildService init → cog load → tree sync), async `get_prefix()` reading cache-first guild config, `on_app_command_error` (ephemeral embed for slash, channel embed for prefix)
- [ ] 4.2 Create `bot/cogs/__init__.py` (empty subpackage init)
- [ ] 4.3 Create `bot/cogs/core.py` — `CoreCog` with hybrid commands: `ping` (latency ms), `status` (DB+cache health embed), `help` (embed by module with pagination), `sync` (tree sync, admin-gated)
- [ ] 4.4 Create `bot/__main__.py` — entry point: load config → instantiate `NebulosaBot` with intents + prefix callable → `bot.run()`

## Phase 5: Testing & Verification

- [ ] 5.1 Add pytest + pytest-asyncio to `pyproject.toml` dev deps; create `tests/__init__.py` and `tests/conftest.py` with shared fixtures (mock DB, mock cache, mock guild)
- [ ] 5.2 Create `tests/test_cache.py` — unit tests for TTLCache: get/set, TTL expiry, invalidate, invalidate_guild, guild isolation
- [ ] 5.3 Create `tests/test_guild_service.py` — unit tests for GuildService: cache hit path, cache miss → DB fetch → cache populate, save invalidates cache, on_guild_join inserts defaults
- [ ] 5.4 Create `tests/test_checks.py` — unit tests for is_mod/is_admin: admin perms, mod role, admin fallback, regular user denied, unconfigured mod role
- [ ] 5.5 Manual verification: run `python -m bot`, confirm bot comes online, test `nb!ping` and `/ping` in dev server, verify guild config loads into cache
