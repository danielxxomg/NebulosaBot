# Exploration: webhook-sync

## Context

The NebulosaBot architecture uses a cache-first pattern: RAM cache (TTLCache) → Supabase fallback, with 300s TTL and guild-scoped keys (`{guild_id}:entity`). The Next.js dashboard writes to Supabase directly via Server Actions using the `service_role` key. When the dashboard mutates guild config, economy config, or greeting config, the bot's RAM cache is **not** invalidated — causing up to 5 minutes of stale data. The original design diagram (`Diagramas/DiagramaSecuencia.mmd`, lines 28-31) explicitly calls for a `POST /webhook/sync` endpoint where the dashboard notifies the bot to evict the affected guild's cache. This webhook does not exist today.

## Current State

### Cache Layer (`bot/core/cache.py`)

- **TTLCache**: dict-based, per-key TTL, monotonic clock (lines 21-82)
- **`invalidate(key)`**: removes a single key (line 65)
- **`invalidate_guild(guild_id)`**: removes all keys with `{guild_id}:` prefix (line 71)
- Default TTL: 300s (5 min) (line 18)

### Per-Service Cache Key Templates

| Service | File | Key Template | TTL | Notes |
|---------|------|-------------|-----|-------|
| GuildService | `bot/services/guild_service.py:26` | `{guild_id}:config` | 300s | Also syncs `_guild_mod_role_cache` dict |
| GreetingService | `bot/services/greeting_service.py:25` | `{guild_id}:greeting_config` | 300s | |
| EconomyService | `bot/services/economy_service.py:286` | `{guild_id}:leaderboard:{sort_by}` | 30s | Only leaderboard is cached; economy_config is read directly from DB on every `gain_xp()` call (line 120) |
| TicketService | `bot/services/ticket_service.py:39` | *(channel ID set, not TTLCache)* | N/A | Uses `_ticket_channel_cache: set[int]` — not guild-scoped TTL keys |

**Key finding**: `EconomyService.gain_xp()` and `claim_daily()` call `self._db.get_economy_config(guild_id)` directly (lines 120, 182) — **no cache layer** for economy_config reads. Only the leaderboard is cached. This means economy_config changes from the dashboard are already picked up immediately by the bot (no desync). However, `invalidate_guild()` would still be useful as a safety net if caching is added later.

### Dashboard Mutation Points

| Server Action | File | Supabase Table | Entity |
|--------------|------|---------------|--------|
| `updateGuildConfig()` | `dashboard/lib/actions/guild-actions.ts:73` | `guild` | Guild config (prefix, language, modRoleId, logChannelId, ticketCategoryId, logEnabled) |
| `updateEconomyConfig()` | `dashboard/lib/actions/economy-actions.ts:59` | `economy_config` | Economy config (dailyReward, xpPerMessage, levelBaseXp, etc.) |
| `updateGreetingConfig()` | `dashboard/lib/actions/greeting-actions.ts:59` | `greeting_config` | Greeting config (welcome/goodbye channels, messages, card toggles) |

All three follow the same pattern: validate → persist to Supabase → `revalidatePath()` for Next.js cache. **None** notify the bot.

### Bot Process Model

- Entry: `bot/__main__.py` — `asyncio.run(main())` → `NebulosaBot.start(token)` (line 49)
- Bot class: `bot/bot.py` — extends `commands.Bot`, runs on discord.py's aiohttp-based gateway
- `aiohttp 3.14.1` is available as a transitive dependency of `discord.py` (verified in the venv)
- **No HTTP server** exists today — the bot only runs the Discord gateway connection
- Config: `bot/config.py` — `BotConfig` dataclass with `from_env()` loading from `.env`

### Design Diagram Evidence

`Diagramas/DiagramaSecuencia.mmd` lines 28-31:
```
par Notificación Asíncrona
    Web->>Bot: ⚡ POST /webhook/sync {guild_id, type: "config"}
    Bot->>Bot: 🗑️ Borra Cache del Guild ID
```

The diagram specifies: `{guild_id, type: "config"}` payload, POST to `/webhook/sync`, bot evicts the guild's cache.

## Affected Areas

