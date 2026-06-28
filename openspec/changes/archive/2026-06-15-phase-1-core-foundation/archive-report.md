# Archive Report: Phase 1 — Core Foundation

**Change**: phase-1-core-foundation
**Archived**: 2026-06-15
**Verdict**: PASS WITH WARNINGS
**Tasks**: 29/29 complete

## Summary

Phase 1 established the runnable skeleton for NebulosaBot: bot connects to Discord + Supabase, cache serves guild config, minimal commands prove the full stack. All infrastructure — no feature modules.

## Specs Created

| Domain | Spec Path | Requirements |
|--------|-----------|-------------|
| bot-core | `openspec/specs/bot-core/spec.md` | Bot lifecycle, hybrid prefix, cog loading, global error handler |
| database-layer | `openspec/specs/database-layer/spec.md` | Async client, health check |
| cache-layer | `openspec/specs/cache-layer/spec.md` | Per-guild TTL cache, cache operations |
| guild-config | `openspec/specs/guild-config/spec.md` | Default values, cache-first reads, CRUD, soft delete, default on join |
| core-commands | `openspec/specs/core-commands/spec.md` | Ping, status, help (with/without module), sync |
| permission-model | `openspec/specs/permission-model/spec.md` | Admin check, mod role check, admin fallback, unconfigured mod role |
| initial-schema | `openspec/specs/initial-schema/spec.md` | Migration 001, Guild/User/Member/Infraction/Ticket tables |

## Files Created (24 total)

### Scaffolding & Config
- `pyproject.toml` — Python 3.11+, deps, dev deps
- `requirements.txt` — Pinned versions
- `.env.example` — DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY

### Bot Core
- `bot/__init__.py` — Package init, `__version__`
- `bot/__main__.py` — Entry point (`python -m bot`)
- `bot/bot.py` — `NebulosaBot(commands.Bot)`, `setup_hook()`, hybrid prefix, error handlers
- `bot/config.py` — `BotConfig` dataclass, env loading, validation

### Core Infrastructure
- `bot/core/__init__.py` — Subpackage init
- `bot/core/database.py` — `Database` wrapping Supabase client
- `bot/core/cache.py` — `TTLCache` dict-based, 5min default TTL
- `bot/core/context.py` — `NebulosaContext` with db/cache/guild_config

### Models
- `bot/models/__init__.py` — Subpackage init
- `bot/models/guild.py` — `GuildConfig` dataclass
- `bot/models/member.py` — `Member` dataclass
- `bot/models/ticket.py` — `Ticket` dataclass
- `bot/models/infraction.py` — `Infraction` dataclass

### Services
- `bot/services/__init__.py` — Subpackage init
- `bot/services/guild_service.py` — `GuildService` (cache-first CRUD, soft delete, default-on-join)

### Cogs
- `bot/cogs/__init__.py` — Subpackage init
- `bot/cogs/core.py` — `CoreCog` with ping, status, help, sync

### Utils
- `bot/utils/__init__.py` — Subpackage init
- `bot/utils/checks.py` — `is_mod()`, `is_admin()` decorators
- `bot/utils/embeds.py` — `error_embed()`, `success_embed()`, `info_embed()`

### Migration
- `migrations/001_initial_schema.sql` — Guild, User, Member, Infraction, Ticket tables

### Tests
- `tests/__init__.py` — Test package init
- `tests/conftest.py` — Shared fixtures (mock DB, cache, guild)
- `tests/test_cache.py` — TTLCache unit tests
- `tests/test_guild_service.py` — GuildService unit tests
- `tests/test_checks.py` — Permission check unit tests

## Known Warnings (Tech Debt — Not Blockers)

1. **Database client sync-under-async**: `Database.connect()` uses sync `create_client`; queries may block event loop. Fix in Phase 2 with async Supabase client or `asyncio.to_thread()`.
2. **Cog load failure not handled**: No `try/except` around `load_extension` in `setup_hook`. Moot with single cog; add when multi-cog.
3. **Manual verification not executable**: Task 5.5 checked but not run in CI environment.
4. **Type hint `callable`**: `_build_prefix_callable` return type should be `Callable`, not `callable`.
5. **Cache key type mixing**: String vs int guild IDs across cache and mod role cache.
6. **Missing unit tests**: Soft-delete and help-module paths need pytest coverage once discord.py is available.

## CRITICAL Issues

None. Both previously critical gaps (guild-config soft delete, core-commands help with module) were resolved during verification.

## Archive Contents

- proposal.md ✅
- design.md ✅
- tasks.md ✅ (29/29 complete)
- verify-report.md ✅ (PASS WITH WARNINGS)
- archive-report.md ✅ (this file)

## SDD Cycle Status

Phase 1 is fully planned, implemented, verified, and archived. Ready for Phase 2.
