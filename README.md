# NebulosaBot

Discord bot with moderation (Sentinel), economy (Stellar), tickets, welcome/goodbye greetings, and a Next.js dashboard. Backed by Supabase Postgres with cache-first reads and Supabase Realtime CDC invalidation.

## What it does

- **Tickets**: panel, categories, auto-assign, transcripts, staff notes.
- **Moderation**: warn/mute/kick/ban with infraction history.
- **Economy**: daily claims, XP/levels, coins, leaderboards.
- **Greetings**: welcome/goodbye cards and messages (Pillow default; SVG stub behind probe+fallback).
- **Dashboard**: per-guild config for tickets/economy/greetings with admin-gated Server Actions.

## How to run (local)

```bash
# 1. Python 3.11+
uv sync
cp .env.example .env  # fill DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY

# 2. Supabase (CLI or hosted)
supabase start  # or set SUPABASE_URL/KEY to your project
# migrations run via `supabase db push` or `supabase migration up --linked`

# 3. Bot
uv run python -m bot

# 4. Dashboard (separate terminal)
cd dashboard && pnpm install && pnpm dev
```

## Architecture (brief)

```
bot/cogs/      → Discord interaction only
bot/services/  → business logic + cache integration (testable without Discord)
bot/core/      → cache (TTLCache), Realtime subscriber, DB facade
bot/core/db/   → table mixins (guild, greeting, ticket, etc.)
bot/models/    → dataclasses mirroring DB rows (camelCase ↔ snake_case)
bot/utils/     → brand tokens, embeds, cache_key, time helpers
dashboard/lib/actions/ → Server Actions gated by verifyGuildAdmin
```

- **Cache-first**: RAM `TTLCache` → DB fallback → populate cache, with `cache_key(guild_id, entity)` guild-scoping.
- **Realtime**: one `cache-sync` channel, 6 `on_postgres_changes` handlers (guild, greeting_config, ticket, ticket_note, member, economy_config), health/poll/watchdog loops, self-echo filtering.
- **No blocking I/O** on the event loop (`asyncio.to_thread` for Pillow/file I/O).
- **Tach boundaries**: 7 layers `cogs→views→services→utils→core→db→models` enforced by `tach check`; `ty` for types, `ruff` for lint/format, `prek` hooks.

## Docs

- `Diagramas/` — sequence/ER/command diagrams
- `openspec/` — specs, design, tasks
- `docs/runbooks/` — staging/live parity, incident flows

## Testing

```bash
uv run pytest              # full suite (≥75% coverage)
uv run ruff check .        # lint
uv run ty check            # type check
uv run tach check          # boundary check
cd dashboard && pnpm test  # dashboard unit tests
```