- `bot/core/cache.py` — already has `invalidate_guild()`, no changes needed
- `bot/config.py` — needs `WEBHOOK_SECRET` and `WEBHOOK_PORT` env vars
- `bot/__main__.py` — needs to start the HTTP server alongside the bot
- `bot/bot.py` — needs to expose `cache` to the webhook handler
- **New file**: `bot/webhook/` — webhook route, auth middleware, server lifecycle
- `dashboard/lib/actions/guild-actions.ts` — add webhook call after Supabase write
- `dashboard/lib/actions/economy-actions.ts` — add webhook call after Supabase write
- `dashboard/lib/actions/greeting-actions.ts` — add webhook call after Supabase write
- `dashboard/.env.local.example` — add `WEBHOOK_SECRET` and `BOT_WEBHOOK_URL`

## Approaches

### Approach A: In-Process aiohttp Web Application

Start an `aiohttp.web.Application` on a separate port inside the same Python process as the bot, sharing the event loop.

- **Pros**:
  - Zero new dependencies — `aiohttp` is already installed via `discord.py`
  - Shares the bot's event loop and `TTLCache` instance directly (no IPC)
  - Simple deployment — one process, one container
  - Graceful shutdown via `bot.close()` tearing down the runner
  - Testable with `aiohttp.test_utils.TestClient` (async, no port binding needed)
  - Aligns with AGENTS.md: async HTTP server does NOT block the event loop
- **Cons**:
  - Binds a second port (must be configurable, default e.g. 8080)
  - Webhook crash could theoretically affect the bot process (mitigated by error handling)
  - Less isolation than a separate process
- **Effort**: Low-Medium

### Approach B: Separate FastAPI/Uvicorn Worker

Run a standalone FastAPI app as a subprocess or separate entrypoint, communicating with the bot via a shared mechanism (e.g., Redis pub/sub, Unix socket, or direct DB read on each webhook call).

- **Pros**:
  - Full process isolation — webhook crash doesn't affect the bot
  - Can scale independently
  - FastAPI is a well-known framework with good OpenAPI docs
- **Cons**:
  - Requires a new dependency (`fastapi` + `uvicorn`) not in `pyproject.toml`
  - Cannot share `TTLCache` instance across processes — must use IPC (Redis, socket, etc.)
  - More complex deployment — two processes to manage
  - More complex testing — need to mock the IPC layer
  - Adds operational overhead (supervising two processes, port management)
  - The bot's cache is in-process RAM; cross-process invalidation needs a bridge
- **Effort**: Medium-High

### Approach C: Discord.py Cog with Background HTTP Listener

Create a cog that starts an aiohttp web server in `cog_load()` and stops it in `cog_unload()`.

- **Pros**:
  - Follows the existing cog pattern — familiar structure
  - Shares the bot's event loop and cache
  - Cog can be loaded/unloaded dynamically
- **Cons**:
  - Cogs are for Discord interaction (AGENTS.md: "Cogs handle Discord interaction only — no business logic")
  - A webhook HTTP server is infrastructure, not a Discord interaction
  - Mixing HTTP serving into a cog blurs the architecture boundary
  - `cog_unload()` lifecycle may not guarantee clean HTTP server shutdown
- **Effort**: Low-Medium

## Recommendation

**Approach A: In-Process aiohttp Web Application.**

Rationale:
1. **Zero new dependencies** — `aiohttp` is already a transitive dependency of `discord.py` (verified: v3.14.1 in the venv)
2. **Direct cache access** — the webhook handler calls `bot.cache.invalidate_guild(guild_id)` with no IPC overhead
3. **AGENTS.md compliant** — an async HTTP server does not block the event loop; the "no blocking I/O" rule is satisfied
4. **Simple deployment** — one process, one container, one port to expose
5. **Testable** — `aiohttp.test_utils` provides `TestClient` and `TestServer` for integration tests without real port binding
6. **Follows the design diagram exactly** — `POST /webhook/sync` on a configurable port

The webhook server should be a separate module (`bot/webhook/`) started in `__main__.py` after the bot connects, not a cog. This keeps infrastructure concerns out of the cog layer.

## Security

### Authentication: HMAC-SHA256 Shared Secret

- Dashboard and bot share a `WEBHOOK_SECRET` env var (32+ random bytes, hex-encoded)
- Dashboard signs the request body with HMAC-SHA256 and sends the signature in a header (e.g., `X-Sync-Signature`)
- Bot verifies the signature before processing — constant-time comparison to prevent timing attacks
- **Why not mTLS**: overkill for a single-endpoint internal service; adds cert management complexity
- **Why not Supabase Edge Function intermediary**: adds latency, another service to maintain, and the dashboard already runs server-side with the secret

