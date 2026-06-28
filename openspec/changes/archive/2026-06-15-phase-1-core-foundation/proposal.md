# Proposal: Phase 1 — Core Foundation

## Intent

Runnable skeleton every phase depends on: bot connects to Discord + Supabase, cache serves guild config, minimal commands prove the stack. Infrastructure only.

## Scope

### In Scope
- Scaffolding: pyproject.toml, folder tree, .env, config.py
- NebulosaBot: `setup_hook()`, hybrid prefix, cog loading
- Supabase async client with health check
- RAM TTL cache per guild
- NebulosaContext with db/cache accessors
- GuildService: cache-first load, save, default-on-join
- Core cog: ping, status, help, sync
- Migration 001: Guild, User, Member, Infraction, Ticket
- `is_mod()`, `is_admin()` decorators
- Global `on_app_command_error`

### Out of Scope
- Feature cogs, dashboard, webhook server, persistent views
- XP/coins listeners, image gen, transcripts, auto-escalation

## Capabilities

### New
- `bot-core`: Bot class, setup_hook, hybrid prefix, cog loading, error handler
- `database-layer`: Supabase async client, health check
- `cache-layer`: Per-guild TTL RAM cache
- `guild-config`: CRUD, cache-first reads, default on join
- `core-commands`: ping, status, help, sync
- `permission-model`: `is_mod()`, `is_admin()` checks
- `initial-schema`: Migration 001, 5 core tables

### Modified
None — greenfield.

## Approach

Follow `Diagramas/DiagramaSecuencia.mmd` cache-first pattern. `setup_hook()` loads cogs → services via bot instance → cache before DB reads. Dynamic prefix from cached guild config.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/bot.py` | New | NebulosaBot, setup_hook |
| `bot/config.py` | New | Env vars, defaults |
| `bot/core/database.py` | New | Supabase wrapper |
| `bot/core/cache.py` | New | TTLCache |
| `bot/core/context.py` | New | NebulosaContext |
| `bot/services/guild_service.py` | New | Guild CRUD |
| `bot/cogs/core.py` | New | Core commands |
| `bot/utils/checks.py` | New | Permission checks |
| `migrations/001_initial_schema.sql` | New | Core tables |

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| No FK enforcement (Transaction Mode) | Med | App-level validation |
| Cache desync before webhook | Low | 5min TTL expiry |
| Hybrid command edge cases | Med | Test both modes |

## Rollback Plan

Delete `bot/` + `migrations/001_initial_schema.sql`. Drop tables reverse order. No production data.

## Dependencies

Python 3.11+, discord.py >=2.3, supabase-py, python-dotenv, Supabase project, Discord token.

## Success Criteria

- [ ] `python -m bot` starts, bot online
- [ ] `!ping` and `/ping` respond
- [ ] Guild config loads from DB into cache
- [ ] Default config inserted on guild join
- [ ] Permission checks gate commands
- [ ] Errors return user-friendly embeds

## Decisions (from Proposal Question Round)

| Question | Answer |
|----------|--------|
| Default prefix | `nb!` |
| Cache TTL | 5 minutes |
| Error format | Ephemeral embeds (slash), channel embeds (prefix) |
| Help command | Custom embed by module (Sentinel, Stellar, etc.) with pagination |
| Default language | `es` (Spanish) |