### Env Vars

- Bot: `WEBHOOK_SECRET` (required), `WEBHOOK_PORT` (default: 8080)
- Dashboard: `BOT_WEBHOOK_URL` (e.g., `http://bot:8080`), `WEBHOOK_SECRET` (same value)
- AGENTS.md: "Never hardcode IDs/secrets — read from env config" ✓

## Events and Payload

### Recommended Payload (First Slice)

```json
{
  "guild_id": "123456789012345678",
  "entity": "config"
}
```

- `entity` values: `"config"`, `"economy_config"`, `"greeting_config"`
- Bot calls `invalidate_guild(guild_id)` — evicts ALL guild cache keys
- **Why full invalidation, not targeted**: `invalidate_guild()` already exists, is O(n) over the small cache, and is safe. Targeted invalidation (per-entity key) adds complexity for minimal gain — a guild has at most ~5 cache keys.
- **Idempotency**: invalidation is inherently idempotent — calling it twice on the same guild is a no-op. Duplicate deliveries are safe.
- **Failure handling**: if the bot/webhook is down, the dashboard write to Supabase still succeeds. Cache stays stale until TTL expires (5 min max). This is **graceful degradation** — no data loss. The dashboard should use fire-and-forget (no retry) for the first slice.

### Dashboard Integration Pattern

After each Supabase write in the server actions, add a fire-and-forget `fetch()` call:

```typescript
// Fire-and-forget — don't await, don't block the response
fetch(process.env.BOT_WEBHOOK_URL!, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Sync-Signature": hmacSignature,
  },
  body: JSON.stringify({ guild_id: guildId, entity: "config" }),
}).catch(() => {}); // swallow errors — Supabase is source of truth
```

## First-Slice Scope Boundaries

### In Scope (First PR)

- `bot/webhook/server.py` — aiohttp web.Application with `POST /webhook/sync`
- `bot/webhook/auth.py` — HMAC-SHA256 signature verification
- `bot/webhook/models.py` — Pydantic/dataclass for request validation
- `bot/config.py` — add `webhook_secret` and `webhook_port` fields
- `bot/__main__.py` — start webhook server after bot connects
- Dashboard: add webhook call to all 3 server actions (fire-and-forget)
- Dashboard: add `BOT_WEBHOOK_URL` and `WEBHOOK_SECRET` to `.env.local.example`
- Tests: unit tests for auth, request validation, cache invalidation; integration test with `aiohttp.test_utils`

### Deferred (Future PRs)

- Per-entity targeted invalidation (only evict `{guild_id}:config` instead of all guild keys)
- Retry with exponential backoff + dead-letter queue
- Webhook health endpoint (`GET /health`)
- Metrics/logging dashboard for webhook calls
- Supabase Edge Function as intermediary (if bot moves behind a firewall)
- Rate limiting on the webhook endpoint

## Risks

- **Port conflict**: if `WEBHOOK_PORT` is already in use, the webhook server fails to start. **Mitigation**: catch `OSError` on startup, log a clear error, and let the bot continue without the webhook (degraded mode — cache stays stale until TTL).
- **Secret rotation**: changing `WEBHOOK_SECRET` requires coordinated restart of both bot and dashboard. **Mitigation**: document the procedure; consider supporting multiple secrets in a future iteration.
- **Dashboard network path**: if the dashboard can't reach the bot (different networks, firewalls), the webhook call fails silently. **Mitigation**: fire-and-forget design means this is already handled — Supabase is source of truth, cache just stays stale.

## Open Questions

1. Should the webhook endpoint return the list of invalidated keys in the response, or just a 200 OK? (Recommendation: 200 OK with `{status: "ok", invalidated: N}` for observability.)
2. Should the bot expose a `GET /health` endpoint for monitoring? (Recommendation: yes, but defer to a follow-up PR.)
3. Should the dashboard retry on 5xx errors? (Recommendation: no for first slice — fire-and-forget is simpler and the system degrades gracefully.)

## Ready for Proposal

Yes. The investigation is complete. All cache key templates are documented, all dashboard mutation points are identified, the approach is recommended with clear rationale, and the first-slice scope is well-defined. The orchestrator should proceed to `propose`.
